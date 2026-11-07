"""Itens do detalhe do pedido a preço de tabela, com o desconto em linha própria.

O desconto (cupom, promoção, grupo, manual) entra no preço de cada linha: o
cupom de R$ 5,00 de valor fixo é rateado entre as linhas, e o detalhe mostrava
"Chá R$ 149,27" e "Água R$ 5,73" sem nenhuma linha "Cupom". O operador não
tinha como saber que houve cupom, nem qual (beta 06/11).

Aqui cada linha volta ao preço de tabela (``meta["_list_q"]``, carimbado pelo
``ItemPricingModifier``; o mesmo que a sacola do Storefront lê) e o que foi
descontado sai em linhas próprias, agrupado pela origem: "Cupom BEMVINDO" com o
código do cupom, e as demais pelo nome do desconto. A soma das linhas menos os
descontos é a soma do que foi cobrado nos itens.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shopman.utils.monetary import format_money, monetary_mult

from shopman.shop.projections.types import OrderItemProjection
from shopman.shop.services import order_composition


@dataclass(frozen=True)
class OrderDiscountLineProjection:
    """Uma linha de desconto do detalhe: "Cupom BEMVINDO", "−R$ 5,00"."""

    #: ``coupon`` (cupom) ou ``discount`` (promoção, grupo, desconto manual).
    kind: str
    label: str
    amount_display: str


def _money(value_q: int) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _qty(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("1")


def _list_unit_q(meta: dict, unit_q: int) -> int:
    listed = meta.get("_list_q")
    try:
        listed_q = int(listed) if listed is not None else 0
    except (TypeError, ValueError):
        return unit_q
    return max(unit_q, listed_q)


def _coupon_code(order) -> str:
    pricing = (getattr(order, "snapshot", None) or {}).get("pricing") or {}
    coupon = pricing.get("coupon") or {}
    return str(coupon.get("code") or (order.data or {}).get("coupon_code") or "").strip().upper()


def priced_items(order) -> tuple[tuple[OrderItemProjection, ...], tuple[OrderDiscountLineProjection, ...]]:
    """Os itens que valem agora, a preço de tabela, e as linhas de desconto."""
    coupon_code = _coupon_code(order)
    items: list[OrderItemProjection] = []
    discounts: dict[tuple[str, str], int] = {}
    for it in order_composition.effective_items(order):
        meta = it.meta if isinstance(it.meta, dict) else {}
        unit_q = int(it.unit_price_q or 0)
        line_q = int(it.line_total_q or 0)
        list_unit_q = _list_unit_q(meta, unit_q)
        list_line_q = monetary_mult(_qty(it.qty), list_unit_q) if list_unit_q != unit_q else line_q
        discount_q = list_line_q - line_q
        if discount_q > 0:
            disc = meta.get("_disc") if isinstance(meta.get("_disc"), dict) else {}
            if disc.get("type") == "coupon":
                key = ("coupon", f"Cupom {coupon_code}" if coupon_code else "Cupom")
            else:
                key = ("discount", str(disc.get("label") or "").strip() or "Desconto")
            discounts[key] = discounts.get(key, 0) + discount_q
        else:
            list_unit_q, list_line_q = unit_q, line_q
        items.append(
            OrderItemProjection(
                sku=it.sku,
                name=it.name or it.sku,
                qty=format(it.qty.normalize(), "f"),
                unit_price_display=_money(list_unit_q),
                total_display=_money(list_line_q),
            )
        )
    # Cupom primeiro: é o que o operador procura quando o cliente pergunta.
    lines = sorted(discounts.items(), key=lambda entry: (entry[0][0] != "coupon", entry[0][1]))
    return tuple(items), tuple(
        OrderDiscountLineProjection(kind=kind, label=label, amount_display=f"−{_money(amount_q)}")
        for (kind, label), amount_q in lines
    )


__all__ = ["OrderDiscountLineProjection", "priced_items"]
