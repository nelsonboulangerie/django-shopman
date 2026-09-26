"""Janela automática do menuboard em torno do expediente da loja.

O canal continua sendo ligado/desligado pelo toggle ``Ativo``. Este módulo resolve
uma segunda decisão, exclusiva das TVs: quando o canal está ativo e o modo
automático está ligado, o cardápio aparece 15 minutos antes da abertura e entra
em descanso 15 minutos depois do fechamento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

AUTOMATIC_LEAD_MINUTES = 15
AUTOMATIC_LAG_MINUTES = 15
MAX_IDLE_MESSAGE_LENGTH = 240
DEFAULT_IDLE_MESSAGE = "Atendimento encerrado. Voltamos no próximo horário da loja."


@dataclass(frozen=True)
class MenuboardAutomaticState:
    enabled: bool
    is_sleeping: bool
    idle_messages: tuple[str, ...]
    state_line: str
    wakes_at: datetime | None = None
    sleeps_at: datetime | None = None


def automatic_settings(channel) -> tuple[bool, tuple[str, ...]]:
    """Config normalizada; dado legado ou torto nunca apaga a TV."""
    display = (getattr(channel, "config", None) or {}).get("display") or {}
    raw = display.get("automatic")
    raw = raw if isinstance(raw, dict) else {}
    enabled = raw.get("enabled") is True
    values = raw.get("idle_messages")
    if not isinstance(values, list):
        values = [raw.get("idle_message")]
    messages = normalize_idle_messages(values)
    return enabled, messages


def normalize_idle_messages(values) -> tuple[str, ...]:
    """Aceita até duas frases; configuração legada de uma frase segue válida."""
    raw_values = values if isinstance(values, (list, tuple)) else [values]
    messages: list[str] = []
    for value in raw_values[:2]:
        message = " ".join(str(value or "").split())
        if message and message not in messages:
            messages.append(message)
    return tuple(messages or [DEFAULT_IDLE_MESSAGE])


def resolve_menuboard_automatic_state(
    channel,
    *,
    now: datetime | None = None,
) -> MenuboardAutomaticState:
    """Resolve conteúdo versus descanso usando o calendário canônico da loja.

    Sem grade semanal configurada, falha aberto: a TV continua com o cardápio.
    Feriados e fechamentos excepcionais entram em descanso e usam a próxima
    abertura conhecida como instante de retorno.
    """
    from shopman.shop.services import business_calendar

    enabled, messages = automatic_settings(channel)
    if not enabled:
        return MenuboardAutomaticState(
            enabled=False,
            is_sleeping=False,
            idle_messages=messages,
            state_line="Automático desligado: conteúdo contínuo.",
        )

    shop = getattr(channel, "shop", None)
    if shop is None:
        from shopman.shop.models import Shop

        shop = Shop.load()

    if not business_calendar.has_regular_hours(shop=shop):
        return MenuboardAutomaticState(
            enabled=True,
            is_sleeping=False,
            idle_messages=messages,
            state_line="Automático: horário da loja não configurado; conteúdo contínuo.",
        )

    instant = now or timezone.now()
    if not timezone.is_aware(instant):
        instant = timezone.make_aware(instant)
    local_now = timezone.localtime(instant, timezone=business_calendar.shop_timezone(shop=shop))
    window = business_calendar.selling_hours_for(local_now.date(), shop=shop)
    operates_today = business_calendar.is_open_on(local_now.date(), shop=shop)

    visible_start = None
    visible_end = None
    if operates_today and window is not None:
        opens_at, closes_at = window
        visible_start = datetime.combine(local_now.date(), opens_at, tzinfo=local_now.tzinfo) - timedelta(
            minutes=AUTOMATIC_LEAD_MINUTES
        )
        visible_end = datetime.combine(local_now.date(), closes_at, tzinfo=local_now.tzinfo) + timedelta(
            minutes=AUTOMATIC_LAG_MINUTES
        )
        if visible_start <= local_now < visible_end:
            return MenuboardAutomaticState(
                enabled=True,
                is_sleeping=False,
                idle_messages=messages,
                state_line=f"Automático: conteúdo visível até {_hour(visible_end)}.",
                wakes_at=visible_start,
                sleeps_at=visible_end,
            )

    calendar_state = business_calendar.current_business_state(now=local_now, shop=shop)
    next_open = calendar_state.next_open_at
    wakes_at = next_open - timedelta(minutes=AUTOMATIC_LEAD_MINUTES) if next_open else None
    state_line = "Automático: descanso de tela."
    if wakes_at:
        state_line = f"Automático: descanso até {_moment(wakes_at, now=local_now)}."
    return MenuboardAutomaticState(
        enabled=True,
        is_sleeping=True,
        idle_messages=messages,
        state_line=state_line,
        wakes_at=wakes_at,
        sleeps_at=visible_end,
    )


def _hour(value: datetime) -> str:
    return f"{value.hour}h{value.minute:02d}" if value.minute else f"{value.hour}h"


def _moment(value: datetime, *, now: datetime) -> str:
    if value.date() == now.date():
        day = "hoje"
    elif value.date() == now.date() + timedelta(days=1):
        day = "amanhã"
    else:
        weekdays = ("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom.")
        day = f"{weekdays[value.weekday()]} {value.day}/{value.month}"
    return f"{day} às {_hour(value)}"
