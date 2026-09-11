"""Canonical Marketing v2 read model.

The projection carries only domain facts, technical references, enums, counts,
timestamps and freshness.  It deliberately excludes rendered UI copy, actors,
audience membership, provider errors and mutable artifact payloads.  Presentation
and authorization Actions live in their own layers.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AudienceSnapshot,
    DeliveryTarget,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    Trigger,
)
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_aggregate import (
    DeliverySummary,
    delivery_summaries_for,
)
from shopman.shop.services.marketing_time import configured_timezone_name

CONTRACT = "marketing.v2"
RECENT_WINDOW = timedelta(hours=24)

FreshnessState = Literal["fresh", "stale", "degraded", "unavailable"]
ReadinessState = Literal["ready", "degraded", "blocked", "unknown"]
AnnouncementState = Literal[
    "draft",
    "pending_review",
    "approved",
    "publishing",
    "settled",
    "published",
    "failed",
    "rejected",
    "expired",
    "cancelled",
]
DecisionActorPolicy = Literal["operator", "automation"]
DeliveryState = Literal[
    "not_started",
    "fanout_pending",
    "delivering",
    "succeeded",
    "completed_with_failures",
    "unknown",
    "cancelled",
    "expired",
    "legacy_untracked",
]
TriggerCode = Literal[
    "",
    "production_finished",
    "low_stock",
    "stock_back",
    "product_created",
    "manual",
    "schedule",
]
ReasonCode = Literal["", "review_required", "review_window_expired"]
ActionKind = Literal[
    "acknowledge_alert",
    "acknowledge_notification",
    "cancel_announcement",
    "configure_platform",
    "edit_announcement",
    "edit_campaign",
    "fire_campaign",
    "mark_notification_seen",
    "open_announcement",
    "open_platform",
    "publish_announcement_now",
    "reconcile_unknown_delivery",
    "reject_announcement",
    "reschedule_announcement",
    "retry_failed_delivery",
    "schedule_announcement",
    "send_platform_test",
]
ActionPriority = Literal["primary", "secondary", "danger", "quiet"]
ActionMethod = Literal["GET", "POST", "PATCH", "DELETE"]
ActionIdempotency = Literal["none", "supported", "required"]
ConfirmationMode = Literal["none", "simple", "summary", "typed"]
StepUpLevel = Literal["none", "password", "totp"]

_SAFE_CODE = re.compile(r"^[a-zA-Z0-9_.:/-]{1,160}$")
_DOMAIN_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_HEX_HASH = re.compile(r"^[a-f0-9]{64}$")
_AUDIENCE_EXCLUSION_REASONS = frozenset({
    "consent_unavailable",
    "customer_inactive",
    "global_optout",
    "invalid_contact",
    "late_duplicate",
    "missing_consent",
    "rule_mismatch",
    "subscription_inactive",
})
_AUDIENCE_COUNT_FIELDS = (
    "eligible_count",
    "deduplicated_count",
    "vip_count",
    "general_count",
    "wave_count",
)
_TARGET_STATES = tuple(value for value, _label in DeliveryTarget.State.choices)
_SAFE_RECEIPT_OUTCOME_FIELDS = frozenset({
    "audience_count",
    "cancelled_count",
    "effective_at",
    "eligible_count",
    "lookup_count",
    "minimum_count",
    "next_allowed_at",
    "outbox_cancelled",
    "outbox_count",
    "platforms",
    "publish_at",
    "publish_mode",
    "publish_timezone",
    "queued_count",
    "retryable",
    "status",
})


@dataclass(frozen=True, slots=True)
class FreshnessProjectionV2:
    state: FreshnessState
    as_of: datetime | None
    degraded_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionConfirmationProjectionV2:
    mode: ConfirmationMode
    token_required: bool
    consequence_code: str
    step_up: StepUpLevel
    dual_control: bool


@dataclass(frozen=True, slots=True)
class MarketingActionProjectionV2:
    ref: str
    resource_ref: str
    kind: ActionKind
    label: str
    priority: ActionPriority
    enabled: bool
    reason: str
    href: str
    method: ActionMethod
    payload_schema: str
    idempotency: ActionIdempotency
    confirmation: ActionConfirmationProjectionV2
    eligible_count: int
    required_capabilities: tuple[str, ...]
    creates_external_effect: bool


@dataclass(frozen=True, slots=True)
class AudienceSummaryProjectionV2:
    source_ref: str
    version: int
    eligible_count: int
    excluded_by_reason: dict[str, int]
    deduplicated_count: int
    vip_count: int
    general_count: int
    wave_count: int
    policy_version: str
    cohort_hash: str
    calculated_at: datetime | None
    expires_at: datetime | None
    freshness: FreshnessProjectionV2


@dataclass(frozen=True, slots=True)
class ArtifactSummaryProjectionV2:
    ref: str
    version: int
    schema_version: int
    artifact_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryCountsProjectionV2:
    planned: int
    suppressed: int
    queued: int
    sending: int
    accepted: int
    confirmed: int
    failed_retryable: int
    failed_final: int
    unknown: int
    cancelled: int
    expired: int


@dataclass(frozen=True, slots=True)
class PlatformDeliveryProjectionV2:
    platform_ref: str
    state: DeliveryState
    counts: DeliveryCountsProjectionV2
    target_count: int
    fanout_expected: int
    fanout_materialized: int
    lane_count: int
    complete_lane_count: int


@dataclass(frozen=True, slots=True)
class DeliveryAggregateProjectionV2:
    state: DeliveryState
    counts: DeliveryCountsProjectionV2
    target_count: int
    fanout_expected: int
    fanout_materialized: int
    platforms: tuple[PlatformDeliveryProjectionV2, ...]
    freshness: FreshnessProjectionV2


@dataclass(frozen=True, slots=True)
class PlatformReadinessProjectionV2:
    platform_ref: str
    state: ReadinessState
    reason_code: str
    version: int
    checked_at: datetime
    facts_as_of: datetime | None
    fresh_until: datetime | None
    source_status: str


@dataclass(frozen=True, slots=True)
class ReadinessProjectionV2:
    state: ReadinessState
    platforms: tuple[PlatformReadinessProjectionV2, ...]


@dataclass(frozen=True, slots=True)
class AnnouncementFactsProjectionV2:
    trigger: TriggerCode
    campaign_ref: str
    template_ref: str
    product_ref: str
    promotion_ref: str
    link_ref: str
    content_as_of: datetime | None
    content_fresh_until: datetime | None
    content_facts_hash: str
    fact_variable_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnnouncementProjectionV2:
    ref: str
    version: int
    state: AnnouncementState
    reason_code: ReasonCode
    decision_actor_policy: DecisionActorPolicy
    facts: AnnouncementFactsProjectionV2
    platform_refs: tuple[str, ...]
    created_at: datetime
    age_seconds: int
    expires_at: datetime | None
    expires_in_seconds: int | None
    scheduled_for: datetime | None
    approved_at: datetime | None
    rejected_at: datetime | None
    published_at: datetime | None
    settled_at: datetime | None
    audience: AudienceSummaryProjectionV2
    artifact: ArtifactSummaryProjectionV2 | None
    readiness: ReadinessProjectionV2
    delivery: DeliveryAggregateProjectionV2


@dataclass(frozen=True, slots=True)
class OperationalCountersProjectionV2:
    pending_decision_count: int
    accepted_unconfirmed_targets_today: int
    confirmed_targets_today: int
    failed_final_targets_today: int
    unknown_targets_open: int


@dataclass(frozen=True, slots=True)
class MarketingBoardDataV2:
    kind: Literal["board"]
    pending: tuple[AnnouncementProjectionV2, ...]
    recent: tuple[AnnouncementProjectionV2, ...]
    counters: OperationalCountersProjectionV2


@dataclass(frozen=True, slots=True)
class CommandReceiptProjectionV2:
    ref: str
    kind: str
    state: str
    base_version: int
    resulting_version: int | None
    resource_ref: str
    outcome: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class MarketingAnnouncementDataV2:
    kind: Literal["announcement_detail"]
    announcement: AnnouncementProjectionV2
    latest_receipt: CommandReceiptProjectionV2 | None


@dataclass(frozen=True, slots=True)
class CursorPageProjectionV2:
    as_of: datetime
    limit: int
    has_more: bool
    next_cursor: str


@dataclass(frozen=True, slots=True)
class MarketingHistoryDataV2:
    kind: Literal["history"]
    items: tuple[AnnouncementProjectionV2, ...]
    page: CursorPageProjectionV2


@dataclass(frozen=True, slots=True)
class MarketingEnvelopeV2:
    contract: Literal["marketing.v2"]
    generated_at: datetime
    shop_timezone: str
    resource_version: int
    freshness: FreshnessProjectionV2
    data: MarketingBoardDataV2 | MarketingAnnouncementDataV2 | MarketingHistoryDataV2
    actions: tuple[MarketingActionProjectionV2, ...]


@dataclass(frozen=True, slots=True)
class MarketingErrorV2:
    code: str
    detail: str
    retryable: bool
    field_errors: dict[str, tuple[str, ...]]
    request_id: str
    current_version: int | None
    actions: tuple[MarketingActionProjectionV2, ...]


@dataclass(frozen=True, slots=True)
class MarketingErrorEnvelopeV2:
    error: MarketingErrorV2


def build_board(*, now: datetime | None = None) -> MarketingEnvelopeV2:
    """Build the complete board without presentation strings or silent row caps."""

    clock = _aware_clock(now)
    recent_since = clock - RECENT_WINDOW
    candidates = list(
        Announcement.objects.filter(
            Q(status=AnnouncementStatus.PENDING_REVIEW)
            | (Q(created_at__gte=recent_since) & ~Q(status=AnnouncementStatus.DRAFT))
        ).select_related("rule", "template")
    )
    evidence = _evidence_for(candidates)
    summaries = delivery_summaries_for(candidates)
    readiness_states = _readiness_states_for(candidates, now=clock)

    pending: list[AnnouncementProjectionV2] = []
    recent: list[AnnouncementProjectionV2] = []
    for announcement in candidates:
        projected = _project_announcement(
            announcement,
            snapshot=evidence.snapshots.get(announcement.pk),
            artifact=evidence.artifacts.get(announcement.pk),
            delivery=summaries[announcement.pk],
            readiness_states=readiness_states,
            now=clock,
        )
        if (
            announcement.status == AnnouncementStatus.PENDING_REVIEW
            and not announcement.is_expired(now=clock)
        ):
            pending.append(projected)
        elif announcement.created_at >= recent_since:
            recent.append(projected)

    data = MarketingBoardDataV2(
        kind="board",
        pending=tuple(pending),
        recent=tuple(recent),
        counters=_operational_counters(pending_count=len(pending), now=clock),
    )
    freshness = _combined_freshness((*pending, *recent), now=clock)
    return MarketingEnvelopeV2(
        contract=CONTRACT,
        generated_at=_local(clock),
        shop_timezone=configured_timezone_name(),
        resource_version=_data_version(data),
        freshness=freshness,
        data=data,
        actions=(),
    )


def build_announcement(
    announcement: Announcement,
    *,
    now: datetime | None = None,
) -> MarketingEnvelopeV2:
    """Build one detail envelope using the same facts as the board card."""

    clock = _aware_clock(now)
    evidence = _evidence_for((announcement,))
    readiness_states = _readiness_states_for((announcement,), now=clock)
    projected = _project_announcement(
        announcement,
        snapshot=evidence.snapshots.get(announcement.pk),
        artifact=evidence.artifacts.get(announcement.pk),
        delivery=delivery_summaries_for((announcement,))[announcement.pk],
        readiness_states=readiness_states,
        now=clock,
    )
    return MarketingEnvelopeV2(
        contract=CONTRACT,
        generated_at=_local(clock),
        shop_timezone=configured_timezone_name(),
        resource_version=announcement.version,
        freshness=_combined_freshness((projected,), now=clock),
        data=MarketingAnnouncementDataV2(
            kind="announcement_detail",
            announcement=projected,
            latest_receipt=_latest_receipt(announcement),
        ),
        actions=(),
    )


def build_history_page(
    announcements: list[Announcement] | tuple[Announcement, ...],
    *,
    as_of: datetime,
    limit: int,
    has_more: bool,
    next_cursor: str,
) -> MarketingEnvelopeV2:
    """Project one stable history page without per-row evidence queries."""

    clock = _aware_clock(as_of)
    rows = tuple(announcements)
    evidence = _evidence_for(rows)
    summaries = delivery_summaries_for(rows)
    readiness_states = _readiness_states_for(rows, now=clock)
    items = tuple(
        _project_announcement(
            announcement,
            snapshot=evidence.snapshots.get(announcement.pk),
            artifact=evidence.artifacts.get(announcement.pk),
            delivery=summaries[announcement.pk],
            readiness_states=readiness_states,
            now=clock,
        )
        for announcement in rows
    )
    data = MarketingHistoryDataV2(
        kind="history",
        items=items,
        page=CursorPageProjectionV2(
            as_of=_local(clock),
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
        ),
    )
    return MarketingEnvelopeV2(
        contract=CONTRACT,
        generated_at=_local(clock),
        shop_timezone=configured_timezone_name(),
        resource_version=_data_version(data),
        freshness=_combined_freshness(items, now=clock),
        data=data,
        actions=(),
    )


def schema() -> dict[str, Any]:
    """Return the executable JSON Schema that later generates the TS client."""

    from pydantic import TypeAdapter

    generated = TypeAdapter(MarketingEnvelopeV2).json_schema()
    generated["additionalProperties"] = False
    for definition in generated.get("$defs", {}).values():
        if definition.get("type") == "object":
            definition["additionalProperties"] = False
    return generated


def error_schema() -> dict[str, Any]:
    """Return the strict error contract used by every Marketing v2 endpoint."""

    from pydantic import TypeAdapter

    generated = TypeAdapter(MarketingErrorEnvelopeV2).json_schema()
    generated["additionalProperties"] = False
    for definition in generated.get("$defs", {}).values():
        if definition.get("type") == "object":
            definition["additionalProperties"] = False
    return generated


def _latest_receipt(
    announcement: Announcement,
) -> CommandReceiptProjectionV2 | None:
    receipt = (
        MarketingCommandReceipt.objects.filter(announcement=announcement)
        .order_by("-created_at")
        .first()
    )
    if receipt is None:
        return None
    return CommandReceiptProjectionV2(
        ref=str(receipt.ref),
        kind=_domain_code(receipt.kind),
        state=_domain_code(receipt.state),
        base_version=receipt.base_version,
        resulting_version=receipt.resulting_version,
        resource_ref=(
            receipt.resource_ref
            if _SAFE_CODE.fullmatch(receipt.resource_ref or "")
            else f"announcement:{announcement.pk}"
        ),
        outcome=_safe_receipt_outcome(receipt.outcome),
        created_at=_local(receipt.created_at),
        completed_at=_optional_local(receipt.completed_at),
    )


def _safe_receipt_outcome(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    count_fields = {
        "audience_count",
        "cancelled_count",
        "eligible_count",
        "lookup_count",
        "minimum_count",
        "outbox_cancelled",
        "outbox_count",
        "queued_count",
    }
    timestamp_fields = {"effective_at", "next_allowed_at", "publish_at"}
    for key in _SAFE_RECEIPT_OUTCOME_FIELDS:
        item = value.get(key)
        if key in count_fields:
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                safe[key] = item
        elif key == "retryable":
            if isinstance(item, bool):
                safe[key] = item
        elif key == "platforms":
            if isinstance(item, list | tuple):
                platforms = [
                    code for entry in item if (code := _domain_code(entry))
                ]
                safe[key] = platforms
        elif key in timestamp_fields:
            if item == "" or _is_offset_timestamp(item):
                safe[key] = item
        elif key == "publish_mode":
            if item in {"now", "scheduled"}:
                safe[key] = item
        elif key == "publish_timezone":
            if isinstance(item, str) and _SAFE_CODE.fullmatch(item):
                safe[key] = item
        elif key == "status":
            if code := _domain_code(item):
                safe[key] = code
    return safe


def _is_offset_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timezone.is_aware(parsed)


@dataclass(frozen=True, slots=True)
class _Evidence:
    snapshots: dict[int, AudienceSnapshot]
    artifacts: dict[int, MarketingContentArtifact]


def _evidence_for(announcements: tuple[Announcement, ...] | list[Announcement]) -> _Evidence:
    announcement_ids = tuple(item.pk for item in announcements)
    if not announcement_ids:
        return _Evidence(snapshots={}, artifacts={})

    snapshots: dict[int, AudienceSnapshot] = {}
    for snapshot in AudienceSnapshot.objects.filter(
        announcement_id__in=announcement_ids
    ).order_by("announcement_id", "-version", "-sealed_at"):
        snapshots.setdefault(snapshot.announcement_id, snapshot)

    artifacts: dict[int, MarketingContentArtifact] = {}
    for artifact in MarketingContentArtifact.objects.filter(
        announcement_id__in=announcement_ids
    ).order_by("announcement_id", "-version", "-created_at"):
        artifacts.setdefault(artifact.announcement_id, artifact)
    return _Evidence(snapshots=snapshots, artifacts=artifacts)


def _project_announcement(
    announcement: Announcement,
    *,
    snapshot: AudienceSnapshot | None,
    artifact: MarketingContentArtifact | None,
    delivery: DeliverySummary,
    readiness_states: dict[str, PlatformReadinessProjectionV2],
    now: datetime,
) -> AnnouncementProjectionV2:
    expired = announcement.is_expired(now=now)
    effective_state = AnnouncementStatus.EXPIRED if expired else announcement.status
    expires_in_seconds = (
        max(0, int((announcement.expires_at - now).total_seconds()))
        if announcement.expires_at
        else None
    )
    trigger = (
        announcement.rule.trigger
        if announcement.rule_id and announcement.rule.trigger in Trigger.values
        else ""
    )
    context = announcement.trigger_context if isinstance(announcement.trigger_context, dict) else {}
    product_ref = _prefixed_ref("product", context.get("sku"))
    content_facts = _content_facts(announcement, artifact=artifact)
    platform_refs = tuple(
        value
        for value in (_domain_code(item) for item in (announcement.platforms or ()))
        if value
    )
    return AnnouncementProjectionV2(
        ref=f"announcement:{announcement.pk}",
        version=announcement.version,
        state=effective_state,
        reason_code=_reason_code(effective_state),
        decision_actor_policy=(
            "operator"
            if announcement.approved_by_id or announcement.rejected_by_id
            else "automation"
        ),
        facts=AnnouncementFactsProjectionV2(
            trigger=trigger,
            campaign_ref=(f"campaign:{announcement.rule_id}" if announcement.rule_id else ""),
            template_ref=(
                f"announcement_template:{announcement.template_id}"
                if announcement.template_id
                else ""
            ),
            product_ref=product_ref,
            promotion_ref=content_facts["promotion_ref"],
            link_ref=content_facts["link_ref"],
            content_as_of=content_facts["as_of"],
            content_fresh_until=content_facts["fresh_until"],
            content_facts_hash=content_facts["source_hash"],
            fact_variable_refs=content_facts["variable_refs"],
        ),
        platform_refs=platform_refs,
        created_at=_local(announcement.created_at),
        age_seconds=max(0, int((now - announcement.created_at).total_seconds())),
        expires_at=_optional_local(announcement.expires_at),
        expires_in_seconds=expires_in_seconds,
        scheduled_for=_optional_local(announcement.publish_at),
        approved_at=_optional_local(announcement.approved_at),
        rejected_at=_optional_local(announcement.rejected_at),
        published_at=_optional_local(announcement.published_at),
        settled_at=_optional_local(announcement.delivery_settled_at),
        audience=_audience_summary(announcement, snapshot=snapshot, now=now),
        artifact=_artifact_summary(artifact),
        readiness=_readiness(platform_refs, states=readiness_states),
        delivery=_delivery_aggregate(delivery=delivery, now=now),
    )


def _audience_summary(
    announcement: Announcement,
    *,
    snapshot: AudienceSnapshot | None,
    now: datetime,
) -> AudienceSummaryProjectionV2:
    raw = snapshot.summary if snapshot is not None else announcement.audience
    values = raw if isinstance(raw, dict) else {}
    calculated_at = snapshot.calculated_at if snapshot is not None else _parsed_datetime(values.get("calculated_at"))
    expires_at = snapshot.expires_at if snapshot is not None else _parsed_datetime(values.get("expires_at"))
    raw_degraded = values.get("degraded_sources")
    has_degraded_source = bool(raw_degraded) if isinstance(raw_degraded, list | tuple) else False

    if has_degraded_source:
        freshness_state: FreshnessState = "degraded"
    elif snapshot is not None:
        freshness_state = "fresh"
    elif calculated_at is None:
        freshness_state = "unavailable"
    elif expires_at is not None and expires_at <= now:
        freshness_state = "stale"
    else:
        freshness_state = "fresh"

    counts = {
        key: _safe_count(values.get(key, values.get("total", 0) if key == "eligible_count" else 0))
        for key in _AUDIENCE_COUNT_FIELDS
    }
    excluded = values.get("excluded_by_reason")
    excluded_by_reason: dict[str, int] = {}
    unclassified_count = 0
    for key, value in (excluded.items() if isinstance(excluded, dict) else ()):
        count = _safe_count(value)
        if key in _AUDIENCE_EXCLUSION_REASONS:
            excluded_by_reason[key] = count
        else:
            unclassified_count += count
    if unclassified_count:
        excluded_by_reason["unclassified"] = unclassified_count
    policy_version = _domain_code(
        snapshot.policy_version if snapshot is not None else values.get("policy_version")
    )
    cohort_hash = str(snapshot.cohort_hash if snapshot is not None else values.get("cohort_hash") or "").lower()
    if not _HEX_HASH.fullmatch(cohort_hash):
        cohort_hash = ""
    return AudienceSummaryProjectionV2(
        source_ref=(f"audience_snapshot:{snapshot.ref}" if snapshot is not None else ""),
        version=snapshot.version if snapshot is not None else announcement.version,
        eligible_count=counts["eligible_count"],
        excluded_by_reason=excluded_by_reason,
        deduplicated_count=counts["deduplicated_count"],
        vip_count=counts["vip_count"],
        general_count=counts["general_count"],
        wave_count=counts["wave_count"],
        policy_version=policy_version,
        cohort_hash=cohort_hash,
        calculated_at=_optional_local(calculated_at),
        expires_at=_optional_local(expires_at),
        freshness=FreshnessProjectionV2(
            state=freshness_state,
            as_of=_optional_local(calculated_at),
            degraded_sources=("audience",) if freshness_state != "fresh" else (),
        ),
    )


def _artifact_summary(
    artifact: MarketingContentArtifact | None,
) -> ArtifactSummaryProjectionV2 | None:
    if artifact is None:
        return None
    artifact_hash = str(artifact.artifact_hash).lower()
    return ArtifactSummaryProjectionV2(
        ref=f"content_artifact:{artifact.ref}",
        version=artifact.version,
        schema_version=artifact.schema_version,
        artifact_hash=artifact_hash if _HEX_HASH.fullmatch(artifact_hash) else "",
        created_at=_local(artifact.created_at),
    )


def _content_facts(
    announcement: Announcement,
    *,
    artifact: MarketingContentArtifact | None,
) -> dict[str, Any]:
    """Project only allowlisted refs/timestamps/hash from the sealed fact payload."""

    raw = None
    if artifact is not None and isinstance(artifact.payload, dict):
        raw = artifact.payload.get("facts")
    if raw is None and isinstance(announcement.content, dict):
        raw = announcement.content.get("facts")
    if raw is None:
        return {
            "as_of": None,
            "fresh_until": None,
            "link_ref": "",
            "promotion_ref": "",
            "source_hash": "",
            "variable_refs": (),
        }
    try:
        from shopman.shop.services.marketing_facts import from_payload

        facts = from_payload(raw)
    except MarketingContractError:
        return {
            "as_of": None,
            "fresh_until": None,
            "link_ref": "",
            "promotion_ref": "",
            "source_hash": "",
            "variable_refs": (),
        }
    link = dict(facts.link)
    link_kind = _domain_code(link.get("kind"))
    link_ref = _prefixed_ref(link_kind, link.get("ref")) if link_kind else ""
    return {
        "as_of": _local(facts.as_of),
        "fresh_until": _local(facts.fresh_until),
        "link_ref": link_ref,
        "promotion_ref": _prefixed_ref("promotion", facts.promotion_ref),
        "source_hash": facts.source_hash if _HEX_HASH.fullmatch(facts.source_hash) else "",
        "variable_refs": tuple(
            value
            for value in (_domain_code(item) for item in facts.referenced_variables)
            if value
        ),
    }


def _delivery_aggregate(
    *,
    delivery: DeliverySummary,
    now: datetime,
) -> DeliveryAggregateProjectionV2:
    legacy = delivery.state == "legacy_untracked"
    freshness = FreshnessProjectionV2(
        state="unavailable" if legacy else "fresh",
        as_of=_local(now),
        degraded_sources=("delivery_ledger",) if legacy else (),
    )
    return DeliveryAggregateProjectionV2(
        state=delivery.state,
        counts=_delivery_counts(delivery.counts),
        target_count=delivery.targets_total,
        fanout_expected=delivery.fanout_expected,
        fanout_materialized=delivery.fanout_materialized,
        platforms=tuple(
            PlatformDeliveryProjectionV2(
                platform_ref=_domain_code(platform.platform) or "unknown",
                state=platform.state,
                counts=_delivery_counts(platform.counts),
                target_count=platform.targets_total,
                fanout_expected=platform.fanout_expected,
                fanout_materialized=platform.fanout_materialized,
                lane_count=platform.lanes_total,
                complete_lane_count=platform.lanes_complete,
            )
            for platform in delivery.platforms
        ),
        freshness=freshness,
    )


def _delivery_counts(counts: dict[str, int]) -> DeliveryCountsProjectionV2:
    normalized = {state: _safe_count(counts.get(state, 0)) for state in _TARGET_STATES}
    return DeliveryCountsProjectionV2(**normalized)


def _readiness(
    platform_refs: tuple[str, ...],
    *,
    states: dict[str, PlatformReadinessProjectionV2],
) -> ReadinessProjectionV2:
    platforms = tuple(
        states[platform_ref]
        for platform_ref in platform_refs
        if platform_ref in states
    )
    values = {item.state for item in platforms}
    if not values:
        overall: ReadinessState = "unknown"
    elif "blocked" in values:
        overall = "blocked"
    elif "unknown" in values:
        overall = "unknown"
    elif "degraded" in values:
        overall = "degraded"
    else:
        overall = "ready"
    return ReadinessProjectionV2(state=overall, platforms=platforms)


def _readiness_states_for(
    announcements,
    *,
    now: datetime,
) -> dict[str, PlatformReadinessProjectionV2]:
    from shopman.shop.services import delivery_readiness

    refs = tuple(dict.fromkeys(
        ref
        for announcement in announcements
        for ref in (
            _domain_code(value) for value in (announcement.platforms or ())
        )
        if ref
    ))
    return {
        state.platform: PlatformReadinessProjectionV2(
            platform_ref=state.platform,
            state=state.state,
            reason_code=_domain_code(state.reason_code),
            version=state.version,
            checked_at=_local(state.checked_at),
            facts_as_of=_optional_local(state.facts_as_of),
            fresh_until=_optional_local(state.fresh_until),
            source_status=_domain_code(state.source_status),
        )
        for state in delivery_readiness.readiness_for(refs, now=now)
    }


def _operational_counters(
    *,
    pending_count: int,
    now: datetime,
) -> OperationalCountersProjectionV2:
    shop_zone = ZoneInfo(configured_timezone_name())
    local_now = timezone.localtime(now, shop_zone)
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=shop_zone)
    next_day = datetime.combine(
        local_now.date() + timedelta(days=1),
        time.min,
        tzinfo=shop_zone,
    )
    values = DeliveryTarget.objects.aggregate(
        accepted_today=Count(
            "pk",
            filter=Q(
                state=DeliveryTarget.State.ACCEPTED,
                settled_at__gte=day_start,
                settled_at__lt=next_day,
            ),
        ),
        confirmed_today=Count(
            "pk",
            filter=Q(
                state=DeliveryTarget.State.CONFIRMED,
                settled_at__gte=day_start,
                settled_at__lt=next_day,
            ),
        ),
        failed_final_today=Count(
            "pk",
            filter=Q(
                state=DeliveryTarget.State.FAILED_FINAL,
                settled_at__gte=day_start,
                settled_at__lt=next_day,
            ),
        ),
        unknown_open=Count("pk", filter=Q(state=DeliveryTarget.State.UNKNOWN)),
    )
    return OperationalCountersProjectionV2(
        pending_decision_count=pending_count,
        accepted_unconfirmed_targets_today=values["accepted_today"],
        confirmed_targets_today=values["confirmed_today"],
        failed_final_targets_today=values["failed_final_today"],
        unknown_targets_open=values["unknown_open"],
    )


def _combined_freshness(
    announcements: tuple[AnnouncementProjectionV2, ...],
    *,
    now: datetime,
) -> FreshnessProjectionV2:
    states: list[FreshnessState] = []
    degraded_sources: set[str] = set()
    for announcement in announcements:
        for item in (announcement.audience.freshness, announcement.delivery.freshness):
            states.append(item.state)
            degraded_sources.update(item.degraded_sources)
    priority: tuple[FreshnessState, ...] = (
        "unavailable",
        "degraded",
        "stale",
        "fresh",
    )
    state = next((candidate for candidate in priority if candidate in states), "fresh")
    return FreshnessProjectionV2(
        state=state,
        as_of=_local(now),
        degraded_sources=tuple(sorted(degraded_sources)),
    )


def _data_version(
    data: MarketingBoardDataV2 | MarketingAnnouncementDataV2 | MarketingHistoryDataV2,
) -> int:
    canonical = json.dumps(
        _without_volatile_clock_fields(asdict(data)),
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
    )
    return int(hashlib.sha256(canonical.encode()).hexdigest()[:15], 16) or 1


def _without_volatile_clock_fields(value: object) -> object:
    """Keep resource versions stable while wall-clock counters tick."""

    if isinstance(value, dict):
        return {
            key: _without_volatile_clock_fields(item)
            for key, item in value.items()
            if key not in {"age_seconds", "expires_in_seconds", "as_of"}
        }
    if isinstance(value, list | tuple):
        return [_without_volatile_clock_fields(item) for item in value]
    return value


def _reason_code(state: str) -> ReasonCode:
    if state == AnnouncementStatus.PENDING_REVIEW:
        return "review_required"
    if state == AnnouncementStatus.EXPIRED:
        return "review_window_expired"
    return ""


def _safe_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _technical_code(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if _SAFE_CODE.fullmatch(candidate) else ""


def _domain_code(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if _DOMAIN_CODE.fullmatch(candidate) else ""


def _prefixed_ref(prefix: str, value: object) -> str:
    code = _technical_code(value)
    return f"{prefix}:{code}" if code else ""


def _parsed_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return None
    return parsed


def _aware_clock(value: datetime | None) -> datetime:
    clock = value or timezone.now()
    if timezone.is_naive(clock):
        raise ValueError("Marketing projection requires an aware clock.")
    return clock


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported projection value: {type(value).__name__}")


def _optional_local(value: datetime | None) -> datetime | None:
    return _local(value) if value is not None else None


def _local(value: datetime) -> datetime:
    return timezone.localtime(value)
