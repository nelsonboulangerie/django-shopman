"""Contagem de insumos — write-side da aba Contagem do Compras.

Traduz a contagem física do dono em ajustes do ledger do Stockman, sempre pelo
caminho canônico (``stock.adjust``/``stock.receive``), nunca escrevendo no
Quant. Cada divergência exige motivo e sai como ``Move kind=adjust`` com o
usuário que contou — a trilha de auditoria é o próprio ledger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.apps import apps
from django.db import transaction

from shopman.backstage.projections.purchase_count import (
    PurchaseCountProjection,
    build_purchase_count,
    system_qty_map,
)
from shopman.backstage.services.purchase import PurchaseError, _default_receive_position

logger = logging.getLogger(__name__)

QTY_PLACES = Decimal("0.001")


@dataclass(frozen=True)
class ResolvedCountLine:
    material: Any
    counted: Decimal
    reason: str


def submit_count(payload: dict[str, Any], *, user) -> tuple[PurchaseCountProjection, str]:
    """Aplica a contagem física: divergência vira ajuste no Stockman."""
    lines = _resolve_lines(payload)
    adjusted = 0
    with transaction.atomic():
        for line in lines:
            if _apply_count(line, user=user):
                adjusted += 1
    if adjusted:
        plural = "s" if adjusted > 1 else ""
        message = f"Contagem registrada: {adjusted} ajuste{plural} lançado{plural} no estoque."
    else:
        message = "Contagem registrada sem divergência. Nenhum ajuste foi necessário."
    return build_purchase_count(), message


def _resolve_lines(payload: dict[str, Any]) -> list[ResolvedCountLine]:
    Material = apps.get_model("buyman", "Material")
    raw_lines = payload.get("counts")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise PurchaseError("Informe ao menos um insumo contado.", code="count_empty", field="counts")

    system = system_qty_map(list(Material.objects.values_list("sku", flat=True)))
    resolved: list[ResolvedCountLine] = []
    seen: set[str] = set()
    for entry in raw_lines:
        entry = entry if isinstance(entry, dict) else {}
        sku = str(entry.get("materialSku") or entry.get("material_sku") or "").strip()
        if not sku:
            raise PurchaseError("Linha de contagem sem insumo.", code="count_material_required", field="materialSku")
        if sku in seen:
            raise PurchaseError(
                f"O insumo {sku} aparece duas vezes na contagem.",
                code="count_material_duplicated",
                field="materialSku",
            )
        seen.add(sku)
        material = Material.objects.filter(sku=sku).first()
        if material is None:
            raise PurchaseError(
                f"Insumo {sku} não existe na base de Compras.",
                code="count_material_not_found",
                field="materialSku",
                status_code=404,
            )
        counted = _parse_qty(entry.get("countedQty", entry.get("counted_qty")))
        if counted is None:
            raise PurchaseError(
                f"Quantidade contada inválida para {material.name}.",
                code="count_qty_invalid",
                field="countedQty",
            )
        reason = str(entry.get("reason") or "").strip()
        if counted != system.get(sku, Decimal("0")) and not reason:
            raise PurchaseError(
                f"Divergência em {material.name} exige um motivo.",
                code="count_reason_required",
                field="reason",
            )
        resolved.append(ResolvedCountLine(material=material, counted=counted, reason=reason))
    return resolved


def _apply_count(line: ResolvedCountLine, *, user) -> bool:
    """Leva o saldo do SKU ao contado. Retorna True quando lançou ajuste."""
    from shopman.stockman import stock
    from shopman.stockman.models.move import Move

    sku = line.material.sku
    quants = list(
        stock.list_quants(sku, include_future=False).order_by("created_at", "pk")
    )
    system = sum((quant.quantity for quant in quants), Decimal("0"))
    delta = line.counted - system
    if delta == 0:
        return False
    # O saldo pode ter mudado entre carregar a tela e confirmar: a divergência
    # real é a de agora, e ela continua exigindo motivo.
    if not line.reason:
        raise PurchaseError(
            f"Divergência em {line.material.name} exige um motivo.",
            code="count_reason_required",
            field="reason",
        )

    if delta > 0:
        # Sobra encontrada entra no quant mais novo; sem quant, nasce um no
        # depósito padrão — mesmo destino do recebimento, kind=ADJUST.
        if quants:
            target = quants[-1]
            stock.adjust(target, target.quantity + delta, line.reason, user=user)
        else:
            stock.receive(
                quantity=delta,
                sku=sku,
                position=_default_receive_position(),
                user=user,
                reason=f"Ajuste: {line.reason}",
                kind=Move.Kind.ADJUST,
            )
    else:
        # Falta some do estoque mais antigo primeiro (consumo é FIFO, a quebra
        # também): zera quant a quant até cobrir a diferença.
        remaining = -delta
        for quant in quants:
            if remaining <= 0:
                break
            take = min(quant.quantity, remaining)
            stock.adjust(quant, quant.quantity - take, line.reason, user=user)
            remaining -= take

    logger.info(
        "purchase.count_adjusted",
        extra={"sku": sku, "system": str(system), "counted": str(line.counted), "delta": str(delta)},
    )
    return True


def _parse_qty(raw: Any) -> Decimal | None:
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
