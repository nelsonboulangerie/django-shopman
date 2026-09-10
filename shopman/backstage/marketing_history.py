"""Canonical, cursor-bound filters for the Marketing v2 history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from shopman.shop.models import (
    AnnouncementDeliveryState,
    AnnouncementStatus,
    MarketingOutbox,
)
from shopman.shop.services.marketing_time import configured_timezone_name

HISTORY_OUTCOMES = tuple(AnnouncementDeliveryState.values)
HISTORY_PLATFORMS = ("instagram", "facebook", "google_business", "whatsapp")
HISTORY_ACTORS = ("operator", "automation")
HISTORY_PERIODS = ("today", "7d", "30d", "all")
HISTORY_QUERY_FIELDS = frozenset({
    "actor",
    "cursor",
    "limit",
    "outcome",
    "period",
    "platform",
})


class InvalidHistoryFilter(ValueError):
    """A history filter is unknown or outside its allowlisted vocabulary."""

    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


@dataclass(frozen=True, slots=True)
class MarketingHistoryFilters:
    outcome: str = ""
    platform: str = ""
    actor: str = ""
    period: str = "all"


def parse_history_filters(params) -> MarketingHistoryFilters:
    """Parse a strict filter set; ignored query typos must never hide results."""

    unknown = sorted(set(params.keys()) - HISTORY_QUERY_FIELDS)
    if unknown:
        raise InvalidHistoryFilter(unknown[0])

    values = MarketingHistoryFilters(
        outcome=str(params.get("outcome") or "").strip(),
        platform=str(params.get("platform") or "").strip(),
        actor=str(params.get("actor") or "").strip(),
        period=str(params.get("period") or "all").strip(),
    )
    for field, value, allowed in (
        ("outcome", values.outcome, HISTORY_OUTCOMES),
        ("platform", values.platform, HISTORY_PLATFORMS),
        ("actor", values.actor, HISTORY_ACTORS),
        ("period", values.period, HISTORY_PERIODS),
    ):
        if value and value not in allowed:
            raise InvalidHistoryFilter(field)
    return values


def cursor_collection(base: str, filters: MarketingHistoryFilters) -> str:
    """Bind an opaque cursor to exactly one non-sensitive filter combination."""

    canonical = json.dumps(
        asdict(filters),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"{base}:{digest}"


def apply_history_filters(
    queryset: QuerySet,
    filters: MarketingHistoryFilters,
    *,
    as_of: datetime,
) -> QuerySet:
    """Apply portable SQL filters before cursor pagination and projection."""

    if filters.outcome:
        if filters.outcome == AnnouncementDeliveryState.CANCELLED:
            queryset = queryset.filter(
                Q(status=AnnouncementStatus.CANCELLED)
                | Q(delivery_state=AnnouncementDeliveryState.CANCELLED)
            )
        elif filters.outcome == AnnouncementDeliveryState.EXPIRED:
            queryset = queryset.filter(
                Q(status=AnnouncementStatus.EXPIRED)
                | Q(delivery_state=AnnouncementDeliveryState.EXPIRED)
            )
        else:
            queryset = queryset.filter(delivery_state=filters.outcome)

    if filters.platform:
        lane = MarketingOutbox.objects.filter(
            announcement_id=OuterRef("pk"),
            platform=filters.platform,
        )
        platform_match = Q(_history_platform_lane=True)
        # The bounded JSON positions preserve legacy rows without relying on a
        # backend-specific JSON-array containment operator.
        for index in range(len(HISTORY_PLATFORMS)):
            platform_match |= Q(**{f"platforms__{index}": filters.platform})
        queryset = queryset.annotate(
            _history_platform_lane=Exists(lane)
        ).filter(platform_match)

    if filters.actor == "operator":
        queryset = queryset.filter(
            Q(approved_by__isnull=False) | Q(rejected_by__isnull=False)
        )
    elif filters.actor == "automation":
        queryset = queryset.filter(
            approved_by__isnull=True,
            rejected_by__isnull=True,
        )

    period_start = _period_start(filters.period, as_of=as_of)
    if period_start is not None:
        queryset = queryset.filter(created_at__gte=period_start)
    return queryset


def _period_start(period: str, *, as_of: datetime) -> datetime | None:
    if period == "all":
        return None
    zone = ZoneInfo(configured_timezone_name())
    local_as_of = timezone.localtime(as_of, zone)
    days = {"today": 0, "7d": 6, "30d": 29}[period]
    local_start = datetime.combine(
        local_as_of.date() - timedelta(days=days),
        time.min,
        tzinfo=zone,
    )
    return local_start.astimezone(UTC)
