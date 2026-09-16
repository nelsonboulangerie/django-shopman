"""iFood preparation times: preserve the contract and never guess a timezone."""

from datetime import UTC, date, datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _parse(value) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else parse_datetime(value) if isinstance(value, str) else None
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed.astimezone(UTC)


def map_schedule(raw: dict) -> dict:
    """Normalize valid dates to UTC; retain malformed input for diagnosis.

    The root preparation time and ``schedule`` window are authoritative.
    ``scheduled`` is a documented alternative used only for missing fields.
    A malformed authoritative value must never fall back to another time.
    """
    schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    fallback = raw.get("scheduled") if isinstance(raw.get("scheduled"), dict) else {}
    values = {
        "preparation_start_at": raw.get("preparationStartDateTime", fallback.get("preparationStartDateTime")),
        "delivery_start_at": schedule.get("deliveryDateTimeStart", fallback.get("deliveryDateTimeStart")),
        "delivery_end_at": schedule.get("deliveryDateTimeEnd", fallback.get("deliveryDateTimeEnd")),
    }
    result = {key: parsed.isoformat() if (parsed := _parse(value)) else value for key, value in values.items()}
    if "schedule" in raw and not isinstance(raw["schedule"], dict):
        result["invalid_window"] = True
    return result


def is_scheduled(order) -> bool:
    block = (getattr(order, "data", None) or {}).get("ifood") or {}
    return getattr(order, "channel_ref", "") == "ifood" and str(block.get("order_timing") or "").upper() == "SCHEDULED"


def _validate_schedule(block) -> datetime | None:
    if not isinstance(block, dict) or block.get("invalid_window"):
        return None
    start = _parse(block.get("preparation_start_at"))
    if start is None:
        return None
    window_start, window_end = block.get("delivery_start_at"), block.get("delivery_end_at")
    if window_start is not None or window_end is not None:
        first, last = _parse(window_start), _parse(window_end)
        if first is None or last is None or first > last or start > first:
            return None
    return start


def delivery_date_from_payload(schedule: dict) -> date | None:
    """Stock commitment date from the authoritative delivery window, never duration."""
    if _validate_schedule(schedule) is None:
        return None
    start = _parse(schedule.get("delivery_start_at"))
    return timezone.localtime(start).date() if start else None


def _validated_start(order) -> datetime | None:
    return _validate_schedule(((order.data or {}).get("ifood") or {}).get("schedule") or {})


def defer_stock_hold(order) -> bool:
    """No window means no inferred stock day; reserve only when preparation is due."""
    if not is_scheduled(order) or is_due(order):
        return False
    schedule = ((order.data or {}).get("ifood") or {}).get("schedule") or {}
    return delivery_date_from_payload(schedule) is None


def preparation_start(order) -> datetime | None:
    """Validated UTC preparation timestamp; None for absent/invalid schedules."""
    return _validated_start(order) if is_scheduled(order) else None


def block_reason(order, *, now: datetime | None = None) -> str:
    """Human reason preventing physical work; confirmation remains allowed."""
    if not is_scheduled(order):
        return ""
    start = _validated_start(order)
    if start is None:
        return "Horário de preparo do pedido agendado iFood ausente ou inválido. Confira o agendamento antes de preparar."
    current = _parse(now) if now is not None else timezone.now()
    if current is None:
        return "Não foi possível validar o horário atual para preparar o pedido iFood."
    if current < start:
        display = timezone.localtime(start).strftime("%d/%m/%Y às %H:%M")
        return f"Pedido agendado no iFood: aguarde o início do preparo em {display}."
    return ""


def is_due(order, *, now: datetime | None = None) -> bool:
    return not block_reason(order, now=now)
