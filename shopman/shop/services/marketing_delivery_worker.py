"""Bounded fan-out and pre-send target claims for the Marketing ledger."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from shopman.shop.models import (
    AnnouncementStatus,
    AudienceSnapshotMember,
    DeliveryTarget,
    MarketingOutbox,
)
from shopman.shop.services.marketing_contracts import (
    DeliveryState,
    MarketingContractError,
    ensure_delivery_transition,
)
from shopman.shop.services.marketing_delivery_ledger import (
    MAX_TARGETS_PER_COMMAND,
    ensure_targets,
)

DEFAULT_FANOUT_CHUNK_SIZE = 100
DEFAULT_MAX_CHUNKS = 10
DEFAULT_CLAIM_LIMIT = 100
DEFAULT_TARGET_LEASE_SECONDS = 60
CONSENT_RETRY_SECONDS = 30
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


@dataclass(frozen=True, slots=True)
class FanoutReport:
    requested: int
    existing: int
    created: int
    remaining: int
    chunks_committed: int
    complete: bool


@dataclass(frozen=True, slots=True)
class TargetClaimReport:
    targets: tuple[DeliveryTarget, ...]
    examined: int
    suppressed: int
    expired: int
    cancelled: int
    deferred: int
    stale_reclaimed: int


def fanout_in_chunks(
    outbox_ref,
    *,
    member_ids: Iterable[int] | None = None,
    now: datetime | None = None,
    chunk_size: int = DEFAULT_FANOUT_CHUNK_SIZE,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> FanoutReport:
    """Commit bounded target chunks; replay discovers progress from the ledger."""

    clock = _aware_now(now)
    safe_chunk_size = max(1, min(int(chunk_size), 500))
    safe_max_chunks = max(1, min(int(max_chunks), 100))
    outbox = MarketingOutbox.objects.select_related("snapshot").get(ref=outbox_ref)
    if outbox.state != MarketingOutbox.State.DISPATCHED:
        raise MarketingContractError(
            code="outbox_not_dispatched",
            detail="A intent ainda não foi entregue à fila durável.",
        )

    if outbox.platform != "whatsapp":
        selection_hash = _selection_hash(outbox, (f"public:{outbox.platform}",))
        outbox = _initialize_fanout(
            outbox.ref,
            selection_hash=selection_hash,
            expected=1,
        )
        before = DeliveryTarget.objects.filter(outbox=outbox).count()
        ensure_targets(outbox.ref, now=clock)
        after = _checkpoint_fanout(
            outbox.ref,
            selection_hash=selection_hash,
            expected=1,
            now=clock,
        )
        return FanoutReport(
            requested=1,
            existing=before,
            created=after - before,
            remaining=0,
            chunks_committed=1 if after > before else 0,
            complete=True,
        )

    selected = _member_ids(member_ids)
    if len(selected) > MAX_TARGETS_PER_COMMAND:
        raise MarketingContractError(
            code="delivery_target_cap_exceeded",
            detail=f"O comando excede o limite de {MAX_TARGETS_PER_COMMAND} targets.",
        )
    if not selected:
        selection_hash = _selection_hash(outbox, ())
        _initialize_fanout(
            outbox.ref,
            selection_hash=selection_hash,
            expected=0,
        )
        _checkpoint_fanout(
            outbox.ref,
            selection_hash=selection_hash,
            expected=0,
            now=clock,
        )
        return FanoutReport(0, 0, 0, 0, 0, True)

    valid_members = dict(
        AudienceSnapshotMember.objects.filter(
            snapshot=outbox.snapshot,
            pk__in=selected,
        ).values_list("pk", "target_key")
    )
    if len(valid_members) != len(selected):
        raise MarketingContractError(
            code="delivery_member_outside_snapshot",
            detail="A seleção contém identidade fora do snapshot aprovado.",
        )
    selection_hash = _selection_hash(
        outbox,
        tuple(valid_members[member_id] for member_id in selected),
    )
    outbox = _initialize_fanout(
        outbox.ref,
        selection_hash=selection_hash,
        expected=len(selected),
    )
    if DeliveryTarget.objects.filter(
        snapshot=outbox.snapshot,
        platform=outbox.platform,
        member_id__in=selected,
    ).exclude(outbox=outbox).exists():
        raise MarketingContractError(
            code="delivery_wave_collision",
            detail="Um target aprovado já pertence a outra lane desta plataforma.",
        )

    existing_ids = set(
        DeliveryTarget.objects.filter(
            outbox=outbox,
            member_id__in=selected,
        ).values_list("member_id", flat=True)
    )
    missing = [member_id for member_id in selected if member_id not in existing_ids]
    budget = safe_chunk_size * safe_max_chunks
    chunks_committed = 0
    for offset in range(0, min(len(missing), budget), safe_chunk_size):
        chunk = missing[offset : offset + safe_chunk_size]
        ensure_targets(outbox.ref, member_ids=chunk, now=clock)
        chunks_committed += 1

    materialized = _checkpoint_fanout(
        outbox.ref,
        selection_hash=selection_hash,
        expected=len(selected),
        now=clock,
    )
    created = max(0, materialized - len(existing_ids))
    remaining = max(0, len(selected) - materialized)
    return FanoutReport(
        requested=len(selected),
        existing=len(existing_ids),
        created=created,
        remaining=remaining,
        chunks_committed=chunks_committed,
        complete=remaining == 0,
    )


def claim_due_targets(
    *,
    worker_id: str,
    now: datetime | None = None,
    limit: int = DEFAULT_CLAIM_LIMIT,
    lease_seconds: int = DEFAULT_TARGET_LEASE_SECONDS,
) -> TargetClaimReport:
    """Lease eligible targets after one batched consent/expiry recheck."""

    clock = _aware_now(now)
    safe_worker_id = _worker_id(worker_id)
    safe_limit = max(1, min(int(limit), 1_000))
    safe_lease = max(10, min(int(lease_seconds), 15 * 60))
    with transaction.atomic():
        query = DeliveryTarget.objects.filter(
            state=DeliveryTarget.State.QUEUED,
            next_attempt_at__lte=clock,
            outbox__fanout_completed_at__isnull=False,
        ).filter(Q(lease_owner="") | Q(lease_until__lte=clock))
        query = query.select_related(
            "announcement",
            "outbox",
            "member__customer",
        ).order_by("next_attempt_at", "pk")
        query = _select_for_update(query)
        rows = list(query[:safe_limit])
        if not rows:
            return TargetClaimReport((), 0, 0, 0, 0, 0, 0)

        statuses, consent_unavailable = _consent_statuses(rows)
        subscriptions, subscription_unavailable = _active_subscriptions(rows, now=clock)
        claimed: list[DeliveryTarget] = []
        suppressed = expired = cancelled = deferred = stale_reclaimed = 0
        lease_until = clock + timedelta(seconds=safe_lease)
        for target in rows:
            had_stale_lease = bool(target.lease_owner)
            outcome, reason = _pre_send_outcome(
                target,
                statuses=statuses,
                subscriptions=subscriptions,
                consent_unavailable=consent_unavailable,
                subscription_unavailable=subscription_unavailable,
                now=clock,
            )
            if outcome == "claim":
                target.lease_owner = safe_worker_id
                target.lease_until = lease_until
                target.last_error_code = ""
                claimed.append(target)
                stale_reclaimed += int(had_stale_lease)
            elif outcome == "defer":
                target.lease_owner = ""
                target.lease_until = None
                target.last_error_code = reason
                target.next_attempt_at = clock + timedelta(seconds=CONSENT_RETRY_SECONDS)
                deferred += 1
            else:
                terminal = DeliveryState(outcome)
                ensure_delivery_transition(DeliveryState(target.state), terminal)
                target.state = terminal.value
                target.lease_owner = ""
                target.lease_until = None
                target.last_error_code = reason
                target.settled_at = clock
                suppressed += int(terminal == DeliveryState.SUPPRESSED)
                expired += int(terminal == DeliveryState.EXPIRED)
                cancelled += int(terminal == DeliveryState.CANCELLED)
            target.version += 1
            target.updated_at = clock

        DeliveryTarget.objects.bulk_update(
            rows,
            [
                "state",
                "lease_owner",
                "lease_until",
                "next_attempt_at",
                "last_error_code",
                "settled_at",
                "version",
                "updated_at",
            ],
        )
        for announcement_id in {target.announcement_id for target in rows}:
            _schedule_aggregate(announcement_id)
        return TargetClaimReport(
            tuple(claimed),
            len(rows),
            suppressed,
            expired,
            cancelled,
            deferred,
            stale_reclaimed,
        )


def _pre_send_outcome(
    target: DeliveryTarget,
    *,
    statuses: dict[str, str],
    subscriptions: set,
    consent_unavailable: bool,
    subscription_unavailable: bool,
    now: datetime,
) -> tuple[str, str]:
    announcement = target.announcement
    if (
        announcement.status == AnnouncementStatus.EXPIRED
        or (announcement.expires_at is not None and announcement.expires_at <= now)
    ):
        return DeliveryState.EXPIRED.value, "announcement_expired_before_send"
    if announcement.status in {
        AnnouncementStatus.CANCELLED,
        AnnouncementStatus.REJECTED,
    }:
        return DeliveryState.CANCELLED.value, "announcement_cancelled_before_send"
    if announcement.status not in {
        AnnouncementStatus.APPROVED,
        AnnouncementStatus.PUBLISHING,
    }:
        return "defer", "announcement_not_dispatchable"
    if target.platform != "whatsapp":
        return "claim", ""

    member = target.member
    if member is None:
        return DeliveryState.SUPPRESSED.value, "delivery_identity_unavailable"
    customer = member.customer if member.customer_id else None
    if customer is not None and not customer.is_active:
        return DeliveryState.SUPPRESSED.value, "customer_inactive"
    if consent_unavailable:
        return "defer", "consent_unavailable"
    customer_ref = customer.ref if customer is not None else ""
    status = statuses.get(customer_ref, "")
    if status == "opted_out":
        return DeliveryState.SUPPRESSED.value, "global_optout"

    reasons = frozenset(member.reasons or [])
    if member.subscription_ref:
        if subscription_unavailable:
            return "defer", "subscription_unavailable"
        if member.subscription_ref not in subscriptions:
            return DeliveryState.SUPPRESSED.value, "subscription_inactive"
    if "alerts" in reasons and member.subscription_ref:
        return "claim", ""
    if customer_ref and status == "opted_in":
        return "claim", ""
    return DeliveryState.SUPPRESSED.value, "missing_consent"


def _consent_statuses(rows) -> tuple[dict[str, str], bool]:
    refs = {
        target.member.customer.ref
        for target in rows
        if target.platform == "whatsapp"
        and target.member_id
        and target.member.customer_id
        and target.member.customer
    }
    try:
        from shopman.guestman import ConsentService

        return ConsentService.get_customer_statuses("whatsapp", refs), False
    except Exception:
        return {}, True


def _active_subscriptions(rows, *, now: datetime) -> tuple[set, bool]:
    refs = {
        target.member.subscription_ref
        for target in rows
        if target.platform == "whatsapp"
        and target.member_id
        and target.member.subscription_ref
    }
    if not refs:
        return set(), False
    try:
        from shopman.storefront.models import StockAlertSubscription

        active = set(
            StockAlertSubscription.objects.active(now=now)
            .filter(ref__in=refs)
            .values_list("ref", flat=True)
        )
        return active, False
    except Exception:
        return set(), True


def _member_ids(values: Iterable[int] | None) -> tuple[int, ...]:
    if values is None:
        raise MarketingContractError(
            code="delivery_member_selection_required",
            detail="A lane WhatsApp exige seleção protegida explícita de membros.",
        )
    try:
        return tuple(sorted({int(value) for value in values}))
    except (TypeError, ValueError) as exc:
        raise MarketingContractError(
            code="invalid_delivery_member_selection",
            detail="A seleção protegida de membros é inválida.",
        ) from exc


def _selection_hash(outbox: MarketingOutbox, target_keys: tuple[str, ...]) -> str:
    canonical = "|".join(
        (
            "marketing-fanout-v1",
            str(outbox.ref),
            outbox.platform,
            outbox.wave_key,
            *sorted(target_keys),
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _initialize_fanout(
    outbox_ref,
    *,
    selection_hash: str,
    expected: int,
) -> MarketingOutbox:
    with transaction.atomic():
        outbox = MarketingOutbox.objects.select_for_update().get(ref=outbox_ref)
        if outbox.state != MarketingOutbox.State.DISPATCHED:
            raise MarketingContractError(
                code="outbox_not_dispatched",
                detail="A intent ainda não foi entregue à fila durável.",
            )
        if outbox.fanout_selection_hash and (
            outbox.fanout_selection_hash != selection_hash
            or outbox.fanout_expected != expected
        ):
            raise MarketingContractError(
                code="delivery_fanout_selection_conflict",
                detail="A seleção protegida desta lane mudou durante o fan-out.",
            )
        if not outbox.fanout_selection_hash:
            outbox.fanout_selection_hash = selection_hash
            outbox.fanout_expected = expected
            outbox.save(update_fields=[
                "fanout_selection_hash",
                "fanout_expected",
                "updated_at",
            ])
            _schedule_aggregate(outbox.announcement_id)
        return outbox


def _checkpoint_fanout(
    outbox_ref,
    *,
    selection_hash: str,
    expected: int,
    now: datetime,
) -> int:
    with transaction.atomic():
        outbox = MarketingOutbox.objects.select_for_update().get(ref=outbox_ref)
        if (
            outbox.fanout_selection_hash != selection_hash
            or outbox.fanout_expected != expected
        ):
            raise MarketingContractError(
                code="delivery_fanout_selection_conflict",
                detail="A seleção protegida desta lane mudou durante o fan-out.",
            )
        materialized = DeliveryTarget.objects.filter(outbox=outbox).count()
        if materialized > expected:
            raise MarketingContractError(
                code="delivery_fanout_count_mismatch",
                detail="O ledger contém mais targets que a seleção aprovada.",
            )
        outbox.fanout_materialized = materialized
        outbox.fanout_completed_at = now if materialized == expected else None
        outbox.updated_at = now
        outbox.save(update_fields=[
            "fanout_materialized",
            "fanout_completed_at",
            "updated_at",
        ])
        _schedule_aggregate(outbox.announcement_id)
        return materialized


def _worker_id(value: str) -> str:
    normalized = str(value or "")
    if not _WORKER_ID_RE.fullmatch(normalized):
        raise MarketingContractError(
            code="invalid_delivery_worker_id",
            detail="A identidade técnica do worker é inválida.",
        )
    return normalized


def _select_for_update(query):
    if connection.features.has_select_for_update_skip_locked:
        return query.select_for_update(skip_locked=True)
    return query.select_for_update()


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing delivery worker requires an aware clock.")
    return value


def _schedule_aggregate(announcement_id: int) -> None:
    from shopman.shop.services.marketing_delivery_aggregate import (
        schedule_delivery_refresh,
    )

    schedule_delivery_refresh(announcement_id)
