"""Write-side adapters for the Compras Backstage surface.

The Core packages own their invariants. This module only translates operator
gestures into those public/domain writes: Buyman costs and Stockman BUY moves.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.module_loading import import_string

from shopman.backstage.projections.purchase import build_purchase
from shopman.shop.adapters.purchase_invoice_nfe import INVOICE_PRODUCT_MAP_KEYS
from shopman.shop.services.remote_mutations import (
    RemoteMutationInProgress,
    run_idempotent_mutation,
)

logger = logging.getLogger(__name__)


class PurchaseError(Exception):
    """Operator-facing purchase error with a stable code."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "purchase_error",
        field: str = "",
        status_code: int = 400,
        lines: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.field = field
        self.status_code = status_code
        #: Erros por LINHA, quando o gesto foi em lote. Um lote recusado sem
        #: dizer qual linha errou obriga o operador a procurar no escuro.
        self.lines = lines or []


@dataclass(frozen=True)
class ResolvedReceiptLine:
    line_id: str
    material: Any
    conversion: Any | None
    purchase_qty: Decimal
    base_qty: Decimal
    total_cost_q: int
    unit_cost_q: int
    expiry_date: Any | None
    note: str
    invoice_product_code: str
    invoice_lot: str
    checked: bool


#: Escopo da trava de recibo na `IdempotencyKey` do orderman.
#:
#: ⚠️ Nenhum modelo novo e nenhuma migração: a casa já tem esta tabela, com
#: `UniqueConstraint(scope, key)`, e já tem o envelope genérico
#: (`shop/services/remote_mutations.run_idempotent_mutation`). É o mesmo
#: mecanismo do commit de sessão, do replay de webhook e do submit do PDV.
RECEIPT_IDEMPOTENCY_SCOPE = "purchase.receipt"


def parse_invoice_access_key(raw: str) -> str | None:
    """Extract and validate a Brazilian NF-e/NFC-e 44-digit access key."""
    candidates = _invoice_key_candidates(raw)
    for key in candidates:
        if _valid_invoice_key(key):
            return key
    return None


def scan_invoice(qr_payload: str) -> tuple[dict[str, Any], str]:
    """Build a receipt draft from a scanned QR/chave.

    The built-in behavior validates the key and resolves the supplier by CNPJ.
    Full item extraction is intentionally adapter-based because reading SEFAZ/
    provider XML is deployment-specific.
    """
    access_key = parse_invoice_access_key(qr_payload)
    if not access_key:
        raise PurchaseError(
            "Não consegui validar a chave da NF. Reescaneie o QR/código de barras ou confira os 44 dígitos.",
            code="invoice_key_invalid",
            field="qrPayload",
        )

    draft = _invoice_reader_draft(access_key=access_key, qr_payload=qr_payload)
    if "supplierRef" in draft or "supplier_ref" in draft:
        supplier_ref = str(draft.get("supplierRef", draft.get("supplier_ref", "")) or "")
    else:
        supplier_ref = _supplier_ref_from_invoice_key(access_key)
    supplier_created = False
    note = str(draft.get("note") or "") or f"NF {access_key}"
    if not supplier_ref:
        supplier_ref, supplier_created = _register_supplier_from_issuer(draft.get("issuer") or {})
        if supplier_ref:
            note = note.replace(" - fornecedor nao cadastrado", "")
    active_receipt = {
        "mode": "invoice",
        "supplierRef": supplier_ref,
        "invoiceInput": qr_payload,
        "note": note,
        "lines": draft.get("lines") or (),
    }
    if draft.get("lines"):
        message = (
            "NF lida e fornecedor cadastrado da nota. Revise os itens antes de confirmar."
            if supplier_created
            else "NF lida. Revise os itens antes de confirmar."
        )
    else:
        message = "Chave da NF lida. Itens não vieram do provedor fiscal; lance ou importe as linhas para conferir."
    return build_purchase(active_receipt=active_receipt), message


def confirm_receipt(payload: dict[str, Any], *, user) -> dict[str, Any]:
    """Confirm a material receipt, writing Stockman BUY moves atomically."""
    Supplier = apps.get_model("buyman", "Supplier")

    mode = str(payload.get("mode") or "").strip()
    if mode not in {"invoice", "manual"}:
        raise PurchaseError("Informe se a entrada é com NF ou sem NF.", code="receipt_mode_invalid", field="mode")

    invoice_key = str(payload.get("invoiceAccessKey") or payload.get("invoice_access_key") or "").strip()
    if mode == "invoice" and not parse_invoice_access_key(invoice_key):
        raise PurchaseError(
            "Entrada com NF precisa de uma chave de acesso válida.",
            code="invoice_key_required",
            field="invoiceAccessKey",
        )

    supplier_ref = str(payload.get("supplierRef") or payload.get("supplier_ref") or "").strip()
    supplier = Supplier.objects.filter(ref=supplier_ref).first()
    if not supplier:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="supplierRef")
    if not supplier.is_active:
        raise PurchaseError("Fornecedor inativo não pode receber entrada.", code="supplier_inactive", field="supplierRef")

    raw_lines = payload.get("lines") or []
    if not isinstance(raw_lines, list) or not raw_lines:
        raise PurchaseError("Inclua ao menos um item recebido.", code="receipt_empty", field="lines")

    if mode == "invoice":
        _require_supplier_is_issuer(supplier=supplier, invoice_key=invoice_key)

    lines = [_resolve_receipt_line(raw, index=index, supplier=supplier) for index, raw in enumerate(raw_lines)]
    note = str(payload.get("note") or "").strip()
    source_ref = invoice_key or _manual_source_ref(supplier_ref=supplier.ref, note=note, lines=lines)
    position = _default_receive_position()

    def _receber() -> tuple[dict[str, Any], int]:
        _write_receipt(
            mode=mode,
            invoice_key=invoice_key,
            supplier=supplier,
            lines=lines,
            note=note,
            source_ref=source_ref,
            position=position,
            user=user,
        )
        return (
            {
                "source_ref": source_ref,
                "mode": mode,
                "supplier_ref": supplier.ref,
                "supplier_name": supplier.name or supplier.ref,
                "lines": len(lines),
                "total_cost_q": sum(line.total_cost_q for line in lines),
                "operator": (getattr(user, "get_username", lambda: "")() if user else "") or "",
                "received_at": timezone.now().isoformat(),
            },
            200,
        )

    # ⚠️ A trava é do BANCO, não da tela. A guarda que existia era só o botão
    # desabilitado enquanto o primeiro clique estava em voo — nenhuma delas
    # sobrevive a um 504 no proxy, a uma aba fechada, ou a um segundo tablet.
    #
    # E o caminho mais provável no chão nem é o retry: três horas depois ninguém
    # conseguia responder "essa nota já entrou?", e reescanear é o gesto natural de
    # quem está em dúvida — duplicando o estoque em silêncio.
    #
    # Ironia que serviu de prova: `reject_receipt` JÁ era idempotente (dedupe de
    # directive). RECUSAR duas vezes não duplicava nada; RECEBER duas vezes sim.
    try:
        resultado = run_idempotent_mutation(
            scope=RECEIPT_IDEMPOTENCY_SCOPE, key=source_ref, execute=_receber
        )
    except RemoteMutationInProgress as exc:
        raise PurchaseError(
            "Esta entrada já está sendo registrada. Aguarde alguns segundos e recarregue.",
            code="receipt_in_progress",
            field="invoiceAccessKey" if mode == "invoice" else "note",
        ) from exc

    if resultado.replayed:
        # Não é replay silencioso de propósito: responder "deu certo" a quem
        # REESCANEOU faria o operador acreditar numa entrada nova. Dizer quando e
        # por quem serve aos dois casos — o retry e a dúvida.
        raise PurchaseError(
            _receipt_already_received_message(resultado.response_body),
            code="receipt_already_received",
            field="invoiceAccessKey" if mode == "invoice" else "note",
        )

    return build_purchase()


