"""Checkout read-side projections: operational dates and remembered defaults.

Builders return semantic data with no copy or formatting. The stock decision
is not here: it is Stockman's, read by the cart and by the commit
(``shop.services.availability``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcceptanceWindow:
    """O prazo que a casa tem para aceitar um pedido enviado AGORA.

    ``minutes`` é o prazo do pedido (curto no pedido do dia com a casa aberta,
    longo na encomenda e com a casa fechada); ``deadline`` é quando ele vence,
    contado em tempo de loja aberta; ``runs_now`` diz que o prazo cabe inteiro
    no expediente em curso, então "em até N minutos" é verdade. Quando não
    cabe (casa fechada, ou o fechamento chega antes), só o ``deadline`` é.
    """

    minutes: int
    deadline: datetime
    runs_now: bool


def shop_today(*, now: datetime | None = None) -> date:
    """O "hoje" da loja, no fuso dela: o mesmo de ``availability_dates``.

    A tela do checkout lia o dia do relógio do dispositivo; "hoje", "amanhã" e os
    limites do calendário passam a sair daqui.
    """
    from shopman.shop.services import fulfillment_window

    return fulfillment_window._local_today(now=now)


def acceptance_window(
    channel_ref: str, *, order_date: date | None, now: datetime | None = None,
) -> AcceptanceWindow | None:
    """O prazo de aceite de um pedido para ``order_date`` enviado agora.

    Só no modo ``auto_cancel`` (a loja aceita ou o pedido cancela e o valor
    volta): é o único em que existe um prazo a prometer. A régua é a mesma de
    ``lifecycle.acceptance_timeout_minutes``: prazo longo na encomenda para
    outro dia e no pedido que chega com a casa fechada; e o vencimento sai de
    ``business_calendar.next_operational_deadline``, o mesmo que agenda o
    cancelamento. ``None`` quando não há prazo a prometer (outro modo, canal
    sem prazo, casa sem próxima abertura) ou quando a leitura do calendário
    falha: a tela não promete o que não sabe.

    A configuração do canal é lida FORA do ``try``: canal sem configuração é
    defeito de instância e falha gritando, nunca vira "sem prazo" em silêncio
    (``test_instance_runtime_config``).
    """
    from django.utils import timezone

    from shopman.shop.config import ChannelConfig
    from shopman.shop.services import business_calendar

    confirmation = ChannelConfig.for_channel(channel_ref).confirmation
    if confirmation.mode != "auto_cancel":
        return None
    try:
        moment = now or timezone.now()
        state = business_calendar.current_business_state(now=moment)
        preorder = order_date is not None and order_date > timezone.localdate(moment)
        minutes = confirmation.acceptance_timeout_minutes(long_deadline=preorder or state.is_closed)
        if minutes <= 0:
            return None
        timeout = timedelta(minutes=minutes)
        deadline, _state = business_calendar.next_operational_deadline(timeout=timeout, now=moment)
        if deadline is None:
            return None
        return AcceptanceWindow(
            minutes=minutes,
            deadline=deadline,
            runs_now=state.is_open and deadline - moment <= timeout + timedelta(seconds=1),
        )
    except Exception:
        logger.debug("checkout_projection_acceptance_window_failed", exc_info=True)
        return None


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


@dataclass(frozen=True)
class MenuDays:
    """Os dias que o "Para quando?" do cardápio pode oferecer (OC-33 B1).

    ``today_open``: hoje ainda tem horário de retirada ou entrega (a mesma conta
    de ``availability_dates``). ``next_days``: os próximos dias em que a casa
    opera, DEPOIS de hoje, em ordem. ``max_date``: o último dia que a casa aceita
    encomenda (``max_preorder_days``), teto do "Outro dia".
    """

    today: date
    today_open: bool
    next_days: tuple[date, ...]
    max_date: date
    closed_weekdays: tuple[int, ...]


def menu_days(max_preorder_days: int, *, count: int = 4, now: datetime | None = None) -> MenuDays | None:
    """Os dias do "Para quando?": hoje (se ainda dá) e os ``count`` próximos dias operantes.

    Mesmas fontes do checkout: ``business_calendar`` (expediente, feriado,
    férias) e a grade de hoje (``fulfillment_window``). Só lê. ``None`` se a
    leitura falhar: a tela não oferece dia que ninguém conferiu.
    """
    try:
        from shopman.shop.services import business_calendar, fulfillment_window

        today = fulfillment_window._local_today(now=now)
        dates = business_calendar.available_dates(
            max_count=count + 1, horizon_days=max_preorder_days, now=now,
        )
        today_open = today in dates and bool(fulfillment_window.delivery_windows_for(today, now=now))
        return MenuDays(
            today=today,
            today_open=today_open,
            next_days=tuple(day for day in dates if day > today)[:count],
            max_date=today + timedelta(days=max(0, max_preorder_days)),
            closed_weekdays=tuple(business_calendar.closed_weekdays()),
        )
    except Exception:
        logger.debug("checkout_projection_menu_days_failed", exc_info=True)
        return None


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
