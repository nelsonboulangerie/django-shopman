"""Honest platform/general delivery summaries derived only from the ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementDeliveryState,
    AnnouncementStatus,
    DeliveryTarget,
    MarketingOutbox,
)

_TARGET_STATES = tuple(value for value, _label in DeliveryTarget.State.choices)
_ACTIVE_TARGET_STATES = {
    DeliveryTarget.State.PLANNED,
    DeliveryTarget.State.QUEUED,
    DeliveryTarget.State.SENDING,
    DeliveryTarget.State.FAILED_RETRYABLE,
}
_SUCCESS_TARGET_STATES = {
    DeliveryTarget.State.ACCEPTED,
    DeliveryTarget.State.CONFIRMED,
}
_TERMINAL_AGGREGATE_STATES = {
    AnnouncementDeliveryState.SUCCEEDED,
    AnnouncementDeliveryState.COMPLETED_WITH_FAILURES,
    AnnouncementDeliveryState.UNKNOWN,
    AnnouncementDeliveryState.CANCELLED,
    AnnouncementDeliveryState.EXPIRED,
    AnnouncementDeliveryState.LEGACY_UNTRACKED,
}


@dataclass(frozen=True, slots=True)
class PlatformDeliverySummary:
    platform: str
    state: str
    counts: dict[str, int]
    targets_total: int
    fanout_expected: int
    fanout_materialized: int
    lanes_total: int
    lanes_complete: int

    @property
    def accepted_unconfirmed(self) -> int:
        return self.counts[DeliveryTarget.State.ACCEPTED]

    @property
    def confirmed(self) -> int:
        return self.counts[DeliveryTarget.State.CONFIRMED]


@dataclass(frozen=True, slots=True)
class DeliverySummary:
    announcement_id: int
    state: str
    counts: dict[str, int]
    targets_total: int
    fanout_expected: int
    fanout_materialized: int
    platforms: tuple[PlatformDeliverySummary, ...]

    @property
    def counts_close(self) -> bool:
        return sum(self.counts.values()) == self.targets_total


def delivery_summary(announcement_id: int) -> DeliverySummary:
    """Return one mathematically closed snapshot; legacy JSON is never read."""

    announcement = Announcement.objects.only(
        "pk",
        "status",
        "platforms",
        "delivery_state",
    ).get(pk=announcement_id)
    lanes = list(
        MarketingOutbox.objects.filter(announcement_id=announcement_id).values(
            "platform",
            "state",
            "fanout_expected",
            "fanout_materialized",
            "fanout_completed_at",
        )
    )
    grouped_counts = list(
        DeliveryTarget.objects.filter(announcement_id=announcement_id)
        .values("platform", "state")
        .annotate(total=Count("pk"))
    )
    if not lanes:
        state = (
            AnnouncementDeliveryState.LEGACY_UNTRACKED
            if announcement.delivery_state == AnnouncementDeliveryState.LEGACY_UNTRACKED
            or announcement.status
            in {AnnouncementStatus.PUBLISHED, AnnouncementStatus.FAILED}
            else AnnouncementDeliveryState.NOT_STARTED
        )
        platforms = tuple(
            PlatformDeliverySummary(
                platform=str(platform),
                state=state,
                counts=_empty_counts(),
                targets_total=0,
                fanout_expected=0,
                fanout_materialized=0,
                lanes_total=0,
                lanes_complete=0,
            )
            for platform in dict.fromkeys(announcement.platforms or [])
        )
        return DeliverySummary(
            announcement_id=announcement.pk,
            state=state,
            counts=_empty_counts(),
            targets_total=0,
            fanout_expected=0,
            fanout_materialized=0,
            platforms=platforms,
        )

    counts_by_platform: dict[str, dict[str, int]] = {}
    for entry in grouped_counts:
        counts_by_platform.setdefault(entry["platform"], _empty_counts())[
            entry["state"]
        ] = entry["total"]
    lanes_by_platform: dict[str, list[dict]] = {}
    for lane in lanes:
        lanes_by_platform.setdefault(lane["platform"], []).append(lane)

    platform_summaries = []
    for platform in sorted(lanes_by_platform):
        platform_lanes = lanes_by_platform[platform]
        counts = counts_by_platform.get(platform, _empty_counts())
        platform_summaries.append(
            PlatformDeliverySummary(
                platform=platform,
                state=_platform_state(platform_lanes, counts),
                counts=counts,
                targets_total=sum(counts.values()),
                fanout_expected=sum(lane["fanout_expected"] for lane in platform_lanes),
                fanout_materialized=sum(
                    lane["fanout_materialized"] for lane in platform_lanes
                ),
                lanes_total=len(platform_lanes),
                lanes_complete=sum(
                    lane["fanout_completed_at"] is not None for lane in platform_lanes
                ),
            )
        )

    total_counts = _empty_counts()
    for platform in platform_summaries:
        for state, count in platform.counts.items():
            total_counts[state] += count
    return DeliverySummary(
        announcement_id=announcement.pk,
        state=_general_state(tuple(item.state for item in platform_summaries)),
        counts=total_counts,
        targets_total=sum(total_counts.values()),
        fanout_expected=sum(item.fanout_expected for item in platform_summaries),
        fanout_materialized=sum(item.fanout_materialized for item in platform_summaries),
        platforms=tuple(platform_summaries),
    )


def refresh_announcement_delivery(
    announcement_id: int,
    *,
    now: datetime | None = None,
) -> DeliverySummary:
    """Persist only the derived state marker; counters remain query-derived."""

    clock = _aware_now(now)
    summary = delivery_summary(announcement_id)
    with transaction.atomic():
        announcement = Announcement.objects.select_for_update().get(pk=announcement_id)
        previous_state = announcement.delivery_state
        announcement.delivery_state = summary.state
        announcement.delivery_state_updated_at = clock
        if summary.state in _TERMINAL_AGGREGATE_STATES:
            if previous_state != summary.state or announcement.delivery_settled_at is None:
                announcement.delivery_settled_at = clock
            if announcement.status not in {
                AnnouncementStatus.CANCELLED,
                AnnouncementStatus.EXPIRED,
                AnnouncementStatus.REJECTED,
            }:
                announcement.status = AnnouncementStatus.SETTLED
        else:
            announcement.delivery_settled_at = None
            if (
                summary.state
                in {
                    AnnouncementDeliveryState.FANOUT_PENDING,
                    AnnouncementDeliveryState.DELIVERING,
                }
                and announcement.status
                in {
                    AnnouncementStatus.APPROVED,
                    AnnouncementStatus.PUBLISHED,
                    AnnouncementStatus.FAILED,
                    AnnouncementStatus.SETTLED,
                }
            ):
                announcement.status = AnnouncementStatus.PUBLISHING
        announcement.save(update_fields=[
            "status",
            "delivery_state",
            "delivery_state_updated_at",
            "delivery_settled_at",
        ])
    return summary


def schedule_delivery_refresh(announcement_id: int) -> None:
    """Refresh after the state mutation commits, without risking its outcome."""

    transaction.on_commit(
        lambda: refresh_announcement_delivery(announcement_id),
        robust=True,
    )


def _platform_state(lanes: list[dict], counts: dict[str, int]) -> str:
    if counts[DeliveryTarget.State.UNKNOWN]:
        return AnnouncementDeliveryState.UNKNOWN
    if any(
        lane["state"] == MarketingOutbox.State.DISPATCHED
        and lane["fanout_completed_at"] is None
        for lane in lanes
    ):
        return AnnouncementDeliveryState.FANOUT_PENDING

    targets_total = sum(counts.values())
    has_active_target = any(counts[state] for state in _ACTIVE_TARGET_STATES)
    has_open_lane = any(
        lane["state"] in {MarketingOutbox.State.PENDING, MarketingOutbox.State.CLAIMED}
        for lane in lanes
    )
    if has_active_target or has_open_lane:
        return (
            AnnouncementDeliveryState.DELIVERING
            if targets_total
            else AnnouncementDeliveryState.NOT_STARTED
        )
    if any(lane["state"] == MarketingOutbox.State.FAILED for lane in lanes):
        return AnnouncementDeliveryState.COMPLETED_WITH_FAILURES
    if not targets_total:
        if lanes and all(lane["state"] == MarketingOutbox.State.CANCELLED for lane in lanes):
            return AnnouncementDeliveryState.CANCELLED
        return AnnouncementDeliveryState.COMPLETED_WITH_FAILURES
    if sum(counts[state] for state in _SUCCESS_TARGET_STATES) == targets_total:
        return AnnouncementDeliveryState.SUCCEEDED
    if counts[DeliveryTarget.State.CANCELLED] == targets_total:
        return AnnouncementDeliveryState.CANCELLED
    if counts[DeliveryTarget.State.EXPIRED] == targets_total:
        return AnnouncementDeliveryState.EXPIRED
    return AnnouncementDeliveryState.COMPLETED_WITH_FAILURES


def _general_state(states: tuple[str, ...]) -> str:
    if AnnouncementDeliveryState.UNKNOWN in states:
        return AnnouncementDeliveryState.UNKNOWN
    if AnnouncementDeliveryState.FANOUT_PENDING in states:
        return AnnouncementDeliveryState.FANOUT_PENDING
    active = {
        AnnouncementDeliveryState.NOT_STARTED,
        AnnouncementDeliveryState.DELIVERING,
    }
    if any(state in active for state in states):
        return (
            AnnouncementDeliveryState.NOT_STARTED
            if all(state == AnnouncementDeliveryState.NOT_STARTED for state in states)
            else AnnouncementDeliveryState.DELIVERING
        )
    if states and all(state == AnnouncementDeliveryState.SUCCEEDED for state in states):
        return AnnouncementDeliveryState.SUCCEEDED
    if states and all(state == AnnouncementDeliveryState.CANCELLED for state in states):
        return AnnouncementDeliveryState.CANCELLED
    if states and all(state == AnnouncementDeliveryState.EXPIRED for state in states):
        return AnnouncementDeliveryState.EXPIRED
    return AnnouncementDeliveryState.COMPLETED_WITH_FAILURES


def _empty_counts() -> dict[str, int]:
    return dict.fromkeys(_TARGET_STATES, 0)


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing delivery aggregate requires an aware clock.")
    return value
