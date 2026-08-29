from __future__ import annotations

DAY_NAMES_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _shop_status() -> dict:
    """Return shop open/closed status based on Shop.opening_hours.

    Returns dict: {is_open, opens_at, closes_at, message}
    """
    from shopman.shop.projections.shop_status import business_state

    state = business_state()
    return {
        "is_open": state.is_open,
        "label": _status_label(state),
        "opens_at": state.opens_at,
        "closes_at": state.closes_at,
        "message": _status_message(state),
    }


_STATUS_FALLBACKS = {
    "SHOP_STATUS_OPEN": "Aberto agora",
    "SHOP_STATUS_OPEN_UNTIL": "Aberto até",
    "SHOP_STATUS_OPEN_CLOSING_SOON": "Últimos pedidos até",
    "SHOP_STATUS_CLOSED": "Fechado agora",
    "SHOP_STATUS_CLOSED_OPENS_AT": "Fechado agora. Abrimos",
}

_LEGACY_STATUS_COPY = {
    "Aberto. Fecha em": "Últimos pedidos até",
    "Fechado": "Fechado agora",
    "Fechado. Abre às": "Fechado agora. Abrimos",
}


def _status_label(state) -> str:
    """Status badge label — copy owned by the omotenashi registry (``SHOP_STATUS_*``).

    Escapa o genérico fixo pelo conjunto granular do registro: aberto agora,
    aberto até {hora}, últimos pedidos até {hora}, fechado com próxima abertura
    quando o calendário souber, ou fechado agora sem prometer horário.
    """
    if state.is_open:
        closes = _human_time(state.closes_at)
        if not closes:
            return _copy("SHOP_STATUS_OPEN")
        prefix = "SHOP_STATUS_OPEN_CLOSING_SOON" if _closing_soon(state) else "SHOP_STATUS_OPEN_UNTIL"
        return _join_copy(_copy(prefix), closes)

    next_opening = _next_opening_display(state)
    if next_opening:
        return _join_copy(_copy("SHOP_STATUS_CLOSED_OPENS_AT"), next_opening)
    return _copy("SHOP_STATUS_CLOSED")


def _status_message(state) -> str:
    """Normalize calendar messages so full status copy stays client-facing."""
    message = (getattr(state, "message", "") or "").strip()
    if not getattr(state, "is_closed", not getattr(state, "is_open", False)):
        return message

    next_opening = _next_opening_display(state)
    if not next_opening:
        return _LEGACY_STATUS_COPY.get(message, message)

    lower = message.lower()
    if lower.startswith("fechado. abrimos às") or lower == "fechado":
        return f"{_copy('SHOP_STATUS_CLOSED_OPENS_AT')} {next_opening}."
    if "abrimos" not in lower:
        return f"{message}. Abrimos {next_opening}." if message else f"Abrimos {next_opening}."
    return message


def _next_opening_display(state) -> str:
    """Return "hoje às 9h", "amanhã às 9h", "quinta às 9h" or "às 9h"."""
    next_open_at = getattr(state, "next_open_at", None)
    if next_open_at:
        from shopman.shop.projections.shop_status import next_opening_phrase

        phrase = next_opening_phrase(next_open_at, now=getattr(state, "resolved_at", None))
        if phrase:
            return phrase

    if (
        getattr(state, "opens_at", None)
        and getattr(state, "closure_source", "") != "after_close"
        and not getattr(state, "closed_reason", "")
    ):
        opens = _human_time(state.opens_at)
        if opens:
            return f"às {opens}"
    return ""


def _copy(key: str) -> str:
    from shopman.shop.omotenashi import resolve_copy

    raw = (resolve_copy(key, moment="*").message or _STATUS_FALLBACKS.get(key, "")).strip()
    return _LEGACY_STATUS_COPY.get(raw, raw)


def _join_copy(prefix: str, suffix: str) -> str:
    return f"{prefix.rstrip()} {suffix.lstrip()}".strip()


def _closing_soon(state, *, threshold_min: int = 60) -> bool:
    """Whether the shop closes within ``threshold_min`` minutes of resolution."""
    resolved_at = getattr(state, "resolved_at", None)
    if not (state.closes_at and resolved_at):
        return False
    try:
        hour, minute = (int(part) for part in state.closes_at.split(":"))
    except (ValueError, AttributeError):
        return False
    close_dt = resolved_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta_min = (close_dt - resolved_at).total_seconds() / 60
    return 0 < delta_min <= threshold_min


def _human_time(hhmm: str | None) -> str:
    """Format a "HH:MM" clock string as "19h" / "19h30", matching opening hours."""
    if not hhmm or ":" not in hhmm:
        return hhmm or ""
    hour, minute = hhmm.split(":", 1)
    return f"{int(hour)}h" if minute == "00" else f"{int(hour)}h{minute}"


def _format_opening_hours() -> list[dict]:
    """Format Shop.opening_hours into display-ready lines for templates.

    Groups consecutive days with the same hours into ranges.
    Returns list of {label, hours} dicts, e.g.:
      [{"label": "Terça a Sábado", "hours": "7h às 19h"},
       {"label": "Domingo", "hours": "7h às 13h"},
       {"label": "Segunda", "hours": "Fechado"}]
    """
    from shopman.shop.models import Shop

    shop = Shop.load()
    if not shop or not shop.opening_hours:
        return []

    def _fmt_time(t: str) -> str:
        """'06:00' -> '6h', '20:00' -> '20h', '07:30' -> '7h30'."""
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if m:
            return f"{h}h{m:02d}"
        return f"{h}h"

    # Build (day, hours_str) pairs in order
    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = shop.opening_hours.get(day)
        if info and info.get("open") and info.get("close"):
            day_hours.append((day, f"{_fmt_time(info['open'])} às {_fmt_time(info['close'])}"))
        else:
            day_hours.append((day, "Fechado"))

    # Group consecutive days with same hours
    groups: list[tuple[list[str], str]] = []
    for day, hours in day_hours:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    result = []
    for days, hours in groups:
        if len(days) == 1:
            label = DAY_NAMES_PT[days[0]]
        elif len(days) == 2:
            label = f"{DAY_NAMES_PT[days[0]]} e {DAY_NAMES_PT[days[1]]}"
        else:
            label = f"{DAY_NAMES_PT[days[0]]} a {DAY_NAMES_PT[days[-1]]}"
        result.append({"label": label, "hours": hours})

    return result
