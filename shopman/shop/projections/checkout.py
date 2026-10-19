"""Checkout read-side projections — stock shortfalls and supporting data.

Drained out of ``checkout_context`` (which embedded ``format_money`` and copy).
Builders return semantic data — cents, refs, quantities — with no copy or
formatting. The storefront presentation renders stock messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from . import catalog_context, checkout_context

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class StockShortfallProjection:
    """A cart line Stockman's promise decision refuses for this session."""

    line_id: str
    sku: str
    name: str
    requested_qty: Decimal | int
    available_qty: Decimal | int


def _qty(value) -> Decimal | int:
    qty = Decimal(str(value or 0))
    return int(qty) if qty == qty.to_integral_value() else qty


def cart_stock_shortfalls(
    *,
    session_key: str,
    cart_lines,
    channel_ref: str,
    target_date: date | None = None,
) -> tuple[tuple[StockShortfallProjection, ...], bool]:
    """Lines Stockman's decision refuses, with the session's own holds as its own.

    One batched reading for every line (``catalog_context.availability_for_skus``
    on the commitment date, today when there is none), then Stockman's pure
    decision per line (``catalog_context.session_line_promise``). Nothing is
    recomputed here: a SKU without ledger, ``demand_ok`` and pause are the
    decision's, not this function's.

    Returns ``(shortfalls, service_unavailable)``; ``service_unavailable`` is
    True when the stock service answered for nothing.
    """
    if not cart_lines:
        return (), False

    from django.utils import timezone

    readings = catalog_context.availability_for_skus(
        list(dict.fromkeys(line.sku for line in cart_lines)),
        channel_ref=channel_ref,
        target_date=target_date or timezone.localdate(),
    )
    session_held = checkout_context.session_held_qty(session_key, target_date=target_date)
    shortfalls = []
    skipped = 0
    for line in cart_lines:
        reading = readings.get(line.sku)
        if reading is None:
            skipped += 1
            continue
        approved, ceiling = catalog_context.session_line_promise(
            line.sku, line.qty, reading, session_held.get(line.sku, Decimal("0")),
        )
        if approved:
            continue
        shortfalls.append(
            StockShortfallProjection(
                line_id=line.line_id,
                sku=line.sku,
                name=line.name or line.sku,
                requested_qty=_qty(line.qty),
                available_qty=_qty(ceiling),
            )
        )

    service_unavailable = skipped == len(cart_lines)
    if skipped:
        logger.warning("checkout.stock_check_unavailable: %d line(s) skipped", skipped)
    return tuple(shortfalls), service_unavailable


def availability_dates(max_preorder_days: int) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Próximas datas operacionais (ISO) + dias da semana fechados.

    Fonte: ``business_calendar`` (horário semanal + feriados/férias coletivas) —
    o mesmo serviço read-only que ``shop_status``/``order_tracking`` já consomem
    pelo read-side. Exposto aqui para a presentation ler sem importar o serviço
    (regra R-A). Degrada para vazio se algo falhar — a UI cai no fallback de datas.
    """
    try:
        from shopman.shop.services import business_calendar

        # Duas é o bastante: a UI mostra "Hoje" (se aberto) + a próxima fornada.
        dates = business_calendar.available_dates(max_count=2, horizon_days=max_preorder_days)
        return (
            tuple(d.isoformat() for d in dates),
            tuple(business_calendar.closed_weekdays()),
        )
    except Exception:
        logger.debug("checkout_projection_availability_dates_failed", exc_info=True)
        return (), ()


def customer_checkout_defaults(customer_ref: str, channel_ref: str) -> dict:
    """Preferências lembradas pelo checkout, no read-side canônico.

    A apresentação não importa serviços de mutação diretamente. Falha de
    conveniência degrada para vazio: nunca impede comprar.
    """
    if not customer_ref:
        return {}
    try:
        from shopman.shop.services.checkout_defaults import CheckoutDefaultsService

        return CheckoutDefaultsService.get_defaults(customer_ref, channel_ref)
    except Exception:
        logger.debug(
            "checkout_projection_customer_defaults_failed customer=%s channel=%s",
            customer_ref,
            channel_ref,
            exc_info=True,
        )
        return {}


__all__ = [
    "StockShortfallProjection",
    "availability_dates",
    "cart_stock_shortfalls",
    "customer_checkout_defaults",
]
