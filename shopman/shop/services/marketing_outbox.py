"""Recoverable hand-off from the transactional Marketing outbox to Directives.

The approval request only writes ``MarketingOutbox``.  This module runs later,
claims committed rows with a bounded lease and creates the existing durable
Directive in the *same* transaction that marks the outbox as dispatched.  The
Directive signal is itself ``on_commit`` based, so no handler can observe half
of that hand-off.

This layer does not claim provider exactly-once.  It only guarantees one
internal durable hand-off per outbox row; DeliveryTarget/Attempt owns external
effect semantics from MKT-013 onward.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from shopman.shop.directives import (
    ANNOUNCEMENT_NOTIFY,
    ANNOUNCEMENT_PUBLISH,
    create_deduped,
)
from shopman.shop.models import (
    AnnouncementStatus,
    MarketingCommandReceipt,
    MarketingOutbox,
)
from shopman.shop.services.marketing_approval import canonical_artifact_bytes
from shopman.shop.services.marketing_contracts import MarketingContractError

DEFAULT_BATCH_SIZE = 100
DEFAULT_LEASE_SECONDS = 60
MAX_ATTEMPTS = 5
_MAX_BACKOFF_SECONDS = 300
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
logger = logging.getLogger(__name__)


class OutboxClaimLost(RuntimeError):
    """The row is no longer leased by this worker; it must not be published."""


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    linked_existing: int = 0
    directive_mismatch: int = 0
    stale_requeued: int = 0
    stale_failed: int = 0
    dispatched_without_directive: int = 0
    approved_without_graph: int = 0


@dataclass(frozen=True, slots=True)
class ProcessReport:
    claimed: int = 0
    dispatched: int = 0
    requeued: int = 0
    failed: int = 0
    oldest_due_age_seconds: int = 0


def claim_due(
    *,
    worker_id: str,
    now: datetime | None = None,
    limit: int = DEFAULT_BATCH_SIZE,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> tuple[MarketingOutbox, ...]:
    """Claim committed, due rows in a short transaction.

    Stale leases are deliberately recovered by ``reconcile`` first.  Keeping
    recovery explicit makes its count observable instead of hiding it inside a
    normal claim.
    """

    safe_worker_id = _worker_id(worker_id)
    from shopman.shop.services.marketing_security import require_external_effects_enabled

    try:
        require_external_effects_enabled()
    except MarketingContractError:
        return ()
    clock = _aware_now(now)
    safe_limit = max(1, min(int(limit), 1_000))
    safe_lease = max(10, min(int(lease_seconds), 15 * 60))

    with transaction.atomic():
        query = MarketingOutbox.objects.filter(
            state=MarketingOutbox.State.PENDING,
            available_at__lte=clock,
        ).order_by("available_at", "pk")
        query = _select_for_update(query)
        rows = list(query[:safe_limit])
        if not rows:
            return ()
        lease_until = clock + timedelta(seconds=safe_lease)
        for row in rows:
            row.state = MarketingOutbox.State.CLAIMED
            row.attempts += 1
            row.lease_owner = safe_worker_id
            row.lease_until = lease_until
            row.last_error_code = ""
            row.updated_at = clock
        MarketingOutbox.objects.bulk_update(
            rows,
            [
                "state",
                "attempts",
                "lease_owner",
                "lease_until",
                "last_error_code",
                "updated_at",
            ],
        )
        return tuple(rows)


def publish_claim(
    outbox_ref,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> MarketingOutbox:
    """Atomically create/find the durable Directive and finish one hand-off."""

    safe_worker_id = _worker_id(worker_id)
    from shopman.shop.services.marketing_security import require_external_effects_enabled

    require_external_effects_enabled()
    clock = _aware_now(now)
    with transaction.atomic():
        row = (
            MarketingOutbox.objects.select_for_update()
            .select_related("announcement", "artifact", "snapshot", "command")
            .get(ref=outbox_ref)
        )
        if row.state == MarketingOutbox.State.DISPATCHED:
            return row
        if (
            row.state != MarketingOutbox.State.CLAIMED
            or row.lease_owner != safe_worker_id
            or row.lease_until is None
            or row.lease_until <= clock
        ):
            raise OutboxClaimLost(f"Marketing outbox {row.ref} is not leased by this worker.")

        graph_error = _graph_error(row, now=clock)
        if graph_error:
            _finish_failed(row, code=graph_error, now=clock)
            return row

        # Registered before Directive.post_save's callback.  Tests can inject a
        # process crash here: the DB transaction is already committed, while the
        # queued Directive remains available to process_directives.
        transaction.on_commit(lambda: _after_publish_commit(str(row.ref)))

        topic = _directive_topic(row)
        dedupe_key = _dedupe_key(row)
        directive = _existing_directive(dedupe_key)
        if directive is not None and not _directive_matches(row, directive):
            _quarantine_mismatched_directive(directive, now=clock)
            _finish_failed(row, code="directive_identity_mismatch", now=clock)
            return row
        if directive is None:
            directive = create_deduped(
                topic,
                payload=_directive_payload(row),
                dedupe_key=dedupe_key,
                available_at=clock,
            )
        if directive is None:
            directive = _existing_directive(dedupe_key)
        if directive is None:
            raise RuntimeError("Durable Marketing directive could not be resolved.")
        if not _directive_matches(row, directive):
            _quarantine_mismatched_directive(directive, now=clock)
            _finish_failed(row, code="directive_identity_mismatch", now=clock)
            return row

        row.state = MarketingOutbox.State.DISPATCHED
        row.dispatch_ref = f"directive:{directive.pk}"
        row.dispatched_at = clock
        row.lease_owner = ""
        row.lease_until = None
        row.last_error_code = ""
        row.updated_at = clock
        row.save(update_fields=[
            "state",
            "dispatch_ref",
            "dispatched_at",
            "lease_owner",
            "lease_until",
            "last_error_code",
            "updated_at",
        ])
        announcement = row.announcement
        if announcement.status == AnnouncementStatus.APPROVED:
            announcement.status = AnnouncementStatus.PUBLISHING
            announcement.publish_at = None
            announcement.save(update_fields=["status", "publish_at"])
        return row


def process_due(
    *,
    worker_id: str,
    now: datetime | None = None,
    limit: int = DEFAULT_BATCH_SIZE,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> ProcessReport:
    """Claim a bounded batch and isolate every row's hand-off failure."""

    clock = _aware_now(now)
    rows = claim_due(
        worker_id=worker_id,
        now=clock,
        limit=limit,
        lease_seconds=lease_seconds,
    )
    dispatched = requeued = failed = 0
    oldest_due_age = max(
        (max(0, int((clock - row.available_at).total_seconds())) for row in rows),
        default=0,
    )
    for row in rows:
        try:
            settled = publish_claim(row.ref, worker_id=worker_id, now=clock)
        except OutboxClaimLost:
            continue
        except Exception:
            logger.warning("marketing.outbox_directive_handoff_failed")
            state = release_failed_claim(
                row.ref,
                worker_id=worker_id,
                code="directive_handoff_failed",
                now=clock,
            )
            if state == MarketingOutbox.State.DISPATCHED:
                # An injected crash after COMMIT lands here.  The durable hand-off
                # won; treating it as retryable would manufacture a duplicate.
                dispatched += 1
            elif state == MarketingOutbox.State.FAILED:
                failed += 1
            elif state == MarketingOutbox.State.PENDING:
                requeued += 1
            continue
        if settled.state == MarketingOutbox.State.DISPATCHED:
            dispatched += 1
        elif settled.state == MarketingOutbox.State.FAILED:
            failed += 1
    return ProcessReport(
        claimed=len(rows),
        dispatched=dispatched,
        requeued=requeued,
        failed=failed,
        oldest_due_age_seconds=oldest_due_age,
    )


