"""Canonical wall-clock handling for Marketing.

The operator chooses a wall time in the shop timezone, while queues and database
rows need one unambiguous instant.  This module is the only bridge between those
two representations.  It deliberately rejects DST gaps and requires an explicit
fold for repeated wall times; silently normalising either would publish at a time
the operator never chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

QUIET_HOURS_START = time(20, 0)
QUIET_HOURS_END = time(8, 0)


@dataclass(frozen=True, slots=True)
class DeliveryWindow:
    allowed: bool
    local: datetime
    next_allowed_at: datetime | None


def configured_timezone_name() -> str:
    """Return the named timezone used by Marketing projections and commands."""

    candidate = str(getattr(settings, "TIME_ZONE", "") or "").strip()
    try:
        ZoneInfo(candidate)
    except (ValueError, ZoneInfoNotFoundError):
        return "UTC"
    return candidate


def zone(timezone_name: str) -> ZoneInfo:
    candidate = str(timezone_name or "").strip()
    try:
        return ZoneInfo(candidate)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("unknown_timezone") from exc


def require_configured_timezone(timezone_name: str) -> str:
    """Reject a caller-selected zone; the backend owns the shop timezone."""

    candidate = str(timezone_name or "").strip()
    try:
        zone(candidate)
    except ValueError as exc:
        raise ValueError("unknown_timezone") from exc
    if candidate != configured_timezone_name():
        raise ValueError("timezone_mismatch")
    return candidate


def wall_candidates(value: datetime, *, timezone_name: str) -> tuple[datetime, ...]:
    """Return the real instants represented by a naive wall time (zero, one or two)."""

    if timezone.is_aware(value):
        raise ValueError("wall_time_must_be_naive")
    target_zone = zone(timezone_name)
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        candidate = value.replace(tzinfo=target_zone, fold=fold)
        roundtrip = candidate.astimezone(UTC).astimezone(target_zone)
        if roundtrip.replace(tzinfo=None) != value:
            continue
        candidates[candidate.astimezone(UTC)] = candidate
    return tuple(candidates[key] for key in sorted(candidates))


def resolve_wall_time(
    value: datetime,
    *,
    timezone_name: str,
    fold: str = "",
) -> datetime:
    """Resolve a wall time without guessing across a DST transition."""

    candidates = wall_candidates(value, timezone_name=timezone_name)
    if not candidates:
        raise ValueError("nonexistent_local_time")
    if len(candidates) == 1:
        return candidates[0]
    if fold == "earlier":
        return candidates[0]
    if fold == "later":
        return candidates[-1]
    raise ValueError("ambiguous_local_time")


def validate_named_instant(value: datetime, *, timezone_name: str) -> datetime:
    """Ensure an offset-bearing ISO value agrees with its named timezone."""

    if timezone.is_naive(value):
        raise ValueError("naive_scheduled_time")
    target_zone = zone(timezone_name)
    localized = value.astimezone(target_zone)
    if (
        localized.replace(tzinfo=None) != value.replace(tzinfo=None)
        or localized.utcoffset() != value.utcoffset()
    ):
        raise ValueError("timezone_offset_mismatch")
    return localized


def local(value: datetime, *, timezone_name: str) -> datetime:
    if timezone.is_naive(value):
        raise ValueError("naive_instant")
    return value.astimezone(zone(timezone_name))


def delivery_window(value: datetime, *, timezone_name: str) -> DeliveryWindow:
    """Apply the approved 20:00–08:00 direct-message quiet-hours policy."""

    localized = local(value, timezone_name=timezone_name)
    wall = localized.timetz().replace(tzinfo=None)
    if QUIET_HOURS_END <= wall < QUIET_HOURS_START:
        return DeliveryWindow(True, localized, None)

    opening_day: date
    if wall >= QUIET_HOURS_START:
        opening_day = localized.date() + timedelta(days=1)
    else:
        opening_day = localized.date()
    opening = resolve_wall_time(
        datetime.combine(opening_day, QUIET_HOURS_END),
        timezone_name=timezone_name,
        fold="earlier",
    )
    return DeliveryWindow(False, localized, opening)


def schedule_timezone(schedule: dict | None) -> str:
    """Named zone carried by new schedules; legacy rows use the configured zone."""

    if isinstance(schedule, dict) and schedule.get("timezone"):
        candidate = str(schedule["timezone"]).strip()
        zone(candidate)
        return candidate
    return configured_timezone_name()
