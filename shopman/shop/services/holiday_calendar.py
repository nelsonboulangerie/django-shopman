"""Upcoming Brazilian holidays for the operation calendar.

This module only proposes dates to the operator.  It never closes the shop on
its own: the decision remains in ``Shop.defaults["closed_dates"]`` and the
business calendar keeps reading that canonical list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, order=True)
class HolidaySuggestion:
    day: date
    label: str
    scope: str = "national"


_NATIONAL_FIXED = (
    (1, 1, "Confraternização Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia Mundial do Trabalho"),
    (9, 7, "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (11, 20, "Dia Nacional de Zumbi e da Consciência Negra"),
    (12, 25, "Natal"),
)


def official_brazil_holidays(year: int) -> tuple[HolidaySuggestion, ...]:
    """Return federal holidays whose calendar date is defined by law.

    State and municipal holidays vary by tenant and therefore come from the
    optional ``defaults.holiday_calendar.regional`` configuration instead of
    being guessed from the deployment location.
    """

    fixed = [
        HolidaySuggestion(date(year, month, day), label)
        for month, day, label in _NATIONAL_FIXED
    ]
    fixed.append(HolidaySuggestion(_easter_sunday(year) - timedelta(days=2), "Paixão de Cristo"))
    return tuple(sorted(fixed))


def _easter_sunday(year: int) -> date:
    """Gregorian computus, used only to place the national Good Friday holiday."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def configured_regional_holidays(defaults: dict | None) -> tuple[HolidaySuggestion, ...]:
    """Read explicit state/city suggestions from tenant configuration."""

    calendar = (defaults or {}).get("holiday_calendar")
    if not isinstance(calendar, dict):
        return ()
    raw_entries = calendar.get("regional")
    if not isinstance(raw_entries, list):
        return ()

    suggestions: list[HolidaySuggestion] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        try:
            day = date.fromisoformat(str(raw.get("date") or ""))
        except ValueError:
            continue
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        scope = str(raw.get("scope") or "regional").strip()
        if scope not in {"state", "city", "regional"}:
            scope = "regional"
        suggestions.append(HolidaySuggestion(day, label, scope))
    return tuple(sorted(suggestions))


def upcoming_holidays(
    *,
    start: date,
    end: date,
    defaults: dict | None = None,
) -> tuple[HolidaySuggestion, ...]:
    """Return unique official/configured holidays inside an inclusive window."""

    candidates: list[HolidaySuggestion] = []
    for year in range(start.year, end.year + 1):
        candidates.extend(official_brazil_holidays(year))
    candidates.extend(configured_regional_holidays(defaults))

    by_day: dict[date, HolidaySuggestion] = {}
    for candidate in sorted(candidates):
        if start <= candidate.day <= end:
            by_day[candidate.day] = candidate
    return tuple(by_day[day] for day in sorted(by_day))


def decision_for_day(day: date, closed_dates: list | tuple | None) -> str:
    """Return the operator decision already stored for ``day``."""

    for entry in closed_dates or ():
        if not isinstance(entry, dict) or str(entry.get("date") or "") != day.isoformat():
            continue
        if entry.get("closed") is False:
            return "special" if entry.get("open") and entry.get("close") else "open"
        return "closed"
    return "pending"
