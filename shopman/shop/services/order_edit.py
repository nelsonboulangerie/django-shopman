"""Editar a encomenda no próprio pedido: itens, observação, recebimento e data.

Decisões do dono (26–28/09/2026, ``docs/plans/ENCOMENDAS-PDV-PLAN.md``, WP-E6):

- a edição acontece NO PRÓPRIO PEDIDO — mesmo ref, mesmo pagamento, mesmo
  acompanhamento. Só a NFC-e autorizada fecha a porta: aí o caminho é cancelar e
  refazer (corrigir nota é outro documento fiscal, não um ajuste);
- diferença a MAIS vira saldo a receber (``payment.balance_due_q`` lê o total
  efetivo; o balcão recebe no "Receber e entregar", o entregador na porta);
- diferença a MENOS com dinheiro recebido volta pelo MESMO meio: cartão online e
  Pix pelo gateway (estorno parcial), dinheiro pela gaveta
  (``payment.pending_cash_refunds``, no *Precisa de você*), maquininha do balcão
  por uma pendência guiada (``payment.pending_card_machine_refunds``) em que o
  operador estorna na maquininha e registra. Meio que não sabe devolver parte
  (conta da casa, cobrança digital ainda aberta, pagamento em mais de um meio)
  RECUSA a redução com o motivo — nunca devolve em outro meio calado;
- trocar retirada ↔ entrega entra: a taxa de entrega é linha do ajuste, pelo
  MESMO motor da venda (``pos.resolve_delivery_fee``), e a entrega com nota
  exige o CPF/CNPJ e o endereço completo como na venda
  (``delivery_fiscal_identity``, decisão de 24/09);
- trocar a data/janela vai pelo reagendar que já existe (``reschedule``), na
  MESMA transação: se ele recusar, nada muda;
- o cliente é avisado do que mudou, do total novo e do destino da diferença
  (``order_updated``, texto em ``notification_copy``), numa mensagem só.

Como
----

O Core não edita ``Order`` (``snapshot``/``total_q`` são selados). O mecanismo
é o de "pedido + ajustes": ``order_composition.record`` grava a lista FINAL de
itens em ``order.data["adjustment"]``, e todo leitor de item/total lê a
composição. :func:`apply_final_items` é o caminho único de gravar o ajuste e
trazer estoque e cozinha junto — o ``ORDER_PATCHED`` do iFood passa por ele
também, com o gate de estoque brando (lá o cliente já mudou do lado de lá).

Preço: o item que já estava mantém o preço vendido; o que entra (item novo ou
quantidade a mais) sai pelo preço do catálogo NO CANAL DO PEDIDO
(``OffermanPricingBackend``, a mesma cascata da venda: faixa do cliente →
listing do canal → preço base). Quantidade a mais com o preço igual ao vendido
soma na mesma linha; com preço diferente vira linha própria, para o "antes" e o
"depois" não mentirem. Descontos NÃO são recalculados: nenhuma regra
promocional nova entra por uma edição, e o total novo é o total vigente mais a
diferença das linhas que mudaram.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.db import transaction
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money, monetary_mult

from shopman.shop import product_options
from shopman.shop.services import fiscal as fiscal_service
from shopman.shop.services import order_composition, weighed_sale

logger = logging.getLogger(__name__)

SOURCE = "pos:edit"
EVENT_TYPE = "order_edited"
CUSTOMER_NOTICE_TEMPLATE = "order_updated"
NOTES_MAX_LENGTH = 500
DELIVERY_FEE_SKU = "__DELIVERY_FEE__"

#: O que ainda se edita: a mercadoria não ficou pronta.
EDITABLE_STATUSES = frozenset({Order.Status.NEW.value, Order.Status.ACCEPTED.value, Order.Status.PREPARING.value})

_REFUSED_STATUSES = {
    Order.Status.READY.value: "já está pronta",
    Order.Status.DISPATCHED.value: "já saiu para entrega",
    Order.Status.DELIVERED.value: "já foi entregue",
    Order.Status.COMPLETED.value: "já foi concluída",
    Order.Status.CANCELLED.value: "foi cancelada",
    Order.Status.RETURNED.value: "foi devolvida",
}

#: Enquanto o pedido está num destes, a mercadoria ainda está na casa e mexer em
#: estoque e cozinha é mexer em coisa que existe. Depois que ele saiu
#: (despachado, entregue) o pão foi junto com o entregador: creditar o estoque de
#: volta inventaria pão que não está na prateleira. O AJUSTE continua valendo —
#: o Gestor, as vias e o B.I. passam a mostrar o que a plataforma vai pagar —,
#: mas o físico não se desfaz por evento.
#:
#: O conjunto mora em ``services.fiscal`` porque a mesma saída da mercadoria é a
#: segunda condição do art. 35 do RICMS/PR para cancelar a NFC-e. Um fato
#: físico, dois leitores — não dois conjuntos que um dia divergem.
GOODS_STILL_IN_THE_HOUSE = fiscal_service.GOODS_NOT_DISPATCHED

# ── Como a diferença de valor se resolve ─────────────────────────────────────

#: Nada a receber nem a devolver.
SETTLE_NONE = "none"
#: Falta receber (``amount_q`` = o saldo novo), na retirada ou na entrega.
SETTLE_COLLECT = "collect"
#: Estorno parcial pelo gateway (cartão online no Stripe, Pix na Efí).
SETTLE_REFUND_GATEWAY = "refund_gateway"
#: Devolução em dinheiro pela gaveta — pendência no *Precisa de você*.
SETTLE_REFUND_CASH = "refund_cash"
#: Estorno na maquininha do balcão — pendência guiada, registrada pelo operador.
SETTLE_REFUND_CARD_MACHINE = "refund_card_machine"

REFUND_KINDS = frozenset({SETTLE_REFUND_GATEWAY, SETTLE_REFUND_CASH, SETTLE_REFUND_CARD_MACHINE})

ROUTE_CASH = "cash"
ROUTE_GATEWAY = "gateway"
ROUTE_CARD_MACHINE = "card_machine"
ROUTE_ACCOUNT = "account"

_CARD_MACHINE_METHODS = frozenset({"credit", "debit", "external"})
_COUNTER_METHODS = frozenset({"cash", "credit", "debit"})


class EditRefused(ValueError):
    """A edição não pode ser feita. Nada foi alterado.

    ``field`` aponta a entrada da tela (``items.<n>``, ``notes``,
    ``fulfillment.<campo>``, ``date``/``slot``) quando a recusa é sobre ela;
    vazio quando é sobre o pedido.
    """

    def __init__(self, message: str, *, code: str, field: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


@dataclass(frozen=True)
class Settlement:
    kind: str
    amount_q: int = 0
    #: O meio do pagamento que recebe a devolução ("card", "pix", "cash",
    #: "credit", "debit", "external"); vazio quando não há devolução.
    method: str = ""


@dataclass(frozen=True)
class EditPlan:
    """O que a edição faria — a prévia que a tela mostra ANTES de confirmar."""

    changed: bool
    items_changed: bool
    items: list[dict]
    previous_total_q: int
    total_q: int
    difference_q: int
    diff: dict
    notes_before: str
    notes_after: str
    notes_changed: bool
    fulfillment_before: str
    fulfillment_after: str
    fulfillment_changed: bool
    delivery_address_after: str
    delivery_fee_before_q: int
    delivery_fee_after_q: int
    schedule_changed: bool
    date_after: str
    slot_after: str
    settlement: Settlement
    balance_before_q: int
    balance_after_q: int
    requires_manager_approval: bool
    customer_note: str = ""
    new_line_ids: tuple[str, ...] = ()
    #: Chaves de ``Order.data`` que a edição reescreve (``None`` = remover).
    data_updates: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EditResult:
    plan: EditPlan
    revision: int | None
    stock: dict | None = None


# ── O caminho comum (iFood e balcão) ─────────────────────────────────────────


def apply_final_items(
    order,
    *,
    items: list[dict],
    total_q: int,
    source: str,
    event_id: str,
    stock_reference: str,
    require_stock: bool = False,
) -> dict:
    """Grava o ajuste e traz estoque e cozinha para a lista nova.

    Chamada com o pedido travado, dentro da transação do chamador: se o estoque
    recusar no meio (``require_stock=True``), a exceção desfaz o ajuste e as
    reservas juntos. Devolve ``{revision, total_q, previous_total_q, diff,
    stock, kds}``.
    """
    from shopman.shop.services import kds as kds_service
    from shopman.shop.services import stock

    before = order_composition.effective_items(order)
    previous_total_q = order_composition.effective_total_q(order)
    previous_lines = kds_service.order_lines(order)

    adjustment = order_composition.record(
        order, items=items, total_q=total_q, source=source, event_id=event_id,
    )
    data = dict(order.data or {})
    data[order_composition.KEY] = adjustment
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    difference = order_composition.diff(before, order_composition.effective_items(order))
    outcome = {
        "revision": adjustment["revision"],
        "total_q": total_q,
        "previous_total_q": previous_total_q,
        "diff": difference,
    }
    if order.status in GOODS_STILL_IN_THE_HOUSE:
        outcome["stock"] = stock.reconcile_to_items(
            order, items=items, reference=stock_reference, require_all=require_stock,
        )
        outcome["kds"] = kds_service.reconcile_to_lines(order, previous_lines=previous_lines)
    else:
        # A mercadoria já saiu com o entregador. O ajuste vale, o físico não se
        # desfaz por evento.
        outcome["stock"] = {"skipped": "goods_left"}
        outcome["kds"] = {"skipped": "goods_left"}
    return outcome


# ── Portas ───────────────────────────────────────────────────────────────────


def fiscal_authorized(order) -> bool:
    """A NFC-e deste pedido está autorizada e viva?"""
    data = order.data or {}
    return bool(data.get("nfce_access_key")) and not data.get("nfce_cancelled")


def state_refusal(order) -> tuple[str, str]:
    """``(code, frase)`` de por que esta encomenda não se edita — ou ``("", "")``.

    A mesma régua de :func:`edit`, para a tela decidir se oferece o gesto. A
    nota autorizada tem código próprio (``fiscal_authorized``): ali a tela
    troca "Editar" por "Cancelar e refazer".
    """
    from shopman.shop.services.order_helpers import is_test_order

    label = _REFUSED_STATUSES.get(str(order.status))
    if label:
        return "order_not_editable", f"Esta encomenda {label}: não dá mais para editar."
    if order.channel_ref == "ifood":
        return "marketplace_order", "Pedido do iFood: a alteração é feita pelo cliente no iFood."
    if is_test_order(order):
        return "test_order", "Pedido de teste do marketplace não se edita."
    if fiscal_authorized(order):
        return (
            "fiscal_authorized",
            "A NFC-e desta encomenda já foi autorizada: para mudar, cancele e refaça a encomenda.",
        )
    if str(order.status) not in EDITABLE_STATUSES:
        return "order_not_editable", "Esta encomenda não pode ser editada neste estado."
    return "", ""


# ── Prévia ───────────────────────────────────────────────────────────────────


def plan(order, *, lines=None, notes=None, fulfillment=None, schedule=None) -> EditPlan:
    """Calcula a edição sem gravar nada: itens, total, diferença e o destino dela.

    - ``lines``: a lista FINAL de itens de produto, ``[{line_id?, sku, qty,
      weighed?}]``. ``line_id`` de uma linha que já existia mantém o preço
      vendido; sem ``line_id`` (ou desconhecido) é item novo, a preço de
      catálogo. O item vendido por peso entra como na venda: ``weighed`` traz a
      etiqueta (``{entry: "label", label_q}``) ou o peso (``{entry: "weight",
      weight_g}``), e cada peça é uma linha; a peça que já estava não muda de
      peso. ``None`` mantém os itens como estão.
    - ``notes``: a observação do cliente (``order_notes``); ``None`` mantém.
    - ``fulfillment``: ``{type: "pickup"|"delivery", delivery_address,
      delivery_address_structured, delivery_fee_override_q, fiscal_tax_id,
      delivery_payment_method}``; ``None`` mantém.
    - ``schedule``: ``{date, slot}``; ``None`` mantém.
    """
    code, message = state_refusal(order)
    if code:
        raise EditRefused(message, code=code)

    data = order.data or {}
    current = order_composition.effective_items(order)
    fee_lines = [item for item in current if _is_fee_line(item)]
    other_fixed = [item for item in current if _is_fixed_line(item) and not _is_fee_line(item)]
    editable = [item for item in current if not _is_fixed_line(item)]
    next_revision = int((order_composition.adjustment(order) or {}).get("revision") or 0) + 1

    # ── produtos
    new_line_ids: list[str] = []
    if lines is None:
        products = [_kept(item, item.qty) for item in editable]
    else:
        products = _products_from_lines(order, lines, editable, next_revision, new_line_ids)
    products_q = sum(int(line["line_total_q"]) for line in products)

    # ── recebimento (e a taxa de entrega, que é linha)
    fulfillment_before = "delivery" if str(data.get("fulfillment_type") or "") == "delivery" else "pickup"
    fee_before_q = sum(item.line_total_q for item in fee_lines)
    receiving = _receiving(order, fulfillment, fulfillment_before, fee_lines, products_q, next_revision)

    items_payload = (
        [_payload(line) for line in products]
        + [order_composition.as_payload(item) for item in other_fixed]
        + receiving["fee_lines"]
    )
    previous_total_q = order_composition.effective_total_q(order)
    old_lines_q = sum(item.line_total_q for item in editable) + fee_before_q
    new_lines_q = products_q + sum(int(line["line_total_q"]) for line in receiving["fee_lines"])
    total_q = previous_total_q - old_lines_q + new_lines_q

    after = [order_composition._item_from_payload(payload) for payload in items_payload]
    difference = order_composition.diff(current, after)
    items_changed = (
        not order_composition.is_empty(difference)
        or total_q != previous_total_q
        or [(i.line_id, i.line_total_q) for i in current] != [(i.line_id, i.line_total_q) for i in after]
    )

    # ── observação
    notes_before = str(data.get("order_notes") or "").strip()
    notes_after = notes_before if notes is None else str(notes).strip()
    if len(notes_after) > NOTES_MAX_LENGTH:
        raise EditRefused(
            f"Observação longa demais (máximo {NOTES_MAX_LENGTH} caracteres).", code="notes_too_long", field="notes",
        )
    notes_changed = notes_after != notes_before

    # ── data/janela (a régua é a do reagendar)
    schedule_changed, date_after, slot_after = _schedule(order, schedule)

    # ── dinheiro
    settlement, balance_before_q, balance_after_q, intents = _settlement(
        order, previous_total_q=previous_total_q, total_q=total_q,
    )
    data_updates = dict(receiving["data_updates"])
    if notes_changed:
        data_updates["order_notes"] = notes_after or None
    payment_after = _payment_after(
        order,
        total_q=total_q,
        settlement=settlement,
        balance_after_q=balance_after_q,
        fulfillment_after=receiving["type"],
        delivery_payment_method=str((fulfillment or {}).get("delivery_payment_method") or "").strip().lower(),
        intents=intents,
    )
    if payment_after is not None:
        data_updates["payment"] = payment_after

    if receiving["type"] == "delivery" and (receiving["changed"] or items_changed):
        _require_delivery_identity(order, data_updates, total_q=total_q)

    result = EditPlan(
        changed=items_changed or notes_changed or receiving["changed"] or schedule_changed,
        items_changed=items_changed,
        items=items_payload,
        previous_total_q=previous_total_q,
        total_q=total_q,
        difference_q=total_q - previous_total_q,
        diff=difference,
        notes_before=notes_before,
        notes_after=notes_after,
        notes_changed=notes_changed,
        fulfillment_before=fulfillment_before,
        fulfillment_after=receiving["type"],
        fulfillment_changed=receiving["type"] != fulfillment_before,
        delivery_address_after=receiving["address"],
        delivery_fee_before_q=fee_before_q,
        delivery_fee_after_q=sum(int(line["line_total_q"]) for line in receiving["fee_lines"]),
        schedule_changed=schedule_changed,
        date_after=date_after,
        slot_after=slot_after,
        settlement=settlement,
        balance_before_q=balance_before_q,
        balance_after_q=balance_after_q,
        requires_manager_approval=settlement.kind in REFUND_KINDS,
        new_line_ids=tuple(new_line_ids),
        data_updates=data_updates if (items_changed or notes_changed or receiving["changed"]) else {},
    )
    return replace(result, customer_note=customer_note(result))


# ── Gravar ───────────────────────────────────────────────────────────────────


def edit(order, *, lines=None, notes=None, fulfillment=None, schedule=None, actor: str, approved_by=None) -> EditResult:
    """Aplica a edição sob o lock do pedido, numa transação.

    Estoque sem saldo, data recusada, porta fechada ou meio que não devolve
    parte: recusa e NADA muda. Redução com dinheiro recebido exige
    ``approved_by`` (o gerente que assinou, mesma régua do cancelamento de
    pedido pago). A mesma edição de novo não mexe em nada.
    """
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.services import reschedule as reschedule_service

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        result = plan(locked, lines=lines, notes=notes, fulfillment=fulfillment, schedule=schedule)
        if not result.changed:
            return EditResult(plan=result, revision=None)
        if result.requires_manager_approval and approved_by is None:
            raise EditRefused(
                "A encomenda paga ficou mais barata: um gerente precisa autorizar a devolução.",
                code="manager_approval_required",
            )

        # Recebimento, observação e pagamento primeiro: a reserva e a cozinha
        # que vêm depois leem o pedido como ele fica.
        if result.data_updates:
            data = dict(locked.data or {})
            for key, value in result.data_updates.items():
                if value is None:
                    data.pop(key, None)
                else:
                    data[key] = value
            locked.data = data
            locked.save(update_fields=["data", "updated_at"])

        revision = None
        stock_summary = None
        previous_skus = {item.sku for item in order_composition.effective_items(locked) if item.sku}
        if result.items_changed:
            try:
                outcome = apply_final_items(
                    locked,
                    items=result.items,
                    total_q=result.total_q,
                    source=SOURCE,
                    event_id=f"pos-edit:{locked.ref}:{_next_revision(locked)}",
                    stock_reference=f"pos_edit:{locked.ref}",
                    require_stock=True,
                )
            except ValidationError as exc:
                raise EditRefused(_stock_refusal(locked, exc, result.items), code=exc.code, field="items") from None
            revision = outcome["revision"]
            stock_summary = outcome.get("stock")

        if result.schedule_changed:
            try:
                reschedule_service.reschedule(
                    locked, date=result.date_after, slot=result.slot_after, actor=actor,
                    reason="edição da encomenda", notify=False,
                )
            except reschedule_service.RescheduleRefused as exc:
                raise EditRefused(exc.message, code=exc.code, field=exc.field or "date") from None
            locked.refresh_from_db()

        locked.emit_event(
            event_type=EVENT_TYPE,
            actor=actor,
            payload=_event_payload(result, revision=revision, approved_by=approved_by),
        )

        if result.settlement.kind == SETTLE_REFUND_GATEWAY:
            amount_q = result.settlement.amount_q
            key = f"order-edit:{locked.ref}:{revision or _edit_count(locked)}"
            ref = locked.ref
            transaction.on_commit(lambda: _refund_gateway(ref, amount_q=amount_q, idempotency_key=key))
        if result.items_changed:
            _relink_production(locked, previous_skus=previous_skus)
        _notify_customer(locked, result)

    order.refresh_from_db()
    logger.info(
        "order_edit: order=%s revision=%s total %s -> %s settlement=%s actor=%s",
        order.ref, revision, result.previous_total_q, result.total_q, result.settlement.kind, actor,
    )
    return EditResult(plan=result, revision=revision, stock=stock_summary)


# ── Produtos ─────────────────────────────────────────────────────────────────


def _products_from_lines(order, lines, editable, next_revision: int, new_line_ids: list[str]) -> list[dict]:
    parsed = _parse_lines(lines)
    if not parsed:
        raise EditRefused(
            "A encomenda precisa de pelo menos um item. Para desistir de tudo, cancele a encomenda.",
            code="empty_order", field="items",
        )
    by_line = {item.line_id: item for item in editable}
    pricing = _Pricing(order)
    out: list[dict] = []
    new_lines: dict[str, dict] = {}
    seen: set[str] = set()

    def add_new(index: int, sku: str, qty: Decimal, *, name: str = "", options=None) -> None:
        product = pricing.product(sku)
        if product is None:
            raise EditRefused(f"O item {sku} não está no catálogo.", code="unknown_sku", field=f"items.{index}")
        # Escolha no produto (sabor, adicionais): conferida contra o cadastro de
        # agora e somada ao preço; a mesma escolha do mesmo SKU é a mesma linha.
        try:
            chosen = product_options.resolve_selection(pricing.catalog_product(sku), options or [])
        except product_options.OptionSelectionError as exc:
            raise EditRefused(exc.message, code=exc.code, field=f"items.{index}.options") from None
        display = product_options.base_name(name, chosen) if name else (product["name"] or sku)
        display = product_options.line_name(display, chosen)
        if weighed_sale.is_sold_by_weight(product["unit"]):
            # A mesma frase da venda: a peça entra pela etiqueta (ou pelo peso).
            raise EditRefused(
                f"{display} é vendido por peso: informe o valor da etiqueta.",
                code="weight_entry_required", field=f"items.{index}.weighed",
            )
        price_q = pricing.price(sku)
        if not price_q:
            raise EditRefused(
                f"{display} está sem preço no cadastro e não pode entrar na encomenda.",
                code="price_missing", field=f"items.{index}",
            )
        price_q = int(price_q) + product_options.options_unit_price_q(pricing.catalog_product(sku), chosen)
        key = f"{sku}:{price_q}:{product_options.signature(chosen)}"
        if key in new_lines:
            line = new_lines[key]
            line["qty"] = line["qty"] + qty
            line["line_total_q"] = monetary_mult(line["qty"], int(price_q))
            return
        line_id = f"E{next_revision}-{len(new_line_ids) + 1}"
        line = {
            "line_id": line_id,
            "sku": sku,
            "name": display,
            "qty": qty,
            "unit_price_q": int(price_q),
            "line_total_q": monetary_mult(qty, int(price_q)),
            "meta": {"added_by": SOURCE, **({product_options.LINE_OPTIONS_KEY: chosen} if chosen else {})},
        }
        new_lines[key] = line
        new_line_ids.append(line_id)
        out.append(line)

    def add_weighed(index: int, sku: str, declared: dict) -> None:
        """A peça pesada que ENTRA: uma linha por peça, como na venda.

        O que o operador tem em mãos (etiqueta ou peso) vira peso pelo preço do
        quilo da vitrine do canal — a mesma conversão da venda
        (``weighed_sale.resolve``) —, e o peso é cobrado pelo preço do catálogo
        no canal do pedido (a cascata do item novo).
        """
        field = f"items.{index}.weighed"
        product = pricing.product(sku)
        if product is None:
            raise EditRefused(f"O item {sku} não está no catálogo.", code="unknown_sku", field=f"items.{index}")
        display = product["name"] or sku
        if not weighed_sale.is_sold_by_weight(product["unit"]):
            raise EditRefused(f"{display} é vendido por unidade, não por peso.", code="not_sold_by_weight", field=field)
        entry = str(declared.get("entry") or "").strip().lower()
        if entry == weighed_sale.ENTRY_WEIGHT and not weighed_sale.weight_entry_enabled():
            raise EditRefused(
                f"Esta loja lança {display} pelo valor da etiqueta, não pelo peso.",
                code="weight_entry_disabled", field=field,
            )
        try:
            piece = weighed_sale.resolve(
                name=display,
                entry=entry,
                price_per_kg_q=weighed_sale.price_per_kg_q(sku, pricing.channel),
                label_q=_int(declared.get("label_q")) or None,
                weight_g=_int(declared.get("weight_g")) or None,
            )
        except weighed_sale.WeighedEntryError as exc:
            raise EditRefused(exc.message, code=exc.code, field=field) from None
        price_q = pricing.price(sku)
        if not price_q:
            raise EditRefused(
                f"{display} está sem preço no cadastro e não pode entrar na encomenda.",
                code="price_missing", field=f"items.{index}",
            )
        line_id = f"E{next_revision}-{len(new_line_ids) + 1}"
        out.append({
            "line_id": line_id,
            "sku": sku,
            "name": display,
            "qty": piece.qty,
            "unit_price_q": int(price_q),
            "line_total_q": monetary_mult(piece.qty, int(price_q)),
            "meta": {"added_by": SOURCE, "weighed": piece.as_meta()},
        })
        new_line_ids.append(line_id)

    for index, (line_id, sku, qty, weighed, options) in enumerate(parsed):
        old = by_line.get(line_id) if line_id else None
        if old is None:
            if weighed:
                add_weighed(index, sku, weighed)
            else:
                add_new(index, sku, qty, options=options)
            continue
        if line_id in seen:
            raise EditRefused("A mesma linha apareceu duas vezes.", code="duplicate_line", field=f"items.{index}")
        seen.add(line_id)
        if sku and sku != old.sku:
            raise EditRefused(
                "Uma linha trocou de produto. Tire a linha e acrescente o outro item.",
                code="line_sku_changed", field=f"items.{index}",
            )
        if _is_weighed_line(old):
            # A peça pesada é a peça: o peso não se digita (na venda também não).
            if qty != old.qty:
                raise EditRefused(
                    f"{old.name or old.sku} é peça pesada: o peso não muda. "
                    "Para trocar a peça, remova a linha e lance a outra etiqueta.",
                    code="weighed_line_changed", field=f"items.{index}",
                )
            out.append(_kept(old, old.qty))
            continue
        if qty != qty.to_integral_value() and old.qty == old.qty.to_integral_value():
            raise EditRefused(
                f"A quantidade de {old.name or old.sku} precisa ser inteira.",
                code="invalid_qty", field=f"items.{index}",
            )
        if qty <= old.qty:
            out.append(_kept(old, qty))
            continue
        old_options = product_options.line_options(old)
        price_q = pricing.price(old.sku)
        if price_q:
            price_q = int(price_q) + product_options.options_unit_price_q(
                pricing.catalog_product(old.sku), old_options,
            )
        if not price_q or int(price_q) == old.unit_price_q:
            # Mesmo preço (ou catálogo sem preço hoje): a linha cresce no preço
            # vendido — não há "antes" e "depois" diferentes a separar.
            out.append(_kept(old, qty))
            continue
        out.append(_kept(old, old.qty))
        add_new(index, old.sku, qty - old.qty, name=old.name, options=product_options.selection_of(old_options))
    return out


# ── Recebimento ──────────────────────────────────────────────────────────────


def _receiving(order, fulfillment, before: str, fee_lines, products_q: int, next_revision: int) -> dict:
    """O recebimento depois da edição: tipo, endereço, linha da taxa e as chaves.

    Sem ``fulfillment``, tudo fica como está (a taxa inclusive — nenhuma regra
    de frete grátis é reavaliada por uma troca de itens). Com ele:

    - retirada: a linha da taxa sai, e o endereço sai do pedido;
    - entrega com o MESMO endereço e sem exceção nova: a taxa fica;
    - entrega nova (ou endereço novo, ou exceção de taxa): a taxa sai do motor
      da venda (``pos.resolve_delivery_fee``); fora da área, recusa.
    """
    data = order.data or {}
    kept_fee = [order_composition.as_payload(item) for item in fee_lines]
    address_now = str(data.get("delivery_address") or "").strip()
    if fulfillment is None:
        return {"type": before, "changed": False, "fee_lines": kept_fee, "data_updates": {}, "address": address_now}
    if not isinstance(fulfillment, dict):
        raise EditRefused("Recebimento inválido.", code="invalid_fulfillment", field="fulfillment")

    kind = str(fulfillment.get("type") or before).strip().lower()
    if kind not in {"pickup", "delivery"}:
        raise EditRefused("Escolha retirada ou entrega.", code="invalid_fulfillment", field="fulfillment.type")

    if kind == "pickup":
        if before == "pickup":
            return {"type": "pickup", "changed": False, "fee_lines": kept_fee, "data_updates": {}, "address": ""}
        updates = {
            "fulfillment_type": "pickup",
            "delivery_address": None,
            "delivery_address_structured": None,
            "delivery_fee_q": None,
            "delivery_fee_override_q": None,
            "delivery_distance_km": None,
        }
        return {"type": "pickup", "changed": True, "fee_lines": [], "data_updates": updates, "address": ""}

    structured = fulfillment.get("delivery_address_structured")
    structured = structured if isinstance(structured, dict) and structured else None
    structured_now = data.get("delivery_address_structured") if isinstance(data.get("delivery_address_structured"), dict) else {}
    address_text = str(
        fulfillment.get("delivery_address") or (structured or {}).get("formatted_address") or ""
    ).strip()
    if structured is None and not address_text:
        structured, address_text = (structured_now or None), address_now
    if structured is None and not address_text:
        raise EditRefused(
            "Informe o endereço da entrega.", code="delivery_address_required", field="fulfillment.delivery_address",
        )
    override = fulfillment.get("delivery_fee_override_q")
    override_q = None if override in (None, "") else max(0, _int(override))
    tax_id = str(fulfillment.get("fiscal_tax_id") or "").strip()

    same_address = before == "delivery" and (
        _address_key(structured) == _address_key(structured_now)
        if structured is not None and structured_now
        else address_text == address_now
    )
    updates: dict = {}
    if before != "delivery":
        updates["fulfillment_type"] = "delivery"
    if not same_address:
        updates["delivery_address"] = address_text or None
        updates["delivery_address_structured"] = structured
    if tax_id:
        fiscal = dict(data.get("fiscal") or {})
        if fiscal.get("tax_id") != tax_id:
            fiscal["tax_id"] = tax_id
            updates["fiscal"] = fiscal

    if same_address and override_q is None:
        return {
            "type": "delivery", "changed": bool(updates), "fee_lines": kept_fee,
            "data_updates": updates, "address": address_text,
        }

    from shopman.shop.services.pos import resolve_delivery_fee

    resolution = resolve_delivery_fee(
        address_structured=structured, address_text=address_text, merchandise_q=products_q, override_q=override_q,
    )
    if resolution.blocked:
        raise EditRefused(
            "Este endereço está fora da área de entrega. Confira o endereço ou mantenha a retirada.",
            code="delivery_out_of_area", field="fulfillment.delivery_address",
        )
    fee_q = int(resolution.fee_q or 0)
    updates["delivery_fee_q"] = fee_q
    updates["delivery_fee_override_q"] = override_q
    if resolution.distance_km is not None:
        updates["delivery_distance_km"] = resolution.distance_km
    line_id = fee_lines[0].line_id if fee_lines else f"E{next_revision}-FEE"
    fee_payload = [] if fee_q <= 0 else [{
        "line_id": line_id,
        "sku": DELIVERY_FEE_SKU,
        "name": "Taxa de entrega",
        "qty": 1,
        "unit_price_q": fee_q,
        "line_total_q": fee_q,
        "meta": {"type": "delivery_fee", "non_production": True},
    }]
    return {"type": "delivery", "changed": True, "fee_lines": fee_payload, "data_updates": updates, "address": address_text}


#: O que faz de um endereço o MESMO endereço. A tela remonta o dicionário
#: (chaves vazias, instruções, ordem): comparar o dicionário inteiro faria uma
#: entrega sem mudança nenhuma recalcular a taxa.
_ADDRESS_IDENTITY = ("route", "street_number", "neighborhood", "postal_code", "city", "state_code", "complement")


def _address_key(structured) -> tuple:
    structured = structured if isinstance(structured, dict) else {}
    return tuple(str(structured.get(key) or "").strip().casefold() for key in _ADDRESS_IDENTITY)


def _require_delivery_identity(order, data_updates: dict, *, total_q: int) -> None:
    """Entrega com nota exige CPF/CNPJ e endereço completo — a régua da venda (24/09)."""
    from shopman.shop.services import delivery_fiscal_identity as identity

    view_data = dict(order.data or {})
    for key, value in data_updates.items():
        if value is None:
            view_data.pop(key, None)
        else:
            view_data[key] = value
    view = identity.order_view(data=view_data, channel_ref=order.channel_ref, total_q=total_q, ref=order.ref)
    refused = identity.refusal(identity.delivery_fiscal_gaps(view))
    if refused is None:
        return
    code, surface_field, message = refused
    raise EditRefused(message, code=code, field=f"fulfillment.{surface_field}")


# ── Data ─────────────────────────────────────────────────────────────────────


def _schedule(order, schedule) -> tuple[bool, str, str]:
    data = order.data or {}
    date_now = str(data.get("delivery_date") or "")
    slot_now = str(data.get("delivery_time_slot") or "")
    if schedule is None:
        return False, date_now, slot_now
    if not isinstance(schedule, dict):
        raise EditRefused("Data inválida.", code="invalid_date", field="date")
    raw_date = str(schedule.get("date") or date_now).strip()
    slot = str(schedule.get("slot") if schedule.get("slot") is not None else slot_now).strip()
    if raw_date == date_now and slot == slot_now:
        return False, date_now, slot_now
    from shopman.shop.services import reschedule as reschedule_service

    try:
        day, slot = reschedule_service.validate_choice(order, date=raw_date, slot=slot)
    except reschedule_service.RescheduleRefused as exc:
        raise EditRefused(exc.message, code=exc.code, field=exc.field or "date") from None
    return True, day.isoformat(), slot


# ── A diferença de valor ─────────────────────────────────────────────────────


def _settlement(order, *, previous_total_q: int, total_q: int):
    """O destino da diferença — e a recusa quando o meio não sabe devolver parte."""
    from shopman.shop.services import payment as payment_service

    captured = payment_service.captured_balance_q(order)
    if captured is None and total_q == previous_total_q:
        # O valor não muda (observação, data, troca sem diferença): não há
        # dinheiro a decidir, e um Payman mudo não precisa travar a edição.
        return Settlement(SETTLE_NONE), 0, 0, []
    if captured is None:
        raise EditRefused(
            "Não deu para conferir o pagamento desta encomenda agora. Tente de novo em instantes.",
            code="payment_unreadable",
        )
    on_account = payment_service.on_account_q(order)
    balance_before_q = max(0, previous_total_q - captured - on_account)
    intents = _intents(order)
    total_changes = total_q != previous_total_q

    if total_changes and (on_account > 0 or any(route == ROUTE_ACCOUNT for route, _i, _n in intents)):
        raise EditRefused(
            "Encomenda na conta do cliente: o valor não muda pela edição. Para mudar, cancele e refaça a encomenda.",
            code="on_account_total_locked",
        )
    if total_changes and _open_digital_charge(order):
        raise EditRefused(
            "Há uma cobrança (Pix ou link) com o valor antigo esperando o cliente. "
            "Receba ou cancele essa cobrança antes de mudar o valor.",
            code="open_digital_charge",
        )

    refund_q = max(0, min(captured, previous_total_q) - total_q)
    balance_after_q = max(0, total_q - captured - on_account)
    if refund_q <= 0:
        if balance_after_q > 0:
            return Settlement(SETTLE_COLLECT, balance_after_q), balance_before_q, balance_after_q, intents
        return Settlement(SETTLE_NONE), balance_before_q, balance_after_q, intents

    held = [(route, intent) for route, intent, net in intents if net > 0]
    routes = {route for route, _intent in held}
    if len(routes) != 1:
        raise EditRefused(
            "Esta encomenda foi paga em mais de um meio: a devolução de parte não sai sozinha. "
            "Para reduzir, cancele e refaça a encomenda.",
            code="mixed_payment_refund",
        )
    route = routes.pop()
    kind = {
        ROUTE_GATEWAY: SETTLE_REFUND_GATEWAY,
        ROUTE_CASH: SETTLE_REFUND_CASH,
        ROUTE_CARD_MACHINE: SETTLE_REFUND_CARD_MACHINE,
    }[route]
    return Settlement(kind, refund_q, str(held[0][1].method or "")), balance_before_q, balance_after_q, intents


def _intents(order) -> list[tuple[str, object, int]]:
    """``[(rota, intent, líquido)]`` dos intents que contam no dinheiro do pedido."""
    from shopman.payman import PaymentService

    rows = PaymentService.get_by_order(order.ref).filter(status__in=("captured", "refunded", "authorized"))
    out = []
    for intent in rows.order_by("id"):
        if intent.method == "account":
            out.append((ROUTE_ACCOUNT, intent, 0))
        elif intent.status == "authorized":
            continue  # autorizado sem captura não tem dinheiro na casa
        else:
            out.append((refund_route(intent), intent, _net_q(intent)))
    return out


def refund_route(intent) -> str:
    """Por onde o dinheiro deste intent volta ao cliente."""
    method = str(intent.method or "")
    if method == "cash":
        return ROUTE_CASH
    if method == "account":
        return ROUTE_ACCOUNT
    if method in _CARD_MACHINE_METHODS:
        return ROUTE_CARD_MACHINE
    if not intent.gateway:
        # Pix/cartão ATESTADOS no balcão (venda mista): não há gateway, a prova
        # é o papel da maquininha — e o estorno também.
        return ROUTE_CARD_MACHINE
    return ROUTE_GATEWAY


def _net_q(intent) -> int:
    from shopman.payman import PaymentService

    return (
        PaymentService.captured_total(intent.ref)
        - PaymentService.refunded_total(intent.ref)
        - PaymentService.chargeback_total(intent.ref)
    )


def _open_digital_charge(order) -> bool:
    """Há cobrança digital viva (Pix/link/cartão online) esperando o cliente?"""
    from shopman.payman import PaymentService

    return (
        PaymentService.get_by_order(order.ref)
        .filter(status__in=("pending", "authorized"))
        .exclude(method="account")
        .exclude(gateway="")
        .exists()
    )


def _payment_after(
    order, *, total_q: int, settlement: Settlement, balance_after_q: int, fulfillment_after: str,
    delivery_payment_method: str, intents,
) -> dict | None:
    """``Order.data["payment"]`` depois da edição — ou ``None`` quando não muda.

    O pagamento do pedido é lido por três leitores que precisam continuar
    somando o total NOVO: a nota fiscal (``fiscal._fiscal_payment`` — soma das
    ``tenders`` quando existem, senão ``amount_q``), o acerto no hand-off
    (``operator_orders.settle_delivery_cash`` — as formas pendentes cobrem o que
    falta) e a saída do entregador (``collection == "on_delivery"``).

    - ``amount_q`` gravado vira o total novo;
    - devolução: a forma recebida pelo meio que devolve encolhe junto;
    - saldo a receber: a forma pendente única passa a valer o saldo; sem forma
      nenhuma e com dinheiro digital já capturado, a parte recebida vira linha
      explícita (``received``) e o saldo vira linha pendente — sem isso a nota
      declararia só o que o balcão recebeu;
    - retirada que vira entrega com saldo: o entregador recebe na porta
      (``collection = on_delivery``), na forma combinada.
    """
    payment = dict((order.data or {}).get("payment") or {})
    original = dict(payment)
    total_changes = total_q != order_composition.effective_total_q(order)
    if "amount_q" in payment and total_changes:
        payment["amount_q"] = int(total_q)
    tenders = [dict(t) for t in payment.get("tenders") or [] if isinstance(t, dict)]

    if settlement.kind in REFUND_KINDS and tenders:
        remaining = settlement.amount_q
        route = {SETTLE_REFUND_CASH: ROUTE_CASH, SETTLE_REFUND_GATEWAY: ROUTE_GATEWAY}.get(
            settlement.kind, ROUTE_CARD_MACHINE,
        )
        for tender in reversed(tenders):
            if remaining <= 0:
                break
            if tender.get("status") != "received" or _tender_route(tender) != route:
                continue
            take = min(remaining, max(0, _int(tender.get("amount_q"))))
            tender["amount_q"] = _int(tender.get("amount_q")) - take
            remaining -= take
        payment["tenders"] = tenders

    door = fulfillment_after == "delivery"
    if balance_after_q > 0:
        pending = [t for t in tenders if t.get("status") != "received" and t.get("method") != "account"]
        if len(pending) > 1:
            raise EditRefused(
                "O saldo desta encomenda está dividido em mais de uma forma a receber: "
                "para mudar o valor, cancele e refaça a encomenda.",
                code="split_pending_tenders",
            )
        method_now = str(payment.get("method") or "").strip().lower()
        collects_by_hand = method_now in _COUNTER_METHODS or (not method_now and not intents)
        if pending:
            pending[0]["amount_q"] = balance_after_q
            if door:
                pending[0]["collection"] = "on_delivery"
            payment["tenders"] = tenders
        elif tenders or not collects_by_hand:
            method = delivery_payment_method or (method_now if method_now in _COUNTER_METHODS else "")
            if door and method not in _COUNTER_METHODS:
                raise EditRefused(
                    f"Diga como o entregador recebe os {_brl(balance_after_q)} que faltam: "
                    "dinheiro, débito ou crédito.",
                    code="delivery_payment_method_required",
                    field="fulfillment.delivery_payment_method",
                )
            if not tenders:
                tenders = _received_tenders(intents)
            tenders.append({
                "method": method or "cash",
                "amount_q": balance_after_q,
                "collection": "on_delivery",
                "status": "pending",
            })
            payment["tenders"] = tenders
            payment["method"] = "mixed" if len({t["method"] for t in tenders}) > 1 else tenders[0]["method"]
            payment["collection"] = "on_delivery"
        elif door:
            method = delivery_payment_method or method_now
            if method not in _COUNTER_METHODS:
                raise EditRefused(
                    f"Diga como o entregador recebe os {_brl(balance_after_q)}: dinheiro, débito ou crédito.",
                    code="delivery_payment_method_required",
                    field="fulfillment.delivery_payment_method",
                )
            payment["method"] = method
            payment["collection"] = "on_delivery"
    return payment if payment != original else None


def _received_tenders(intents) -> list[dict]:
    """O dinheiro já capturado como linhas ``received`` — uma por intent."""
    out = []
    for route, intent, net in intents:
        if route == ROUTE_ACCOUNT or net <= 0:
            continue
        out.append({
            "method": str(intent.method or ""),
            "amount_q": int(net),
            "collection": "online" if route == ROUTE_GATEWAY else "terminal",
            "status": "received",
            "intent_ref": intent.ref,
        })
    return out


def _tender_route(tender: dict) -> str:
    method = str(tender.get("method") or "")
    if method == "cash":
        return ROUTE_CASH
    if method in _CARD_MACHINE_METHODS or str(tender.get("collection") or "") == "terminal":
        return ROUTE_CARD_MACHINE
    return ROUTE_GATEWAY


def _refund_gateway(order_ref: str, *, amount_q: int, idempotency_key: str) -> None:
    """Estorno parcial pelo gateway, depois do commit.

    Fora da transação de propósito: estorno é chamada remota, e segurar o lock
    do pedido durante ela prenderia a linha por segundos. Falha transitória
    vira retry (Directive ``payment.refund``); recusa do gateway vira alerta
    crítico — as duas redes são as de ``payment.refund``.
    """
    from shopman.shop.services import payment as payment_service

    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    try:
        payment_service.refund(order, amount_q=amount_q, idempotency_key=idempotency_key)
    except Exception as exc:
        logger.exception("order_edit: estorno parcial falhou order=%s", order_ref)
        payment_service.alert_refund_failed(order, "", amount_q, str(exc) or "erro inesperado")


# ── O aviso ao cliente ───────────────────────────────────────────────────────


def customer_note(result: EditPlan) -> str:
    """O ``{status_note}`` do aviso ``order_updated``: o que mudou e o que acontece com o dinheiro.

    Frases INTEIRAS, cada uma com o seu ponto final — é o padrão aprovado na Meta
    para a informação que muda ("{{Motivo: item indisponível.}}"): o texto do
    aviso não põe ponto depois da variável. Nunca vazia.

    Montada por regra a partir da diferença da edição, nunca inventada. Edição
    grande não vira parágrafo: acima de :data:`MAX_ITEM_CHANGES_DESCRIBED`
    mudanças de itens, a frase resume ("Ajustamos 5 itens."); o dinheiro sai sempre.
    """
    sentences: list[str] = []
    products = _describe_for_customer(result.diff) if result.items_changed else ""
    if products:
        sentences.append(products)
    if result.fulfillment_changed:
        if result.fulfillment_after == "delivery":
            where = f" em {result.delivery_address_after}" if result.delivery_address_after else ""
            fee = (
                f", com taxa de {_brl(result.delivery_fee_after_q)}"
                if result.delivery_fee_after_q else ", sem taxa de entrega"
            )
            sentences.append(f"Agora é entrega{where}{fee}.")
        else:
            sentences.append("Agora é retirada na loja.")
    if result.schedule_changed:
        phrase = _commitment_phrase(result.date_after, result.slot_after)
        if phrase:
            sentences.append(f"Nova data: {phrase}.")
    if result.notes_changed:
        sentences.append("Anotamos sua observação." if result.notes_after else "Tiramos a observação do pedido.")
    money = _money_for_customer(result)
    if money:
        sentences.append(money)
    return " ".join(sentences) or "Os detalhes estão no acompanhamento."


#: Acima disto, as mudanças de itens viram um resumo: um aviso não é extrato.
MAX_ITEM_CHANGES_DESCRIBED = 3


def _describe_for_customer(difference: dict) -> str:
    parts: list[str] = []
    for entry in difference.get("removed") or []:
        if str(entry.get("sku") or "").startswith("__"):
            continue
        verb = "saiu" if _is_one(entry["qty"]) else "saíram"
        parts.append(f"{verb} {entry['qty']} {entry['name']}")
    for entry in difference.get("added") or []:
        if str(entry.get("sku") or "").startswith("__"):
            continue
        verb = "entrou" if _is_one(entry["qty"]) else "entraram"
        parts.append(f"{verb} {entry['qty']} {entry['name']}")
    for entry in difference.get("changed") or []:
        parts.append(f"{entry['name']} passou de {entry['previous_qty']} para {entry['qty']}")
    if not parts:
        return ""
    if len(parts) > MAX_ITEM_CHANGES_DESCRIBED:
        return f"Ajustamos {len(parts)} itens."
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]
    return text[:1].upper() + text[1:] + "."


def _money_for_customer(result: EditPlan) -> str:
    total = _brl(result.total_q)
    where = "na entrega" if result.fulfillment_after == "delivery" else "na retirada"
    settlement = result.settlement
    if settlement.kind in REFUND_KINDS:
        amount = _brl(settlement.amount_q)
        if settlement.kind == SETTLE_REFUND_CASH:
            how = f"Devolvemos {amount} em dinheiro {where}."
        elif settlement.method == "pix":
            how = f"Devolvemos {amount} pelo Pix."
        else:
            how = f"Devolvemos {amount} no seu cartão."
        return f"O novo total é {total}. {how}"
    if result.total_q == result.previous_total_q:
        return f"O total continua {total}." if result.items_changed else ""
    if settlement.kind == SETTLE_COLLECT:
        if result.balance_before_q == 0:
            moment = "a entrega" if result.fulfillment_after == "delivery" else "a retirada"
            return f"O novo total é {total}. A diferença de {_brl(settlement.amount_q)} fica para {moment}."
        return f"O novo total é {total}, a pagar {where}."
    return f"O novo total é {total}."


def _commitment_phrase(date_iso: str, slot: str) -> str:
    from shopman.shop.services.notification import _commitment_phrase as phrase

    return phrase(SimpleNamespace(data={"delivery_date": date_iso, "delivery_time_slot": slot}))


def _notify_customer(order, result: EditPlan) -> None:
    from shopman.shop.notification_copy import CUSTOMER_COPY
    from shopman.shop.services import notification

    if CUSTOMER_NOTICE_TEMPLATE not in CUSTOMER_COPY:
        return
    # Uma mensagem POR edição: o dedupe de ``send`` é por pedido+aviso, e sem a
    # ocorrência a segunda edição calava.
    notification.send(
        order, CUSTOMER_NOTICE_TEMPLATE, occurrence=str(_edit_count(order)), status_note=result.customer_note,
    )


def _edit_count(order) -> int:
    from shopman.orderman.models import OrderEvent

    return OrderEvent.objects.filter(order=order, type=EVENT_TYPE).count()


# ── Internos ─────────────────────────────────────────────────────────────────


class _Pricing:
    """Preço e cadastro dos itens que ENTRAM, pela cascata da venda, com cache."""

    def __init__(self, order):
        self.order = order
        self._loaded = False
        self._channel = None
        self._customer = None
        self._prices: dict[str, int | None] = {}
        self._products: dict[str, dict | None] = {}
        self._catalog_products: dict = {}

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        from shopman.shop.models import Channel

        self._channel = Channel.objects.filter(ref=self.order.channel_ref).first()
        data = self.order.data or {}
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        customer_ref = data.get("customer_ref") or customer.get("ref")
        if customer_ref:
            try:
                from shopman.guestman.models import Customer

                self._customer = Customer.objects.select_related("price_tier").filter(ref=customer_ref).first()
            except Exception:
                logger.warning("order_edit: faixa do cliente indisponível order=%s", self.order.ref, exc_info=True)

    @property
    def channel(self):
        self._load()
        return self._channel

    def price(self, sku: str) -> int | None:
        if sku not in self._prices:
            self._load()
            from shopman.shop.handlers.pricing import OffermanPricingBackend

            price = OffermanPricingBackend().get_price(sku, self._channel, customer=self._customer, qty=1)
            self._prices[sku] = int(price) if price else None
        return self._prices[sku]

    def product(self, sku: str) -> dict | None:
        if sku not in self._products:
            from shopman.offerman.models import Product

            row = Product.objects.filter(sku=sku).values("name", "unit").first()
            self._products[sku] = {"name": str(row["name"] or ""), "unit": str(row["unit"] or "")} if row else None
        return self._products[sku]

    def catalog_product(self, sku: str):
        """O ``Product`` inteiro, para as escolhas (``metadata["option_groups"]``)."""
        if sku not in self._catalog_products:
            from shopman.offerman.models import Product

            self._catalog_products[sku] = Product.objects.filter(sku=sku).first()
        return self._catalog_products[sku]


def _parse_lines(lines) -> list[tuple[str, str, Decimal, dict | None, list[dict]]]:
    if not isinstance(lines, list | tuple):
        raise EditRefused("Lista de itens inválida.", code="invalid_items", field="items")
    parsed = []
    for index, raw in enumerate(lines):
        if not isinstance(raw, dict):
            raise EditRefused("Item inválido.", code="invalid_items", field=f"items.{index}")
        sku = str(raw.get("sku") or "").strip()
        line_id = str(raw.get("line_id") or "").strip()
        try:
            qty = Decimal(str(raw.get("qty")))
        except (InvalidOperation, TypeError, ValueError):
            qty = Decimal("NaN")
        if not qty.is_finite() or qty <= 0:
            raise EditRefused(
                "Quantidade inválida. Para tirar o item, remova a linha.", code="invalid_qty", field=f"items.{index}",
            )
        if not sku and not line_id:
            raise EditRefused("Item sem produto.", code="invalid_items", field=f"items.{index}")
        if sku.startswith("__"):
            raise EditRefused(
                "A taxa de entrega muda pelo recebimento, não pelos itens.", code="invalid_items", field=f"items.{index}",
            )
        weighed = raw.get("weighed")
        if weighed not in (None, "", {}) and not isinstance(weighed, dict):
            raise EditRefused("Venda por peso inválida.", code="invalid_weighed", field=f"items.{index}.weighed")
        raw_options = raw.get("options") or []
        if not isinstance(raw_options, list):
            raise EditRefused("Escolha do item inválida.", code="invalid_options", field=f"items.{index}.options")
        options = [
            {"group": str(entry.get("group") or ""), "ref": str(entry.get("ref") or "")}
            for entry in raw_options
            if isinstance(entry, dict)
        ]
        parsed.append((line_id, sku, qty, weighed or None, options))
    return parsed


def _is_weighed_line(item) -> bool:
    """A linha é uma peça vendida por peso (registro ``meta.weighed`` ou kg fracionado)."""
    meta = item.meta if isinstance(item.meta, dict) else {}
    return isinstance(meta.get("weighed"), dict) or item.qty != item.qty.to_integral_value()


def _is_fee_line(item) -> bool:
    meta = item.meta if isinstance(item.meta, dict) else {}
    return str(item.sku or "") == DELIVERY_FEE_SKU or meta.get("type") == "delivery_fee"


def _is_fixed_line(item) -> bool:
    """Linha que não é produto (taxa de entrega e afins): a lista de itens não a toca."""
    return str(item.sku or "").startswith("__") or _is_fee_line(item)


def _kept(old, qty: Decimal) -> dict:
    line_total_q = old.line_total_q if qty == old.qty else monetary_mult(qty, old.unit_price_q)
    return {
        "line_id": old.line_id,
        "sku": old.sku,
        "name": old.name,
        "qty": qty,
        "unit_price_q": old.unit_price_q,
        "line_total_q": int(line_total_q),
        "meta": old.meta,
    }


def _payload(line: dict) -> dict:
    from shopman.shop.services.order_helpers import json_quantity

    return {**line, "qty": json_quantity(line["qty"])}


def _next_revision(order) -> int:
    return int((order_composition.adjustment(order) or {}).get("revision") or 0) + 1


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_one(qty) -> bool:
    try:
        return Decimal(str(qty)) == 1
    except (InvalidOperation, ValueError):
        return False


def _brl(value_q: int) -> str:
    return f"R$ {format_money(int(value_q))}"


def _stock_refusal(order, exc, items: list[dict]) -> str:
    from shopman.shop.services.order_helpers import get_commitment_date

    context = getattr(exc, "context", None) or {}
    if exc.code == "insufficient_stock":
        sku = context.get("sku") or context.get("component_sku") or ""
        name = next((item.get("name") for item in items if item.get("sku") == sku), None) or sku
        day = get_commitment_date(order)
        when = f" para {day.strftime('%d/%m')}" if day else ""
        return f"{name} não tem saldo{when}. Nada foi alterado."
    return f"{exc.message} Nada foi alterado."


def _relink_production(order, *, previous_skus) -> None:
    """Religa as ordens de produção depois do commit — o SKU que saiu inclusive."""
    from shopman.shop.handlers.production_order_sync import queue_order_items_resync

    queue_order_items_resync(order=order, previous_skus=previous_skus)


def _event_payload(result: EditPlan, *, revision, approved_by) -> dict:
    payload = {
        "source": SOURCE,
        "revision": revision,
        "previous_total_q": result.previous_total_q,
        "total_q": result.total_q,
        "diff": result.diff if result.items_changed else {"added": [], "removed": [], "changed": []},
        "settlement": {
            "kind": result.settlement.kind,
            "amount_q": result.settlement.amount_q,
            "method": result.settlement.method,
        },
        "customer_note": result.customer_note,
    }
    if result.notes_changed:
        payload["notes"] = {"before": result.notes_before, "after": result.notes_after}
    if result.fulfillment_changed:
        payload["fulfillment"] = {"before": result.fulfillment_before, "after": result.fulfillment_after}
    if result.fulfillment_after == "delivery" and result.delivery_fee_after_q != result.delivery_fee_before_q:
        payload["delivery_fee"] = {"before_q": result.delivery_fee_before_q, "after_q": result.delivery_fee_after_q}
    if result.schedule_changed:
        payload["schedule"] = {"date": result.date_after, "slot": result.slot_after}
    if approved_by is not None:
        username = approved_by.get_username() if hasattr(approved_by, "get_username") else str(approved_by)
        payload["approved_by"] = username
    return payload


__all__ = [
    "CUSTOMER_NOTICE_TEMPLATE",
    "EVENT_TYPE",
    "EditPlan",
    "EditRefused",
    "EditResult",
    "GOODS_STILL_IN_THE_HOUSE",
    "REFUND_KINDS",
    "SETTLE_COLLECT",
    "SETTLE_NONE",
    "SETTLE_REFUND_CARD_MACHINE",
    "SETTLE_REFUND_CASH",
    "SETTLE_REFUND_GATEWAY",
    "SOURCE",
    "Settlement",
    "apply_final_items",
    "customer_note",
    "edit",
    "fiscal_authorized",
    "plan",
    "refund_route",
    "state_refusal",
]