def _receipt_already_received_message(recibo: dict[str, Any]) -> str:
    quando = _format_receipt_moment(str(recibo.get("received_at") or ""))
    quem = str(recibo.get("operator") or "").strip()
    partes = ["Esta nota já entrou"]
    if quando:
        partes.append(f"em {quando}")
    if quem:
        partes.append(f"por {quem}")
    return " ".join(partes) + ". Confira o histórico de recebimentos antes de lançar de novo."


def _format_receipt_moment(raw: str) -> str:
    if not raw:
        return ""
    try:
        momento = timezone.localtime(datetime.fromisoformat(raw))
    except ValueError:
        return ""
    return momento.strftime("%d/%m às %H:%M")


def _write_receipt(*, mode, invoice_key, supplier, lines, note, source_ref, position, user) -> None:
    """O corpo do recebimento — o que era o `with transaction.atomic()` de sempre."""
    Batch = apps.get_model("stockman", "Batch")
    Move = apps.get_model("stockman", "Move")
    from shopman.stockman import stock

    with transaction.atomic():
        for line in lines:
            batch_ref = ""
            if line.expiry_date or line.material.shelf_life_days is not None:
                batch_ref = _batch_ref(source_ref=source_ref, line=line)
                Batch.objects.get_or_create(
                    ref=batch_ref,
                    defaults={
                        "sku": line.material.sku,
                        "production_date": timezone.localdate(),
                        "expiry_date": line.expiry_date,
                        "supplier": supplier.name or supplier.ref,
                        "notes": _receipt_batch_note(receipt_note=note, line_note=line.note),
                    },
                )

            stock.receive(
                quantity=line.base_qty,
                sku=line.material.sku,
                position=position,
                batch=batch_ref,
                user=user,
                reason=_receipt_reason(mode=mode, source_ref=source_ref),
                kind=Move.Kind.BUY,
                purchase_supplier_ref=supplier.ref,
                purchase_supplier_name=supplier.name,
                purchase_receipt_mode=mode,
                purchase_invoice_access_key=invoice_key,
                purchase_receipt_note=note,
                purchase_line_note=line.note,
                purchase_line_id=line.line_id,
                purchase_material_sku=line.material.sku,
                purchase_qty=str(line.purchase_qty),
                purchase_base_qty=str(line.base_qty),
                purchase_total_cost_q=line.total_cost_q,
                purchase_unit_cost_q=line.unit_cost_q,
                **_converted_via(line),
            )
            if line.total_cost_q > 0:
                _upsert_supplier_cost(
                    material=line.material,
                    supplier=supplier,
                    conversion=line.conversion,
                    cost_q=line.unit_cost_q,
                    make_preferred=False,
                    prefer_if_missing=True,
                )
        if mode == "invoice":
            _learn_invoice_product_map(supplier=supplier, lines=lines)


def reject_receipt(payload: dict[str, Any], *, user) -> tuple[dict[str, Any], str]:
    """Record a supplier delivery refusal/return without touching stock."""
    Supplier = apps.get_model("buyman", "Supplier")

    mode = str(payload.get("mode") or "").strip()
    if mode not in {"invoice", "manual"}:
        raise PurchaseError("Informe se a devolução é com NF ou sem NF.", code="receipt_mode_invalid", field="mode")

    invoice_key = str(payload.get("invoiceAccessKey") or payload.get("invoice_access_key") or "").strip()
    if invoice_key and not parse_invoice_access_key(invoice_key):
        raise PurchaseError(
            "Chave da NF inválida para registrar devolução.",
            code="invoice_key_invalid",
            field="invoiceAccessKey",
        )

    supplier_ref = str(payload.get("supplierRef") or payload.get("supplier_ref") or "").strip()
    supplier = Supplier.objects.filter(ref=supplier_ref).first()
    if not supplier:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="supplierRef")

    raw_lines = payload.get("lines") or []
    if raw_lines and not isinstance(raw_lines, list):
        raise PurchaseError("Itens da devolução inválidos.", code="receipt_lines_invalid", field="lines")

    note = str(payload.get("note") or "").strip()
    line_notes = [str(line.get("lineNote") or line.get("line_note") or "").strip() for line in raw_lines if isinstance(line, dict)]
    reason = note or next((item for item in line_notes if item), "")
    if not reason:
        raise PurchaseError(
            "Descreva o motivo da recusa/devolução antes de registrar.",
            code="receipt_rejection_reason_required",
            field="note",
        )

    source_ref = invoice_key or _manual_source_ref(supplier_ref=supplier.ref, note=reason)
    receipt_ref = _receipt_rejection_ref(source_ref=source_ref, supplier_ref=supplier.ref)
    context = {
        "receipt_ref": receipt_ref,
        "supplier_ref": supplier.ref,
        "supplier_name": supplier.name or supplier.ref,
        "document_ref": source_ref,
        "receipt_mode": mode,
        "reason": reason,
        "lines_text": _receipt_rejection_lines(raw_lines),
        "operator_username": getattr(user, "get_username", lambda: "")() if user else "",
        "shop_name": _shop_name(),
    }
    notification_payload = {
        "event": "purchase_receipt_rejected",
        "recipient": str(getattr(settings, "SHOPMAN_PURCHASE_INTERNAL_RECIPIENT", "compras")),
        "backends": list(getattr(settings, "SHOPMAN_PURCHASE_INTERNAL_NOTIFICATION_BACKENDS", ["console"])),
        "context": context,
    }
    dedupe_key = _receipt_rejection_dedupe_key(
        source_ref=source_ref,
        supplier_ref=supplier.ref,
        reason=reason,
        lines_text=context["lines_text"],
    )

    from shopman.shop.directives import NOTIFICATION_SEND, create_deduped

    create_deduped(topic=NOTIFICATION_SEND, payload=notification_payload, dedupe_key=dedupe_key)
    return build_purchase(), f"Devolução registrada ({receipt_ref})."