def release_failed_claim(
    outbox_ref,
    *,
    worker_id: str,
    code: str,
    now: datetime | None = None,
) -> str:
    """Return an internal hand-off failure to pending, without raw exception text."""

    safe_worker_id = _worker_id(worker_id)
    clock = _aware_now(now)
    safe_code = _error_code(code)
    with transaction.atomic():
        row = MarketingOutbox.objects.select_for_update().get(ref=outbox_ref)
        if row.state != MarketingOutbox.State.CLAIMED or row.lease_owner != safe_worker_id:
            return row.state
        if row.attempts >= MAX_ATTEMPTS:
            _finish_failed(row, code=safe_code, now=clock)
        else:
            row.state = MarketingOutbox.State.PENDING
            row.available_at = clock + timedelta(
                seconds=min(2 ** row.attempts, _MAX_BACKOFF_SECONDS)
            )
            row.lease_owner = ""
            row.lease_until = None
            row.last_error_code = safe_code
            row.updated_at = clock
            row.save(update_fields=[
                "state",
                "available_at",
                "lease_owner",
                "lease_until",
                "last_error_code",
                "updated_at",
            ])
        return row.state


def reconcile(
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_BATCH_SIZE,
) -> ReconcileReport:
    """Repair stale pre-effect states and report unsafe drift without blind retry."""

    clock = _aware_now(now)
    safe_limit = max(1, min(int(limit), 1_000))
    linked = mismatched = requeued = failed = 0
    with transaction.atomic():
        candidates = (
            MarketingOutbox.objects.select_related(
                "announcement",
                "artifact",
                "snapshot",
                "command",
            )
            .filter(
                Q(state=MarketingOutbox.State.PENDING)
                | Q(
                    state=MarketingOutbox.State.CLAIMED,
                    lease_until__lte=clock,
                )
            )
            .order_by("available_at", "pk")
        )
        candidates = _select_for_update(candidates)
        for row in list(candidates[:safe_limit]):
            directive = _existing_directive(_dedupe_key(row))
            if directive is not None:
                if _directive_matches(row, directive):
                    _link_existing(row, directive_pk=directive.pk, now=clock)
                    linked += 1
                else:
                    _quarantine_mismatched_directive(directive, now=clock)
                    _finish_failed(
                        row,
                        code="directive_identity_mismatch",
                        now=clock,
                    )
                    mismatched += 1
                continue
            if row.state != MarketingOutbox.State.CLAIMED:
                continue
            if row.attempts >= MAX_ATTEMPTS:
                _finish_failed(row, code="stale_lease_exhausted", now=clock)
                failed += 1
            else:
                row.state = MarketingOutbox.State.PENDING
                row.lease_owner = ""
                row.lease_until = None
                row.last_error_code = "stale_lease_recovered"
                row.updated_at = clock
                row.save(update_fields=[
                    "state",
                    "lease_owner",
                    "lease_until",
                    "last_error_code",
                    "updated_at",
                ])
                requeued += 1

    from shopman.orderman.models import Directive

    missing_directive = 0
    dispatched = MarketingOutbox.objects.filter(
        state=MarketingOutbox.State.DISPATCHED,
    ).only("dispatch_ref")
    for dispatch_ref in dispatched.values_list("dispatch_ref", flat=True)[:safe_limit]:
        pk = _directive_pk(dispatch_ref)
        if pk is None or not Directive.objects.filter(pk=pk).exists():
            # An already-dispatched row is never reset automatically: the queue
            # object may have been removed after a provider effect.
            missing_directive += 1

    approved_without_graph = _approved_without_graph_count()
    return ReconcileReport(
        linked_existing=linked,
        directive_mismatch=mismatched,
        stale_requeued=requeued,
        stale_failed=failed,
        dispatched_without_directive=missing_directive,
        approved_without_graph=approved_without_graph,
    )


