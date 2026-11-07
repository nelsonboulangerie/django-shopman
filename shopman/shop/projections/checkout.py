"""Checkout read-side projections: operational dates and remembered defaults.

Builders return semantic data with no copy or formatting. The stock decision
is not here: it is Stockman's, read by the cart and by the commit
(``shop.services.availability``).
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def availability_dates(
    max_preorder_days: int, *, now: datetime | None = None
) -> tuple[tuple[str, ...], tuple[int, ...], bool]:
    """Próximas datas operacionais (ISO), dias da semana fechados e ``today_over``.

    Fonte: ``business_calendar`` (horário semanal + feriados/férias coletivas) —
    o mesmo serviço read-only que ``shop_status``/``order_tracking`` já consomem
    pelo read-side. Exposto aqui para a presentation ler sem importar o serviço
    (regra R-A). Degrada para vazio se algo falhar — a UI cai no fallback de datas.

    HOJE só entra se ainda tem horário: a grade de hoje (``fulfillment_window
    .delivery_windows_for``, a mesma da retirada e da entrega) é quem diz. Às
    17:54 de uma loja que fecha às 18h a meia hora já não cabe, e "Hoje" levaria
    o cliente a uma lista vazia. ``today_over`` é verdadeiro quando hoje é dia de
    loja aberta e as retiradas e entregas de hoje já acabaram: a tela diz por que
    "Hoje" não está entre as opções, em vez de ele sumir calado.
    """
    try:
        from shopman.shop.services import business_calendar, fulfillment_window

        # Três para sobrar duas: a UI mostra "Hoje" (se ainda dá) + a próxima fornada.
        dates = business_calendar.available_dates(max_count=3, horizon_days=max_preorder_days, now=now)
        today = fulfillment_window._local_today(now=now)
        today_over = (
            business_calendar.is_open_on(today)
            and business_calendar.selling_hours_for(today) is not None
            and not fulfillment_window.delivery_windows_for(today, now=now)
        )
        if today_over:
            dates = [day for day in dates if day != today]
        return (
            tuple(d.isoformat() for d in dates[:2]),
            tuple(business_calendar.closed_weekdays()),
            bool(today_over),
        )
    except Exception:
        logger.debug("checkout_projection_availability_dates_failed", exc_info=True)
        return (), (), False


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
    "availability_dates",
    "customer_checkout_defaults",
]