def upsert_cost(payload: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Create/update a supplier cost from the Base > Custos form."""
    Material = apps.get_model("buyman", "Material")
    Supplier = apps.get_model("buyman", "Supplier")

    material_sku = str(payload.get("materialSku") or payload.get("material_sku") or "").strip()
    supplier_ref = str(payload.get("supplierRef") or payload.get("supplier_ref") or "").strip()
    material = Material.objects.filter(sku=material_sku).first()
    supplier = Supplier.objects.filter(ref=supplier_ref).first()
    if not material:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field="materialSku")
    if not supplier:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="supplierRef")

    cost_q = parse_money_input(str(payload.get("costInput") or payload.get("cost_input") or ""))
    if cost_q <= 0:
        raise PurchaseError("Informe um valor de compra maior que zero.", code="cost_invalid", field="costInput")

    conversion = _resolve_conversion(
        payload.get("conversionId") or payload.get("conversion_id"),
        material=material,
        supplier=supplier,
        field="conversionId",
    )
    _upsert_supplier_cost(
        material=material,
        supplier=supplier,
        conversion=conversion,
        cost_q=cost_q,
        make_preferred=_as_flag(payload, "makePreferred", "make_preferred", field="makePreferred"),
    )
    # Custo de fornecedor é dado de dinheiro: quem alterou fica no log
    # estruturado (o modelo não tem trilha própria — decisão adiada com o
    # ADR-023, custo vivo × congelado).
    logger.info(
        "purchase.cost_upserted",
        extra={
            "material": material.sku,
            "supplier": supplier.ref,
            "cost_q": cost_q,
            "user": getattr(user, "username", "") or "anon",
        },
    )
    return build_purchase()


def upsert_costs(payload: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Vários custos de uma vez, quase sempre do mesmo fornecedor.

    Um insumo só vira pedido quando tem custo padrão e fornecedor preferencial
    — ``_queue_supplier_purchase_request`` recusa sem isso. Cadastrar dezenas
    de insumos um a um, com dois selects e um round-trip que devolve a projeção
    inteira a cada salvamento, é trabalho de horas para uma tarefa que é, na
    prática, uma tabela de preços do mesmo fornecedor. O ``supplierRef`` do
    lote é o padrão herdado por todas as linhas; a linha que discordar traz o
    seu.

    **Tudo-ou-nada.** Custo é dado de dinheiro: um lote meio-aplicado deixa o
    operador sem saber o que entrou e o que não entrou. Toda linha é validada
    antes de qualquer escrita, e o lote inválido volta com o índice, o SKU e o
    campo de cada linha errada — sem isso a recusa manda procurar no escuro.

    Linha em branco é omissão, não erro: a tela lista todos os insumos e o
    operador preenche os que sabe.
    """
    Material = apps.get_model("buyman", "Material")
    Supplier = apps.get_model("buyman", "Supplier")

    default_supplier_ref = str(payload.get("supplierRef") or payload.get("supplier_ref") or "").strip()
    make_preferred = _as_flag(payload, "makePreferred", "make_preferred", field="makePreferred")
    raw_lines = payload.get("costs") or payload.get("lines") or []
    if not isinstance(raw_lines, list):
        raise PurchaseError("Lote de custos inválido.", code="cost_batch_invalid", field="costs")

    resolved: list[tuple[Any, Any, Any, int]] = []
    line_errors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(raw_lines):
        entry = dict(raw or {})
        material_sku = str(entry.get("materialSku") or entry.get("material_sku") or "").strip()
        cost_text = str(entry.get("costInput") or entry.get("cost_input") or "")
        if not cost_text.strip():
            continue

        def fail(detail: str, *, field: str, sku: str = material_sku, at: int = index) -> None:
            line_errors.append({"index": at, "materialSku": sku, "field": field, "detail": detail})

        material = Material.objects.filter(sku=material_sku).first()
        if not material:
            fail("Insumo não encontrado.", field="materialSku")
            continue
        # Insumo e fornecedor aposentados são recusados AQUI, na validação, e
        # não lá na frente pelo `full_clean` do modelo: um custo preferencial
        # não pode apontar para par retirado, e essa recusa chegava como
        # `ValidationError` crua no meio do loop de escrita — sem número de
        # linha, que é exatamente a busca no escuro que o lote veio eliminar.
        if not material.is_active:
            fail("Insumo inativo.", field="materialSku")
            continue

        supplier_ref = (
            str(entry.get("supplierRef") or entry.get("supplier_ref") or "").strip() or default_supplier_ref
        )
        supplier = Supplier.objects.filter(ref=supplier_ref).first()
        if not supplier:
            fail("Fornecedor não encontrado.", field="supplierRef")
            continue
        if not supplier.is_active:
            fail("Fornecedor inativo.", field="supplierRef")
            continue

        key = (material.sku, supplier.ref)
        if key in seen:
            fail("Insumo repetido no lote para o mesmo fornecedor.", field="materialSku")
            continue

        try:
            cost_q = parse_money_input(cost_text)
        except PurchaseError as exc:
            fail(str(exc), field="costInput")
            continue
        if cost_q <= 0:
            fail("Informe um valor de compra maior que zero.", field="costInput")
            continue

        try:
            conversion = _resolve_conversion(
                entry.get("conversionId") or entry.get("conversion_id"),
                material=material,
                supplier=supplier,
                field="conversionId",
            )
        except PurchaseError as exc:
            fail(str(exc), field=exc.field or "conversionId")
            continue

        seen.add(key)
        resolved.append((material, supplier, conversion, cost_q))

    if line_errors:
        raise PurchaseError(
            "Corrija as linhas indicadas para lançar o lote.",
            code="cost_batch_invalid",
            lines=line_errors,
        )
    if not resolved:
        raise PurchaseError("Informe ao menos um valor para lançar.", code="cost_batch_empty", field="costs")

    with transaction.atomic():
        for material, supplier, conversion, cost_q in resolved:
            _upsert_supplier_cost(
                material=material,
                supplier=supplier,
                conversion=conversion,
                cost_q=cost_q,
                make_preferred=make_preferred,
                # O primeiro custo de um insumo vira o preferencial sozinho —
                # mesma regra do recebimento. Sem preferencial o insumo
                # continua fora do pedido, que é justamente o que o lote veio
                # resolver.
                prefer_if_missing=True,
            )

    logger.info(
        "purchase.costs_batch_upserted",
        extra={
            "count": len(resolved),
            "suppliers": sorted({supplier.ref for _, supplier, _, _ in resolved}),
            "user": getattr(user, "username", "") or "anon",
        },
    )
    return {"saved": len(resolved), "purchase": build_purchase()}


def set_min_stock(payload: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Declara o estoque mínimo dos insumos — a outra metade da solicitação.

    ``dailyUse`` sai das baixas que a produção lança ao finalizar uma ficha; sem
    fornada rodando no sistema ele é zero. E aí o cálculo fecha o círculo contra
    o operador: sem consumo, o mínimo também cai para zero
    (``daily_use * replenish_at if daily_use > 0 else 0``), o alvo de reposição
    vira zero e ``suggestedQty`` é zero para sempre. Cadastrar custo e
    fornecedor não muda isso — o insumo simplesmente não aparece no Compras.

    O mínimo declarado quebra esse círculo: com ele o alvo existe sem histórico
    nenhum, e o insumo volta a poder virar pedido. Mora em
    ``Material.metadata["purchase"]["min_stock"]``, que é onde a projeção já o
    procura — nenhum campo novo, nenhuma migração.

    Zero **apaga** a declaração em vez de gravar zero: os dois levam ao mesmo
    alvo hoje, mas só o campo ausente volta a seguir o consumo quando a produção
    começar a rodar.
    """
    Material = apps.get_model("buyman", "Material")

    raw_lines = payload.get("minimums") or payload.get("min_stocks") or []
    if not isinstance(raw_lines, list):
        raise PurchaseError("Lote de mínimos inválido.", code="min_stock_batch_invalid", field="minimums")

    resolved: list[tuple[Any, Decimal | None]] = []
    line_errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, raw in enumerate(raw_lines):
        entry = dict(raw or {})
        material_sku = str(entry.get("materialSku") or entry.get("material_sku") or "").strip()
        raw_value = entry.get("minStock", entry.get("min_stock"))
        text = "" if raw_value is None else str(raw_value)
        if not text.strip():
            continue

        def fail(detail: str, *, field: str, sku: str = material_sku, at: int = index) -> None:
            line_errors.append({"index": at, "materialSku": sku, "field": field, "detail": detail})

        material = Material.objects.filter(sku=material_sku).first()
        if not material:
            fail("Insumo não encontrado.", field="materialSku")
            continue
        if material.sku in seen:
            fail("Insumo repetido no lote.", field="materialSku")
            continue

        value = parse_qty_input(text)
        if value is None:
            fail("Informe uma quantidade válida.", field="minStock")
            continue

        seen.add(material.sku)
        resolved.append((material, None if value == 0 else value))

    if line_errors:
        raise PurchaseError(
            "Corrija as linhas indicadas para lançar os mínimos.",
            code="min_stock_batch_invalid",
            lines=line_errors,
        )
    if not resolved:
        raise PurchaseError("Informe ao menos um mínimo.", code="min_stock_batch_empty", field="minimums")

    with transaction.atomic():
        for material, value in resolved:
            metadata = dict(material.metadata or {})
            purchase = dict(metadata.get("purchase") or {})
            if value is None:
                purchase.pop("min_stock", None)
                purchase.pop("minStock", None)
            else:
                purchase["min_stock"] = str(value)
                purchase.pop("minStock", None)
            metadata["purchase"] = purchase
            material.metadata = metadata
            material.save(update_fields=["metadata", "updated_at"])

    logger.info(
        "purchase.min_stock_set",
        extra={
            "count": len(resolved),
            "materials": sorted(material.sku for material, _ in resolved),
            "user": getattr(user, "username", "") or "anon",
        },
    )
    return {"saved": len(resolved), "purchase": build_purchase()}


#: Rótulo de conversão cabe em 60 caracteres (``MaterialConversion.label``).
CONVERSION_LABEL_MAX = 60


def declare_conversion(payload: dict[str, Any], *, user=None) -> tuple[dict[str, Any], str, str]:
    """Declara uma conversão de unidade sem sair do recebimento.

    O buraco que isto fecha: até aqui o operador só podia ESCOLHER entre as
    conversões já cadastradas, e cadastrar era coisa do Admin. Uma nota com uma
    embalagem nova — o caso normal, não o raro — parava a entrada e mandava o
    operador para outra tela, no meio da conferência, com o entregador esperando.

    O que **não** muda: a R4 continua valendo, porque continua sendo uma pessoa
    declarando o fator. A NF sugere (``conversionSuggestion``); quem assina é
    quem está com a nota na mão, e a linha guarda o autor.
    """
    Material = apps.get_model("buyman", "Material")
    Supplier = apps.get_model("buyman", "Supplier")
    MaterialConversion = apps.get_model("buyman", "MaterialConversion")

    material_sku = str(payload.get("materialSku") or payload.get("material_sku") or "").strip()
    material = Material.objects.filter(sku=material_sku).first()
    if not material:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field="materialSku")
    if not material.is_active:
        raise PurchaseError(
            "Insumo inativo não recebe conversão nova.",
            code="material_inactive",
            field="materialSku",
        )

    supplier_ref = str(payload.get("supplierRef") or payload.get("supplier_ref") or "").strip()
    supplier = None
    if supplier_ref:
        supplier = Supplier.objects.filter(ref=supplier_ref).first()
        if not supplier:
            raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="supplierRef")

    # A nota sabe o fator, mas só depois de existir insumo: "7 CX = 35 KG" só
    # vira "1 caixa = 5 kg" quando há uma unidade-base para converter PARA. Na
    # nota real o item chega como "MANTEIGA S/SAL CX 5 KG PRESIDENT TEU" e não
    # casa com nenhum insumo, então a sugestão do scan sai vazia — e o operador
    # que escolhe a manteiga na mão caía num cadastro manual que a nota já
    # respondia. Aqui o par volta e o servidor deriva, com a mesma física.
    derived = _conversion_from_invoice_axes(payload, material=material)
    if derived is not None:
        payload = {
            "label": payload.get("label") or derived.label,
            "factor": payload.get("factor") or derived.factor,
            "kind": payload.get("kind") or derived.kind,
        }

    label = str(payload.get("label") or "").strip()
    if not label:
        raise PurchaseError(
            "Dê um nome à embalagem: 'saco 25 kg', 'pacote 500 g', 'cartela'.",
            code="conversion_label_required",
            field="label",
        )
    if len(label) > CONVERSION_LABEL_MAX:
        raise PurchaseError(
            f"O rótulo da conversão cabe em {CONVERSION_LABEL_MAX} caracteres.",
            code="conversion_label_too_long",
            field="label",
        )

    factor = _decimal(payload.get("factor"))
    if factor <= 0:
        raise PurchaseError(
            f"O fator precisa ser maior que zero: quanto vale UM {label} em {material.unit}.",
            code="conversion_factor_invalid",
            field="factor",
        )

    kind = str(payload.get("kind") or MaterialConversion.Kind.CONVENTIONAL).strip()
    if kind not in set(MaterialConversion.Kind.values):
        raise PurchaseError(
            "Tipo de conversão inválido.",
            code="conversion_kind_invalid",
            field="kind",
        )

    # Declarar duas vezes a MESMA coisa não é conflito, é o segundo clique — ou
    # dois operadores lendo a mesma nota. Devolver a linha que já existe evita
    # um "Edite a existente" incompreensível diante de um formulário idêntico.
    # Rótulo igual com fator DIFERENTE continua recusado: aí é conflito de
    # verdade, e quem decide qual vale é o Admin.
    existing = MaterialConversion.objects.filter(
        material=material, supplier=supplier, label=label,
    ).first()
    if existing is not None and existing.to_base_factor == factor and existing.kind == kind:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=["is_active", "updated_at"])
        return build_purchase(), f"Conversão já cadastrada: {label}.", str(existing.pk)

    conversion = MaterialConversion(
        material=material,
        supplier=supplier,
        label=label,
        to_base_factor=factor,
        kind=kind,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    try:
        # `full_clean` roda as UniqueConstraint parciais (rótulo repetido no
        # insumo/fornecedor) além do `clean` do modelo — a recusa vem com a
        # mensagem que o próprio Core escreveu, e não com uma cópia daqui.
        conversion.full_clean()
        conversion.save()
    except ValidationError as exc:
        errors = getattr(exc, "message_dict", None) or {}
        # Apontar para o campo que o Core reclamou, e não sempre para o rótulo:
        # fator com casas demais chegava rotulado como erro de nome, e a tela
        # destacava o campo errado.
        field = "factor" if "to_base_factor" in errors else "label"
        raise PurchaseError(
            "; ".join(message for messages in errors.values() for message in messages) or str(exc),
            code="conversion_validation_failed",
            field=field,
        ) from exc

    logger.info(
        "purchase.conversion_declared material=%s supplier=%s label=%s factor=%s kind=%s",
        material.sku,
        supplier.ref if supplier else "",
        label,
        factor,
        kind,
    )
    approximate = " (aproximada)" if conversion.is_approximate else ""
    message = f"Conversão salva: 1 {label} = {_format_decimal(factor)} {material.unit}{approximate}."
    return build_purchase(), message, str(conversion.pk)


def set_purchase_request_status(material_sku: str, status: str, *, user=None) -> dict[str, Any]:
    """Persist the operator-side status for a replenishment decision."""
    if status not in {"approved", "sent"}:
        raise PurchaseError("Status de compra inválido.", code="request_status_invalid")
    Material = apps.get_model("buyman", "Material")
    material = Material.objects.filter(sku=material_sku).first()
    if not material:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field="materialSku", status_code=404)

    with transaction.atomic():
        dispatch = _queue_supplier_purchase_request(material, user=user) if status == "sent" else None

        metadata = dict(material.metadata or {})
        purchase = dict(metadata.get("purchase") or {})
        purchase["request_status"] = status
        purchase["request_status_at"] = timezone.now().isoformat()
        if dispatch:
            purchase["request_ref"] = dispatch["purchase_ref"]
            purchase["request_supplier_ref"] = dispatch["supplier_ref"]
            purchase["request_channel"] = dispatch["channel"]
            purchase["request_recipient"] = dispatch["recipient"]
            purchase["request_dedupe_key"] = dispatch["dedupe_key"]
        metadata["purchase"] = purchase
        material.metadata = metadata
        material.save(update_fields=["metadata", "updated_at"])
    return build_purchase()


def _queue_supplier_purchase_request(material, *, user=None) -> dict[str, str]:
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")

    cost = (
        SupplierMaterialCost.objects.select_related("supplier", "material", "conversion")
        .filter(material=material, is_preferred=True)
        .first()
    )
    if not cost:
        raise PurchaseError(
            "Defina o custo padrão e o fornecedor antes de enviar o pedido.",
            code="purchase_preferred_cost_required",
            field="materialSku",
        )
    supplier = cost.supplier
    if not supplier.is_active:
        raise PurchaseError(
            "Fornecedor inativo não pode receber pedido de compra.",
            code="supplier_inactive",
            field="supplierRef",
        )

    channel, recipient, backends = _supplier_dispatch_route(supplier)
    snapshot = _purchase_request_snapshot(material, cost)
    purchase_ref = _purchase_ref(material.sku, supplier.ref, snapshot["purchase_qty_display"])
    context = {
        **snapshot,
        "purchase_ref": purchase_ref,
        "supplier_ref": supplier.ref,
        "supplier_name": supplier.name or supplier.ref,
        "shop_name": _shop_name(),
        "requested_delivery_label": _requested_delivery_label(supplier),
        "operator_username": getattr(user, "get_username", lambda: "")() if user else "",
        "operator_note": "",
    }
    payload = {
        "event": "purchase_request",
        "recipient": recipient,
        "backends": backends,
        "context": context,
    }
    dedupe_key = _purchase_request_dedupe_key(
        material_sku=material.sku,
        supplier_ref=supplier.ref,
        purchase_qty=snapshot["purchase_qty_display"],
        cost_q=cost.cost_q,
    )

    from shopman.shop.directives import NOTIFICATION_SEND, create_deduped

    create_deduped(topic=NOTIFICATION_SEND, payload=payload, dedupe_key=dedupe_key)
    return {
        "purchase_ref": purchase_ref,
        "supplier_ref": supplier.ref,
        "channel": channel,
        "recipient": recipient,
        "dedupe_key": dedupe_key,
    }


def _supplier_dispatch_route(supplier) -> tuple[str, str, list[str]]:
    meta = _purchase_meta(supplier)
    preferred = _meta_text(
        meta,
        "order_channel",
        "orderChannel",
        "preferred_order_channel",
        "preferredOrderChannel",
        "preferred_channel",
        "preferredChannel",
    ).lower()
    contact = _meta_text(meta, "order_contact", "orderContact", "contact")
    email = _meta_text(meta, "order_email", "orderEmail", "email") or supplier.email or _email_from_contact(contact)
    phone = _meta_text(meta, "order_phone", "orderPhone", "whatsapp", "phone") or supplier.phone or _phone_from_contact(contact)

    if preferred == "email" and email:
        return "email", email, ["email", "console"]
    if preferred in {"sms", "phone"} and phone:
        return "sms", phone, ["sms", "console"]
    if preferred in {"whatsapp", "manychat"} and phone:
        return "whatsapp", phone, ["manychat", "console"]
    if preferred == "console":
        return "console", supplier.ref, ["console"]
    if preferred:
        raise PurchaseError(
            f"Canal preferencial do fornecedor sem contato utilizável: {preferred}.",
            code="supplier_contact_missing",
            field="supplierRef",
        )
    if email:
        return "email", email, ["email", "console"]
    if phone:
        return "sms", phone, ["sms", "console"]
    raise PurchaseError(
        "Fornecedor sem e-mail ou telefone para envio do pedido.",
        code="supplier_contact_missing",
        field="supplierRef",
    )


def _purchase_request_snapshot(material, cost) -> dict[str, str]:
    projected = next((item for item in build_purchase().materials if item.sku == material.sku), None)
    suggested_base_qty = Decimal(str(projected.suggestedQty if projected else 0)).to_integral_value(
        rounding=ROUND_CEILING
    )
    if suggested_base_qty <= 0:
        raise PurchaseError(
            "Este insumo não tem reposição sugerida agora.",
            code="purchase_request_not_needed",
            field="materialSku",
        )

    factor = Decimal(cost.conversion.to_base_factor) if cost.conversion_id else Decimal("1")
    purchase_qty = (suggested_base_qty / factor).to_integral_value(rounding=ROUND_CEILING)
    if purchase_qty <= 0:
        purchase_qty = Decimal("1")
    base_qty = purchase_qty * factor
    estimated_total_q = int((Decimal(cost.cost_q) * purchase_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    unit_label = cost.purchase_unit_label or material.unit
    purchase_qty_display = f"{_format_decimal(purchase_qty)} {unit_label}".strip()
    base_qty_display = f"{_format_decimal(base_qty)} {material.unit}".strip()
    lines_text = f"- {material.name} ({material.sku}): {purchase_qty_display} ({base_qty_display})"
    return {
        "material_sku": material.sku,
        "material_name": material.name,
        "purchase_unit_label": unit_label,
        "purchase_qty_display": purchase_qty_display,
        "base_qty_display": base_qty_display,
        "estimated_total": _format_money_q(estimated_total_q),
        "lines_text": lines_text,
    }


def _purchase_ref(material_sku: str, supplier_ref: str, purchase_qty: str) -> str:
    digest = hashlib.sha1(f"{material_sku}:{supplier_ref}:{purchase_qty}".encode()).hexdigest()[:6].upper()
    return f"PC-{timezone.localdate():%y%m%d}-{digest}"


def _purchase_request_dedupe_key(*, material_sku: str, supplier_ref: str, purchase_qty: str, cost_q: int) -> str:
    digest = hashlib.sha1(f"{material_sku}:{supplier_ref}:{purchase_qty}:{cost_q}".encode()).hexdigest()[:16]
    return f"purchase.request:{material_sku[:32]}:{supplier_ref[:32]}:{digest}"[:128]


def _shop_name() -> str:
    try:
        Shop = apps.get_model("shop", "Shop")
        shop = Shop.load()
        return str(getattr(shop, "name", "") or "Loja")
    except Exception:
        logger.debug("purchase.shop_name_failed", exc_info=True)
        return "Loja"


def _requested_delivery_label(supplier) -> str:
    meta = _purchase_meta(supplier)
    lead_time = _meta_text(meta, "lead_time_days", "leadTimeDays")
    if lead_time:
        try:
            days = int(lead_time)
        except ValueError:
            return "A combinar"
        if days <= 0:
            return "Assim que possível"
        target = timezone.localdate() + timedelta(days=days)
        return f"até {target:%d/%m/%Y}"
    return "A combinar"


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.001")).normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _format_money_q(value: int) -> str:
    reais = Decimal(value) / Decimal("100")
    return f"R$ {reais:.2f}".replace(".", ",")


def _meta_text(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _email_from_contact(value: str) -> str:
    contact = str(value or "").strip()
    if "@" not in contact:
        return ""
    return contact


def _phone_from_contact(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) >= 10 else ""


def _purchase_meta(obj) -> dict[str, Any]:
    metadata = dict(getattr(obj, "metadata", None) or {})
    nested = metadata.get("purchase")
    if isinstance(nested, dict):
        return {**metadata, **nested}
    return metadata


#: Casas decimais da quantidade em toda a superfície de Compras.
QTY_PLACES = Decimal("0.001")

#: O que conta como "sim" e como "não" numa flag vinda do JSON.
_FLAG_TRUE = {"true", "1", "yes", "on"}
_FLAG_FALSE = {"false", "0", "no", "off", ""}


def _as_flag(payload: dict[str, Any], *keys: str, field: str = "") -> bool:
    """Flag booleana do payload, no dialeto desta camada (levanta `PurchaseError`).

    O `bool()` cru aceita qualquer coisa e chama de verdade: `"false"` e `"não"`
    viram `True`, e `[]` vira `False`. Numa flag que decide se o custo vira o
    preferencial do insumo, isso é o tipo de "sim" que ninguém disse.

    Espelha `parsing.as_bool` da camada de API; o que muda é a exceção — a
    camada HTTP mapeia por TIPO (`services/exceptions.py`), e importar o parser
    do DRF aqui quebraria essa separação. Mesmo caminho que `services/catalog.py`
    seguiu com o seu `_as_flag`.
    """
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
        elif isinstance(value, str):
            text = value.strip().lower()
            if text in _FLAG_TRUE:
                return True
            if text in _FLAG_FALSE:
                return False
        raise PurchaseError(
            "Valor inválido para uma opção de sim/não.",
            code="flag_invalid",
            field=field or key,
        )
    return False


def parse_qty_input(raw: Any) -> Decimal | None:
    """Quantidade digitada pelo operador, no teclado da casa ou no do sistema.

    ``None`` é "não informado" — vazio, ilegível ou negativo. Quem chama decide
    se isso é omissão (linha em branco) ou erro (valor inválido); aqui não dá
    para saber a diferença.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        text = raw.strip().replace(" ", "")
        # Vírgula presente = notação pt-BR ("1.250,5"); sem vírgula, o ponto é decimal.
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
    else:
        text = str(raw)
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value < 0:
        return None
    return value.quantize(QTY_PLACES)


def parse_money_input(value: str, *, field: str = "costInput") -> int:
    """Dinheiro digitado → centavos. Vazio é zero; ILEGÍVEL é erro.

    ⚠️ A distinção é o achado. Um custo impossível de parsear virava `0` em
    silêncio, e o confirm simplesmente pulava o custo: digitar
    ``"12,50 (com frete)"`` gravava a entrada com custo ZERO e não dizia nada.
    Isso é falhar aberto em dinheiro — contra a régua explícita da casa.

    Vazio continua valendo zero de propósito: "não informei o custo" é uma resposta
    legítima do balcão, e é diferente de "escrevi algo que ninguém entende".
    """
    raw = value.strip().replace("R$", "").replace(" ", "")
    if not raw:
        return 0
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") == 1 and len(raw.rsplit(".", 1)[1]) <= 2:
        normalized = raw
    else:
        normalized = raw.replace(".", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise PurchaseError(
            f"Não entendi o valor {value.strip()!r}. Escreva só o número, como 12,50.",
            code="money_input_invalid",
            field=field,
        ) from exc
    if amount < 0:
        raise PurchaseError(
            "O valor não pode ser negativo.",
            code="money_input_negative",
            field=field,
        )
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _resolve_receipt_line(raw: dict[str, Any], *, index: int, supplier) -> ResolvedReceiptLine:
    Material = apps.get_model("buyman", "Material")

    if not isinstance(raw, dict):
        raise PurchaseError("Item de recebimento inválido.", code="receipt_line_invalid", field=f"lines.{index}")
    if not raw.get("checked"):
        raise PurchaseError(
            "Todos os itens precisam ser conferidos antes da entrada.",
            code="receipt_line_unchecked",
            field=f"lines.{index}.checked",
        )

    material_sku = str(raw.get("materialSku") or raw.get("material_sku") or "").strip()
    material = Material.objects.filter(sku=material_sku).first()
    if not material:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field=f"lines.{index}.materialSku")
    if not material.is_active:
        raise PurchaseError("Insumo inativo não pode receber entrada.", code="material_inactive", field=f"lines.{index}.materialSku")

    purchase_qty = _decimal(raw.get("purchaseQty", raw.get("purchase_qty")))
    if purchase_qty <= 0:
        raise PurchaseError(
            "Quantidade recebida precisa ser maior que zero.",
            code="quantity_invalid",
            field=f"lines.{index}.purchaseQty",
        )

    conversion = _resolve_conversion(
        raw.get("conversionId") or raw.get("conversion_id"),
        material=material,
        supplier=supplier,
        field=f"lines.{index}.conversionId",
    )
    if bool(raw.get("requiresConversion") or raw.get("requires_conversion")) and conversion is None:
        raise PurchaseError(
            "Defina a conversão da unidade de compra antes de confirmar a entrada.",
            code="conversion_required",
            field=f"lines.{index}.conversionId",
        )
    factor = Decimal(conversion.to_base_factor) if conversion else Decimal("1")
    base_qty = purchase_qty * factor

    expiry_raw = str(raw.get("expiryDate") or raw.get("expiry_date") or "").strip()
    expiry_date = parse_date(expiry_raw) if expiry_raw else None
    if expiry_raw and expiry_date is None:
        raise PurchaseError("Validade inválida.", code="expiry_invalid", field=f"lines.{index}.expiryDate")
    if material.shelf_life_days is not None and expiry_date is None:
        raise PurchaseError(
            "Insumo perecível precisa de validade para rastrear lote.",
            code="expiry_required",
            field=f"lines.{index}.expiryDate",
        )

    total_cost_q = parse_money_input(str(raw.get("costInput") or raw.get("cost_input") or ""))
    unit_cost_q = 0
    if total_cost_q > 0:
        unit_cost_q = int((Decimal(total_cost_q) / purchase_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    note = str(raw.get("lineNote") or raw.get("line_note") or raw.get("note") or "").strip()

    return ResolvedReceiptLine(
        line_id=str(raw.get("id") or f"line-{index + 1}"),
        material=material,
        conversion=conversion,
        purchase_qty=purchase_qty,
        base_qty=base_qty,
        total_cost_q=total_cost_q,
        unit_cost_q=unit_cost_q,
        expiry_date=expiry_date,
        note=note,
        invoice_product_code=str(raw.get("invoiceProductCode") or raw.get("invoice_product_code") or "").strip(),
        invoice_lot=str(raw.get("invoiceLot") or raw.get("invoice_lot") or "").strip(),
        checked=True,
    )


def _resolve_conversion(raw_id: Any, *, material, supplier, field: str):
    if raw_id in (None, "", "null"):
        return None
    MaterialConversion = apps.get_model("buyman", "MaterialConversion")
    try:
        conversion_id = int(raw_id)
    except (TypeError, ValueError):
        raise PurchaseError("Conversão inválida.", code="conversion_invalid", field=field) from None
    conversion = MaterialConversion.objects.filter(pk=conversion_id).select_related("material", "supplier").first()
    if not conversion:
        raise PurchaseError("Conversão não encontrada.", code="conversion_not_found", field=field)
    if conversion.material_id != material.pk:
        raise PurchaseError(
            "Conversão pertence a outro insumo.",
            code="conversion_material_mismatch",
            field=field,
        )
    if conversion.supplier_id and conversion.supplier_id != supplier.pk:
        raise PurchaseError(
            "Conversão pertence a outro fornecedor.",
            code="conversion_supplier_mismatch",
            field=field,
        )
    if not conversion.is_active:
        raise PurchaseError("Conversão inativa.", code="conversion_inactive", field=field)
    return conversion


def _conversion_from_invoice_axes(payload: dict[str, Any], *, material):
    """Deriva rótulo e fator do par da NF, quando o gesto mandou o par."""
    if payload.get("factor") and payload.get("label"):
        return None
    quantity = _decimal(payload.get("invoiceQty") or payload.get("invoice_qty"))
    tax_quantity = _decimal(payload.get("invoiceTaxQty") or payload.get("invoice_tax_qty"))
    unit = str(payload.get("invoiceUnit") or payload.get("invoice_unit") or "").strip()
    tax_unit = str(payload.get("invoiceTaxUnit") or payload.get("invoice_tax_unit") or "").strip()
    if quantity <= 0 or not unit:
        return None
    from shopman.shop.adapters.purchase_invoice_nfe import conversion_from_invoice_axes

    return conversion_from_invoice_axes(
        material=material,
        quantity=quantity,
        unit=unit,
        tax_quantity=tax_quantity,
        tax_unit=tax_unit,
        name=str(payload.get("invoiceDescription") or payload.get("invoice_description") or ""),
    )


def _converted_via(line: ResolvedReceiptLine) -> dict[str, Any]:
    """O carimbo da ponte que a quantidade atravessou — ou nada, se não houve ponte.

    ``Move.metadata["converted_via"]`` é o que a Fase 5 do UNIT-CONVERSION-PLAN
    pede, e existe para uma pergunta poder ser feita depois: *este saldo foi
    medido ou foi convertido?* Sem o carimbo, 5 kg que vieram de "10 pacotes ≈
    500 g" ficam indistinguíveis de 5 kg pesados na balança — que é exatamente o
    que a R3 da ADR-024 proíbe ("some o ``≈``, some a informação").

    As três chaves viajam JUNTAS, num objeto só, porque separadas elas podiam
    aparecer pela metade: rótulo sem fator não permite refazer a conta, e fator
    sem o ``approximate`` não diz se a conta era exata. Entrada na própria
    unidade-base não carimba nada — não houve conversão para registrar, e uma
    chave com ``null`` fingiria que houve.
    """
    if line.conversion is None:
        return {}
    return {
        "converted_via": {
            "label": line.conversion.label,
            "factor": str(line.conversion.to_base_factor),
            "approximate": bool(line.conversion.is_approximate),
        }
    }


def _upsert_supplier_cost(*, material, supplier, conversion, cost_q: int, make_preferred: bool, prefer_if_missing: bool = False) -> None:
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
    preferred_exists = SupplierMaterialCost.objects.filter(material=material, is_preferred=True).exists()
    should_prefer = make_preferred or (prefer_if_missing and not preferred_exists)
    cost = SupplierMaterialCost.objects.filter(material=material, supplier=supplier).first()
    if cost is None:
        cost = SupplierMaterialCost(material=material, supplier=supplier)
    cost.conversion = conversion
    cost.cost_q = cost_q
    if should_prefer or cost.is_preferred:
        cost.is_preferred = True
    try:
        cost.full_clean()
        cost.save()
    except ValidationError as exc:
        raise PurchaseError(str(exc), code="cost_validation_failed", field="costInput") from exc


def _learn_invoice_product_map(*, supplier, lines: list[ResolvedReceiptLine]) -> None:
    """Persist operator-confirmed NF line → material pairs on the supplier.

    The scan adapter resolves future invoices from
    ``Supplier.metadata.purchase.invoice_product_map`` (see
    docs/reference/data-schemas.md); confirming a receipt is the only writer.
    A divergent existing entry is replaced — the operator's confirmation is the
    freshest truth — but never silently: the swap goes to the structured log.
    """
    learned = {
        line.invoice_product_code: {
            "materialSku": line.material.sku,
            "conversionLabel": line.conversion.label if line.conversion else "",
        }
        for line in lines
        if line.invoice_product_code
    }
    if not learned:
        return

    metadata = dict(supplier.metadata or {})
    purchase = dict(metadata.get("purchase") or {})
    mapping = dict(_current_invoice_product_map(metadata, purchase))
    changed = False
    for code, entry in learned.items():
        current = mapping.get(code)
        if current == entry:
            continue
        current_sku = _mapped_material_sku(current)
        if current_sku and current_sku != entry["materialSku"]:
            logger.warning(
                "purchase.invoice_product_map_overwrite",
                extra={
                    "supplier": supplier.ref,
                    "invoice_product_code": code,
                    "old_material": current_sku,
                    "new_material": entry["materialSku"],
                },
            )
        mapping[code] = entry
        changed = True
    if not changed:
        return

    purchase["invoice_product_map"] = mapping
    metadata["purchase"] = purchase
    supplier.metadata = metadata
    supplier.save(update_fields=["metadata", "updated_at"])


def _current_invoice_product_map(metadata: dict[str, Any], purchase: dict[str, Any]) -> dict[str, Any]:
    # Mesma ordem de resolução do adapter (escopo purchase antes da raiz,
    # aliases em INVOICE_PRODUCT_MAP_KEYS): aprender por cima do mapa que o
    # scan realmente lê, senão um mapa manual sob alias ficaria sombreado.
    for scope in (purchase, metadata):
        for key in INVOICE_PRODUCT_MAP_KEYS:
            value = scope.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _mapped_material_sku(entry: Any) -> str:
    if isinstance(entry, str | int):
        return str(entry).strip()
    if isinstance(entry, dict):
        for key in ("materialSku", "material_sku", "sku", "material"):
            if entry.get(key):
                return str(entry[key]).strip()
    return ""


def _default_receive_position():
    Position = apps.get_model("stockman", "Position")
    return (
        Position.objects.filter(is_default=True).first()
        or Position.objects.filter(kind="physical").order_by("ref").first()
        or Position.objects.order_by("ref").first()
    )


def _invoice_reader_draft(*, access_key: str, qr_payload: str) -> dict[str, Any]:
    path = (getattr(settings, "SHOPMAN_PURCHASE_INVOICE_READER", "") or "").strip()
    if not path:
        return {}
    try:
        reader = import_string(path)
        draft = reader(access_key=access_key, qr_payload=qr_payload)
        return dict(draft or {})
    except Exception:
        logger.warning("purchase.invoice_reader_failed path=%s", path, exc_info=True)
        return {}


_SUPPLIER_REF_STOPWORDS = {
    "ATACADISTA", "ATACADO", "ALIMENTICIO", "ALIMENTICIOS", "ALIMENTOS", "CIA", "COMERCIAL",
    "COMERCIO", "DA", "DAS", "DE", "DISTRIBUICAO", "DISTRIBUIDORA", "DO", "DOS", "E", "EIRELI",
    "EM", "EPP", "EXPORTACAO", "IMPORTACAO", "INDUSTRIA", "INDUSTRIAL", "LTDA", "ME", "MEI",
    "PRODUTO", "PRODUTOS", "SA", "VAREJO",
}


def _supplier_name_key(name: str) -> str:
    """Reduz uma razão social ao núcleo que identifica a empresa.

    ``ESPACO GASTRONOMICO IMPORTADORA LTDA`` e ``Espaço Gastronômico`` são a
    mesma casa escrita de dois jeitos: a NF traz a razão social completa, o
    cadastro do dono traz o nome de boca. Tirar acento, caixa, pontuação e as
    palavras de forma jurídica (LTDA, ME, COMERCIO…) faz as duas colapsarem na
    mesma chave.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", ascii_name.upper()) if token]
    core = [token for token in tokens if token not in _SUPPLIER_REF_STOPWORDS] or tokens
    return "-".join(core[:2])[:40].strip("-")


def _supplier_ref_from_name(name: str) -> str:
    """Ref limpo, minúsculo, sem prefixo de tipo — o padrão da casa.

    O tipo já mora no lugar certo (a tabela, o ref_type do registro); `SUP-` era
    ruído de ERP, e o dono normalizou os 4 que nasceram assim (01/09/2026).
    """
    slug = _supplier_name_key(name)
    return slug.lower() if slug else ""


def _adopt_supplier_by_name(issuer_names: list[str], document_text: str, phone: str) -> str:
    """Encontra um fornecedor JÁ cadastrado, ainda sem CNPJ, que seja este emitente.

    Sem isto, o primeiro escaneamento de NF de um fornecedor que o dono já
    cadastrou pelo nome cria um segundo cadastro para a mesma empresa, e o
    histórico de custo nasce partido em dois. O casamento por CNPJ (acima) não
    alcança esse caso justamente porque o cadastro do dono não tem CNPJ.

    Só adota quem tem ``document`` VAZIO — nunca sobrescreve um CNPJ já
    conhecido — e só quando a chave de nome aponta para UM único candidato:
    empate é ambiguidade, e ambiguidade cadastra novo em vez de adivinhar.
    """
    Supplier = apps.get_model("buyman", "Supplier")
    chaves = {_supplier_name_key(n) for n in issuer_names if n}
    chaves.discard("")
    if not chaves:
        return ""
    candidatos = [
        supplier
        for supplier in Supplier.objects.filter(is_active=True).only("ref", "name", "document", "phone", "metadata")
        if not re.sub(r"\D", "", supplier.document or "") and _supplier_name_key(supplier.name) in chaves
    ]
    if len(candidatos) != 1:
        return ""
    supplier = candidatos[0]
    supplier.document = document_text
    if phone and not (supplier.phone or "").strip():
        supplier.phone = phone
    metadata = dict(supplier.metadata or {})
    purchase = dict(metadata.get("purchase") or {})
    purchase["document_learned_from"] = "nfe_scan"
    metadata["purchase"] = purchase
    supplier.metadata = metadata
    supplier.save(update_fields=["document", "phone", "metadata", "updated_at"])
    logger.info(
        "purchase.supplier_adopted_by_name ref=%s document=%s", supplier.ref, document_text
    )
    return supplier.ref


def _register_supplier_from_issuer(issuer: dict[str, Any]) -> tuple[str, bool]:
    """Resolve (ou cadastre) o fornecedor pelo emitente da NF. Retorna (ref, criado)."""
    Supplier = apps.get_model("buyman", "Supplier")
    document = re.sub(r"\D", "", str(issuer.get("document") or ""))
    name = str(issuer.get("name") or "").strip()
    if not document or not name:
        return "", False
    for supplier in Supplier.objects.all().only("ref", "document"):
        if re.sub(r"\D", "", supplier.document or "") == document:
            return supplier.ref, False
    trade_name = str(issuer.get("tradeName") or "").strip()
    phone = str(issuer.get("phone") or "").strip()[:32]
    document_text = (
        f"{document[0:2]}.{document[2:5]}.{document[5:8]}/{document[8:12]}-{document[12:14]}"
        if len(document) == 14
        else document
    )
    adotado = _adopt_supplier_by_name([trade_name, name], document_text, phone)
    if adotado:
        return adotado, False
    base = _supplier_ref_from_name(trade_name or name)
    if not base:
        return "", False
    ref = base
    suffix = 2
    while Supplier.objects.filter(ref=ref).exists():
        ref = f"{base}-{suffix}"
        suffix += 1
    Supplier.objects.create(
        ref=ref,
        name=name,
        document=document_text,
        phone=phone,
        metadata={"purchase": {"created_from": "nfe_scan"}},
    )
    logger.info("purchase.supplier_autocreated ref=%s document=%s", ref, document)
    return ref, True


def _require_supplier_is_issuer(*, supplier, invoice_key: str) -> None:
    """O fornecedor escolhido tem de ser quem EMITIU a nota.

    O confirm validava a chave e validava que o fornecedor existe e está ativo —
    mas nunca cruzava os dois. Os 14 dígitos do CNPJ do emitente estão DENTRO da
    própria chave, e o código já sabia disso (`_supplier_ref_from_invoice_key`).

    No chão: o scan preenche o fornecedor certo, e o que volta no confirm é o do
    dropdown, que o operador pode ter trocado sem perceber ao navegar entre abas. O
    resultado é movimento com fornecedor errado, custo no fornecedor errado e — o
    pior — o de-para fiscal aprendido NO FORNECEDOR ERRADO, envenenando o scan de
    todas as notas futuras daquele fornecedor. O overwrite loga um aviso; o
    aprendizado inicial não loga nada.

    ⚠️ Fornecedor SEM documento cadastrado não é recusado: recusar quebraria
    entrada legítima por causa de cadastro incompleto, e a nota não fica melhor
    guardada por isso. É o único caso em que a checagem se cala — e ela se cala
    dizendo por quê no log, não em silêncio.
    """
    chave = parse_invoice_access_key(invoice_key) or ""
    if not chave:
        return
    emitente = chave[6:20]
    documento = re.sub(r"\D", "", getattr(supplier, "document", "") or "")
    if not documento:
        logger.info(
            "purchase.issuer_check_skipped supplier=%s reason=sem_documento", supplier.ref
        )
        return
    if documento != emitente:
        raise PurchaseError(
            "O fornecedor selecionado não é quem emitiu esta nota. "
            "Confira o fornecedor antes de dar entrada.",
            code="supplier_not_issuer",
            field="supplierRef",
        )


def _supplier_ref_from_invoice_key(access_key: str) -> str:
    Supplier = apps.get_model("buyman", "Supplier")
    issuer_cnpj = access_key[6:20]
    for supplier in Supplier.objects.filter(is_active=True).only("ref", "document"):
        if re.sub(r"\D", "", supplier.document or "") == issuer_cnpj:
            return supplier.ref
    return ""


def _invoice_key_candidates(raw: str) -> list[str]:
    text = str(raw or "")
    candidates: list[str] = []
    parsed = urlparse(text)
    if parsed.query:
        for value in parse_qs(parsed.query).get("p", []):
            candidates.extend(re.findall(r"\d{44}", re.sub(r"\D", "", value)))
    candidates.extend(re.findall(r"\d{44}", re.sub(r"\D", "", text)))
    return list(dict.fromkeys(candidates))


def _valid_invoice_key(key: str) -> bool:
    if not re.fullmatch(r"\d{44}", key):
        return False
    weights = []
    weight = 2
    for _ in range(43):
        weights.append(weight)
        weight = 2 if weight == 9 else weight + 1
    total = sum(int(digit) * weight for digit, weight in zip(reversed(key[:43]), weights, strict=True))
    remainder = total % 11
    check_digit = 0 if remainder in (0, 1) else 11 - remainder
    return check_digit == int(key[-1])


def _receipt_reason(*, mode: str, source_ref: str) -> str:
    prefix = "Compra NF" if mode == "invoice" else "Compra sem NF"
    return f"{prefix} {source_ref[-12:]}"


def _receipt_batch_note(*, receipt_note: str, line_note: str) -> str:
    return "\n".join(note for note in (receipt_note, line_note) if note)


def _receipt_rejection_ref(*, source_ref: str, supplier_ref: str) -> str:
    digest = hashlib.sha1(f"{source_ref}:{supplier_ref}".encode()).hexdigest()[:6].upper()
    return f"DEV-{timezone.localdate():%y%m%d}-{digest}"


def _receipt_rejection_dedupe_key(*, source_ref: str, supplier_ref: str, reason: str, lines_text: str) -> str:
    digest = hashlib.sha1(f"{source_ref}:{supplier_ref}:{reason}:{lines_text}".encode()).hexdigest()[:16]
    return f"purchase.receipt_rejected:{supplier_ref[:32]}:{digest}"[:128]


def _receipt_rejection_lines(raw_lines: list[Any]) -> str:
    Material = apps.get_model("buyman", "Material")
    rows: list[str] = []
    material_names = {
        item.sku: item.name
        for item in Material.objects.filter(
            sku__in=[str(line.get("materialSku") or line.get("material_sku") or "") for line in raw_lines if isinstance(line, dict)]
        ).only("sku", "name")
    }
    for raw in raw_lines:
        if not isinstance(raw, dict):
            continue
        sku = str(raw.get("materialSku") or raw.get("material_sku") or "").strip()
        qty = str(raw.get("purchaseQty") or raw.get("purchase_qty") or "").strip()
        note = str(raw.get("lineNote") or raw.get("line_note") or "").strip()
        label = material_names.get(sku, sku or "item")
        suffix = f" — {note}" if note else ""
        rows.append(f"- {label}: {qty or '?'}{suffix}")
    return "\n".join(rows)


def _manual_source_ref(*, supplier_ref: str, note: str, lines: list | None = None) -> str:
    """A identidade de uma entrada SEM nota — derivada do conteúdo, não do relógio.

    ⚠️ Isto carregava `timezone.now()` no seed, então a mesma entrada gerava um ref
    diferente a cada chamada. Servia para nomear um lote; NÃO serve para responder
    "essa entrada já foi feita?", que é o que a trava de recibo precisa perguntar.

    Com o conteúdo no seed, dois envios do mesmo recebimento colidem — que é o
    ponto. Duas entradas legitimamente iguais no mesmo dia (o fornecedor voltou com
    outra remessa idêntica) também colidem: é o preço, e é o lado seguro do erro.
    Quem precisa registrar a segunda declara a diferença na observação.
    """
    corpo = ""
    if lines:
        corpo = "|".join(
            f"{line.material.sku}:{line.purchase_qty}:{line.total_cost_q}" for line in lines
        )
    seed = f"{supplier_ref}:{note}:{corpo}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"MANUAL-{digest}"


def _batch_ref(*, source_ref: str, line: ResolvedReceiptLine) -> str:
    """A referência do lote — a do FORNECEDOR quando a nota informa.

    Num recall, quem chama o lote é quem fabricou: o aviso diz "lote L2408A",
    não o código que a nossa entrada inventou. Guardar o número da nota é o que
    torna a pergunta "esse lote entrou aqui?" respondível em segundos.

    O SKU entra na frente porque o número do fornecedor só é único dentro do
    produto dele: dois insumos diferentes podem chegar com "L2408A" no mesmo
    dia, e o lote é chave global no Stockman. Sem lote na nota — o caso comum,
    porque ``rastro`` é opcional — vale o código derivado de sempre.
    """
    sku = re.sub(r"[^A-Z0-9]+", "", line.material.sku.upper())[:18] or "SKU"
    if line.invoice_lot:
        lot = re.sub(r"[^A-Z0-9]+", "", line.invoice_lot.upper())[:20]
        if lot:
            return f"{sku}-L{lot}"[:50]
    source = re.sub(r"[^A-Z0-9]+", "", source_ref.upper())[-10:] or "REC"
    seed = f"{source_ref}:{line.line_id}:{line.material.sku}:{line.expiry_date}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"BUY-{source}-{sku}-{digest}"[:50]


def _decimal(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw).replace(",", "."))
    except InvalidOperation:
        return Decimal("0")