def _graph_error(row: MarketingOutbox, *, now: datetime) -> str:
    announcement = row.announcement
    if announcement.status not in {
        AnnouncementStatus.APPROVED,
        AnnouncementStatus.PUBLISHING,
    }:
        return "announcement_not_dispatchable"
    if announcement.expires_at is not None and announcement.expires_at <= now:
        return "announcement_expired_before_dispatch"
    command = row.command
    if (
        command.state != MarketingCommandReceipt.State.COMPLETED
        or command.resulting_version is None
        or row.artifact.version != command.resulting_version
        or row.snapshot.version != command.resulting_version
        or row.artifact.announcement_id != announcement.pk
        or row.snapshot.announcement_id != announcement.pk
    ):
        return "approval_graph_mismatch"
    platforms = row.artifact.payload.get("platforms", [])
    if row.platform not in platforms:
        return "platform_not_approved"
    digest = hashlib.sha256(canonical_artifact_bytes(row.artifact.payload)).hexdigest()
    if digest != row.artifact.artifact_hash:
        return "artifact_hash_mismatch"
    return ""


def _directive_topic(row: MarketingOutbox) -> str:
    return ANNOUNCEMENT_NOTIFY if row.platform == "whatsapp" else ANNOUNCEMENT_PUBLISH


def _directive_payload(row: MarketingOutbox) -> dict:
    payload = {
        "announcement_id": row.announcement_id,
        "artifact_hash": row.artifact.artifact_hash,
        "artifact_ref": str(row.artifact.ref),
        "content_version": row.artifact.version,
        "outbox_ref": str(row.ref),
        "platform": row.platform,
        "snapshot_ref": str(row.snapshot.ref),
    }
    if row.platform == "whatsapp":
        wave_keys = list(
            MarketingOutbox.objects.filter(
                command=row.command,
                platform="whatsapp",
            )
            .order_by("available_at", "pk")
            .values_list("wave_key", flat=True)
        )
        wave_keys = [key or "all" for key in wave_keys]
        payload["wave"] = row.wave_key or "all"
        payload["wave_keys"] = wave_keys
        payload["waves_expected"] = len(wave_keys)
    return payload


