"""Checkout read-side projections: operational dates and remembered defaults.

Builders return semantic data with no copy or formatting. The stock decision
is not here: it is Stockman's, read by the cart and by the commit
(``shop.services.availability``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
    "availability_dates",
    "customer_checkout_defaults",
]
