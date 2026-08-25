"""Operational calendar helpers for customer-facing promises and automation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

logger = logging.getLogger(__name__)

DAY_NAMES_PT = {
    "monday": "segunda",
    "tuesday": "terça",
    "wednesday": "quarta",
    "thursday": "quinta",
    "friday": "sexta",
    "saturday": "sábado",
    "sunday": "domingo",
}
DAY_ORDER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class BusinessCalendarState:
    """Resolved operational state for one instant."""

    is_open: bool
    opens_at: str | None
    closes_at: str | None
    message: str
    next_open_at: datetime | None = None
    closed_reason: str = ""
    closure_source: str = ""
    resolved_at: datetime | None = None

    @property
    def is_closed(self) -> bool:
        return not self.is_open


def current_business_state(*, now: datetime | None = None, shop=None) -> BusinessCalendarState:
    """Return whether the shop is operational at ``now`` and when it opens next.

    The model is intentionally simple and canonical:
    regular weekly hours are stored in ``Shop.opening_hours``; closures such as
    holidays and collective vacations are date exceptions in
    ``Shop.defaults["closed_dates"]``.
    """
    shop = _load_shop(shop)
    if not shop:
        return BusinessCalendarState(is_open=True, opens_at=None, closes_at=None, message="")

    local_now = _localtime_for_shop(now or timezone.now(), shop)
    closed, closed_label, closure_source = closed_date_for(local_now.date(), _closed_dates(shop))
    day_window = _day_window(shop, local_now.date())
    next_open_at = _next_open_at(shop, local_now=local_now)

    if closed:
        message = f"Fechado hoje: {closed_label}" if closed_label else "Fechado hoje"
        return BusinessCalendarState(
            is_open=False,
            opens_at=None,
            closes_at=None,
            message=message,
            next_open_at=next_open_at,
            closed_reason=closed_label,
            closure_source=closure_source,
            resolved_at=local_now,
        )

    if day_window is None:
        if not _has_regular_hours(shop):
            return BusinessCalendarState(is_open=True, opens_at=None, closes_at=None, message="", resolved_at=local_now)
        return BusinessCalendarState(
            is_open=False,
            opens_at=None,
            closes_at=None,
            message="Fechado hoje",
            next_open_at=next_open_at,
            closure_source="weekly",
            resolved_at=local_now,
        )

    opens_at, closes_at = day_window
    current_time = local_now.time()
    if opens_at <= current_time < closes_at:
        return BusinessCalendarState(
            is_open=True,
            opens_at=_fmt_hhmm(opens_at),
            closes_at=_fmt_hhmm(closes_at),
            message=f"Aberto até {_fmt_hour(closes_at)}",
            next_open_at=None,
            resolved_at=local_now,
        )

    if current_time < opens_at:
        open_dt = datetime.combine(local_now.date(), opens_at, tzinfo=local_now.tzinfo)
        return BusinessCalendarState(
            is_open=False,
            opens_at=_fmt_hhmm(opens_at),
            closes_at=_fmt_hhmm(closes_at),
            message=f"Fechado. Abrimos às {_fmt_hour(opens_at)}",
            next_open_at=open_dt,
            closure_source="before_open",
            resolved_at=local_now,
        )

    return BusinessCalendarState(
        is_open=False,
        opens_at=_fmt_hhmm(opens_at),
        closes_at=_fmt_hhmm(closes_at),
        message="Fechado",
        next_open_at=next_open_at,
        closure_source="after_close",
        resolved_at=local_now,
    )


def next_operational_deadline(
    *,
    timeout: timedelta,
    now: datetime | None = None,
    shop=None,
) -> tuple[datetime | None, BusinessCalendarState]:
    """Return the truthful deadline for an operator timeout.

    When the shop is closed, the timeout starts at the next known opening. If
    there is no configured future opening, no automated deadline is returned.
    """
    local_now = now or timezone.now()
    state = current_business_state(now=local_now, shop=shop)
    if state.is_open:
        return local_now + timeout, state
    if state.next_open_at:
        return state.next_open_at + timeout, state
    return None, state


def store_review_deferred_state(
    order,
    *,
    state: BusinessCalendarState | None = None,
) -> BusinessCalendarState | None:
    """O calendário quando o pedido aguarda a loja E a loja está fechada.

    Uma pergunta, uma resposta. O acompanhamento e a tela de pagamento precisam
    dizer a MESMA coisa sobre quando a loja vai olhar o pedido — e decidiam isso
    cada um por conta. Só o acompanhamento consultava o calendário, então quem
    ficava na tela de pagamento lia "estamos conferindo a disponibilidade" com a
    padaria fechada, enquanto o aceite automático só venceria na abertura
    (``next_operational_deadline``, que conta o prazo em tempo de loja aberta).

    Devolve o estado (para a superfície formar a frase da próxima abertura) ou
    ``None`` quando a loja já está olhando.
    """
    if str(getattr(order, "status", "") or "") != "new":
        return None
    state = state or current_business_state()
    return state if state.is_closed else None


def is_open_on(day: date, *, shop=None) -> bool:
    """Whether the shop operates on ``day`` (regular weekday + sem exceção).

    Considera o horário semanal (``Shop.opening_hours``) e as exceções de
    fechamento (feriados e férias coletivas em ``closed_dates``, inclusive
    ranges ``from/to``). Sem agenda configurada → degrada para aberto (não
    bloqueia deployments sem horário).
    """
    shop = _load_shop(shop)
    if not shop or not _has_regular_hours(shop):
        return True
    if closed_date_for(day, _closed_dates(shop))[0]:
        return False
    return _day_window(shop, day) is not None


def selling_hours_for(day: date, *, shop=None) -> tuple[time, time] | None:
    """O par (abre, fecha) declarado para o dia da semana de ``day``.

    Devolve None quando não há horário configurado ou quando o dia não tem
    expediente regular — quem consome decide o que fazer com a ausência, em vez
    de receber um expediente inventado.
    """
    shop = _load_shop(shop)
    if not shop:
        return None
    return _day_window(shop, day)


def closed_weekdays(*, shop=None) -> list[int]:
    """Índices de dia da semana (0=segunda … 6=domingo) sem expediente regular."""
    shop = _load_shop(shop)
    if not shop or not _has_regular_hours(shop):
        return []
    hours = getattr(shop, "opening_hours", {}) or {}
    out: list[int] = []
    for index, name in enumerate(DAY_ORDER):
        raw = hours.get(name)
        if not (isinstance(raw, dict) and raw.get("open") and raw.get("close")):
            out.append(index)
    return out


def available_dates(*, max_count: int = 3, horizon_days: int = 30, now: datetime | None = None, shop=None) -> list[date]:
    """As próximas ``max_count`` datas em que a loja realmente opera.

    Pula dias da semana fechados e exceções (feriados/férias) — nunca devolve
    um dia fechado. Fonte da verdade para as opções de data do checkout.
    """
    shop = _load_shop(shop)
    base = now or timezone.now()
    local = _localtime_for_shop(base, shop) if shop else base
    today = local.date() if isinstance(local, datetime) else local
    # Hoje só conta se a loja ainda não fechou — depois do expediente, a próxima
    # data fulfillável é o próximo dia operante (eixo de HORA, par do is_open_on).
    today_done = current_business_state(now=base, shop=shop).closure_source == "after_close"
    out: list[date] = []
    for offset in range(0, max(0, horizon_days) + 1):
        candidate = today + timedelta(days=offset)
        if offset == 0 and today_done:
            continue
        if is_open_on(candidate, shop=shop):
            out.append(candidate)
            if len(out) >= max_count:
                break
    return out


#: De quanto em quanto tempo o balcão combina uma entrega. Meia hora é a menor
#: promessa que a casa consegue cumprir com um entregador só, e é a granularidade
#: que o dono pediu — mais fino vira compromisso que a rua não honra.
DELIVERY_SLOT_MINUTES = 30

#: Antecedência mínima entre AGORA e o começo do primeiro horário combinável.
#: Sem ela o balcão ofereceria "13:00" às 12:58 e o pedido nasceria atrasado.
DELIVERY_SLOT_LEAD_MINUTES = 30


def delivery_slots_for(
    day: date,
    *,
    now: datetime | None = None,
    shop=None,
) -> list[dict]:
    """As janelas de meia hora combináveis para entregar em ``day``.

    Fatia o EXPEDIENTE do dia (``selling_hours_for`` — a mesma fonte que a loja e
    o gestor leem) em intervalos de ``DELIVERY_SLOT_MINUTES``. Para HOJE, corta o
    que já passou e mais ``DELIVERY_SLOT_LEAD_MINUTES`` de antecedência: horário
    que não dá para cumprir não é oferta, é promessa quebrada no ato.

    Devolve ``[{"ref": "14:00-14:30", "label": "14:00 às 14:30"}, …]``. Lista
    vazia significa "não há janela neste dia" — dia fechado, feriado, ou o
    expediente de hoje já acabou. Quem consome decide o que dizer; aqui não se
    inventa expediente (é a mesma promessa de ``selling_hours_for``).

    O ``ref`` é o próprio par de horas porque ele já é estável e legível: vai
    para ``Order.data["delivery_time_slot"]``, e um pedido antigo continua se
    explicando sozinho mesmo que o expediente da casa mude depois.
    """
    window = selling_hours_for(day, shop=shop)
    if window is None or not is_open_on(day, shop=shop):
        return []
    opens_at, closes_at = window

    shop = _load_shop(shop)
    base = now or timezone.now()
    local = _localtime_for_shop(base, shop) if shop else base
    today = local.date() if isinstance(local, datetime) else local
    earliest: time | None = None
    if day == today and isinstance(local, datetime):
        cutoff = local + timedelta(minutes=DELIVERY_SLOT_LEAD_MINUTES)
        earliest = cutoff.time() if cutoff.date() == day else None
        if cutoff.date() > day:
            return []  # a antecedência já empurrou para depois da meia-noite

    slots: list[dict] = []
    cursor = datetime.combine(day, opens_at)
    end = datetime.combine(day, closes_at)
    step = timedelta(minutes=DELIVERY_SLOT_MINUTES)
    while cursor + step <= end:
        starts = cursor.time()
        finishes = (cursor + step).time()
        if earliest is None or starts >= earliest:
            slots.append({
                "ref": f"{_fmt_hhmm(starts)}-{_fmt_hhmm(finishes)}",
                "label": f"{_fmt_hhmm(starts)} às {_fmt_hhmm(finishes)}",
            })
        cursor += step
    return slots


def closed_date_for(day: date, closed_dates: list | tuple | None) -> tuple[bool, str, str]:
    """Return whether ``day`` is covered by a closure exception."""
    for entry in closed_dates or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if entry.get("closed") is False:
            continue
        if "date" in entry:
            try:
                if day == date.fromisoformat(str(entry["date"])):
                    return True, label, "date"
            except ValueError:
                continue
        if "from" in entry and "to" in entry:
            try:
                starts = date.fromisoformat(str(entry["from"]))
                ends = date.fromisoformat(str(entry["to"]))
            except ValueError:
                continue
            if starts <= day <= ends:
                return True, label, "range"
    return False, "", ""


def format_next_opening(value: datetime | None, *, now: datetime | None = None) -> str:
    """Format a next-opening datetime for compact customer copy."""
    if not value:
        return ""
    tz = value.tzinfo or timezone.get_current_timezone()
    local = timezone.localtime(value, timezone=tz)
    reference = now or timezone.now()
    if not timezone.is_aware(reference):
        reference = timezone.make_aware(reference, timezone=tz)
    today = timezone.localtime(reference, timezone=tz).date()
    tomorrow = today + timedelta(days=1)
    hour = _fmt_hour(local.time())
    if local.date() == today:
        return f"hoje às {hour}"
    if local.date() == tomorrow:
        return f"amanhã às {hour}"
    weekday = DAY_NAMES_PT.get(local.strftime("%A").lower(), local.strftime("%A").lower())
    return f"{weekday} às {hour}"


def _load_shop(shop):
    if shop is not None:
        return shop
    try:
        from shopman.shop.models import Shop

        return Shop.load()
    except Exception:
        logger.debug("business_calendar.load_shop_failed", exc_info=True)
        return None


def _localtime_for_shop(value: datetime, shop) -> datetime:
    if not timezone.is_aware(value):
        value = timezone.make_aware(value)
    tz_name = getattr(shop, "timezone", "") or timezone.get_current_timezone_name()
    if not isinstance(tz_name, str):
        tz_name = timezone.get_current_timezone_name()
    try:
        tz = ZoneInfo(tz_name)
    except (ValueError, ZoneInfoNotFoundError):
        tz = timezone.get_current_timezone()
    return timezone.localtime(value, timezone=tz)


def _closed_dates(shop) -> list:
    defaults = getattr(shop, "defaults", None) or {}
    if not isinstance(defaults, dict):
        return []
    calendar = defaults.get("calendar") if isinstance(defaults.get("calendar"), dict) else {}
    dates = []
    for key in ("closed_dates", "closures", "holidays"):
        value = defaults.get(key)
        if isinstance(value, list):
            dates.extend(value)
    for key in ("closed_dates", "closures", "holidays"):
        value = calendar.get(key)
        if isinstance(value, list):
            dates.extend(value)
    return dates


def _has_regular_hours(shop) -> bool:
    hours = getattr(shop, "opening_hours", None)
    return isinstance(hours, dict) and any(
        isinstance(value, dict) and value.get("open") and value.get("close")
        for value in hours.values()
    )


def _day_window(shop, day: date) -> tuple[time, time] | None:
    hours = getattr(shop, "opening_hours", None)
    if not isinstance(hours, dict) or not hours:
        return None
    weekday = DAY_ORDER[day.weekday()]
    raw = hours.get(weekday)
    if not isinstance(raw, dict):
        return None
    try:
        opens_at = time.fromisoformat(str(raw["open"]))
        closes_at = time.fromisoformat(str(raw["close"]))
    except (KeyError, TypeError, ValueError):
        return None
    if opens_at >= closes_at:
        return None
    return opens_at, closes_at


def _next_open_at(shop, *, local_now: datetime) -> datetime | None:
    if not _has_regular_hours(shop):
        return None
    for offset in range(0, 15):
        candidate_date = local_now.date() + timedelta(days=offset)
        closed, _, _ = closed_date_for(candidate_date, _closed_dates(shop))
        if closed:
            continue
        window = _day_window(shop, candidate_date)
        if window is None:
            continue
        opens_at, closes_at = window
        candidate = datetime.combine(candidate_date, opens_at, tzinfo=local_now.tzinfo)
        if candidate <= local_now:
            if local_now.date() == candidate_date and local_now.time() < closes_at:
                return candidate
            continue
        return candidate
    return None


def _fmt_hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_hour(value: time) -> str:
    if value.minute:
        return f"{value.hour}h{value.minute:02d}"
    return f"{value.hour}h"