def _dedupe_key(row: MarketingOutbox) -> str:
    return f"marketing-outbox:{row.ref}"


def _existing_directive(dedupe_key: str):
    from shopman.orderman.models import Directive

    return Directive.objects.filter(dedupe_key=dedupe_key).order_by("pk").first()


def _directive_matches(row: MarketingOutbox, directive) -> bool:
    payload = directive.payload if isinstance(directive.payload, dict) else {}
    matches = (
        directive.topic == _directive_topic(row)
        and payload.get("outbox_ref") == str(row.ref)
        and payload.get("artifact_ref") == str(row.artifact.ref)
        and payload.get("snapshot_ref") == str(row.snapshot.ref)
        and payload.get("artifact_hash") == row.artifact.artifact_hash
        and payload.get("content_version") == row.artifact.version
        and payload.get("platform") == row.platform
    )
    if row.platform == "whatsapp":
        expected = _directive_payload(row)
        matches = matches and all(
            payload.get(key) == expected[key]
            for key in ("wave", "wave_keys", "waves_expected")
        )
    return matches


def _quarantine_mismatched_directive(directive, *, now: datetime) -> None:
    """Stop a not-started corrupt hand-off; never rewrite an effect that began."""

    from shopman.orderman.models import Directive

    Directive.objects.filter(
        pk=directive.pk,
        status=Directive.Status.QUEUED,
    ).update(
        status=Directive.Status.FAILED,
        error_code="payload_invalid",
        last_error="Marketing outbox identity mismatch",
        updated_at=now,
    )


def _link_existing(row: MarketingOutbox, *, directive_pk: int, now: datetime) -> None:
    row.state = MarketingOutbox.State.DISPATCHED
    row.dispatch_ref = f"directive:{directive_pk}"
    row.dispatched_at = now
    row.lease_owner = ""
    row.lease_until = None
    row.last_error_code = "reconciled_existing_directive"
    row.updated_at = now
    row.save(update_fields=[
        "state",
        "dispatch_ref",
        "dispatched_at",
        "lease_owner",
        "lease_until",
        "last_error_code",
        "updated_at",
    ])
    announcement = row.announcement
    if announcement.status == AnnouncementStatus.APPROVED:
        announcement.status = AnnouncementStatus.PUBLISHING
        announcement.publish_at = None
        announcement.save(update_fields=["status", "publish_at"])


def _finish_failed(row: MarketingOutbox, *, code: str, now: datetime) -> None:
    row.state = MarketingOutbox.State.FAILED
    row.lease_owner = ""
    row.lease_until = None
    row.last_error_code = _error_code(code)
    row.updated_at = now
    row.save(update_fields=[
        "state",
        "lease_owner",
        "lease_until",
        "last_error_code",
        "updated_at",
    ])


def _select_for_update(query):
    if connection.features.has_select_for_update_skip_locked:
        return query.select_for_update(skip_locked=True)
    return query.select_for_update()


def _approved_without_graph_count() -> int:
    return (
        MarketingCommandReceipt.objects.filter(
            kind=MarketingCommandReceipt.Kind.APPROVE,
            state=MarketingCommandReceipt.State.COMPLETED,
            announcement__status__in=(
                AnnouncementStatus.APPROVED,
                AnnouncementStatus.PUBLISHING,
            ),
        )
        .filter(
            Q(outbox_entries__isnull=True)
            | Q(announcement__content_artifacts__isnull=True)
            | Q(announcement__audience_snapshots__isnull=True)
        )
        .distinct()
        .count()
    )


def _directive_pk(dispatch_ref: str) -> int | None:
    prefix, separator, raw_pk = str(dispatch_ref or "").partition(":")
    if prefix != "directive" or not separator or not raw_pk.isdigit():
        return None
    return int(raw_pk)


def _worker_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not _WORKER_ID_RE.fullmatch(normalized):
        raise ValueError("worker_id must be 1-100 safe ASCII characters.")
    return normalized


def _error_code(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 64 or not all(
        char.islower() or char.isdigit() or char == "_" for char in normalized
    ):
        return "internal_error"
    return normalized


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing outbox requires an aware clock.")
    return value


def _after_publish_commit(_outbox_ref: str) -> None:
    """Crash-injection seam; production deliberately performs no work here."""
