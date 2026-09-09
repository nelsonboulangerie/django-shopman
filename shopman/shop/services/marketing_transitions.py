"""Transactional reject, cancel, reschedule and expiry commands for Marketing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AudienceSnapshot,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    MarketingOutbox,
)
from shopman.shop.services.marketing_approval import (
    APPROVAL_RECORD_RETENTION,
    PUBLISH_SCHEDULED,
    normalize_schedule,
)
from shopman.shop.services.marketing_commands import (
    CommandExecution,
    RejectCommand,
    command_fingerprints,
    execute_announcement_command,
)
from shopman.shop.services.marketing_contracts import MarketingContractError

SYSTEM_EXPIRY_ACTOR = "system:marketing-expiry"


@dataclass(frozen=True, slots=True)
class TransitionResult:
    announcement: Announcement
    receipt: MarketingCommandReceipt
    affected_outbox: tuple[MarketingOutbox, ...]
    replayed: bool


def reject_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    reason: str = "",
    request_id: str = "",
    now: datetime | None = None,
) -> TransitionResult:
    now = _aware_now(now)
    normalized_reason = str(reason or "").strip()
    if len(normalized_reason) > 200:
        raise MarketingContractError(
            code="rejection_reason_too_long",
            detail="O motivo da recusa deve ter no máximo 200 caracteres.",
            field_errors={"reason": ("Use no máximo 200 caracteres.",)},
        )

    def operation(announcement, receipt):
        allowed = {AnnouncementStatus.DRAFT, AnnouncementStatus.PENDING_REVIEW}
        if announcement.status == AnnouncementStatus.APPROVED and announcement.publish_at:
            allowed.add(AnnouncementStatus.APPROVED)
        if announcement.status not in allowed:
            raise RejectCommand(
                code="announcement_not_rejectable",
                detail="Este anúncio não pode mais ser recusado.",
                outcome={"status": announcement.status},
            )
        rows = _cancellable_rows(announcement, allow_empty=True)
        _cancel_rows(rows, receipt=receipt, at=now)
        artifact, snapshot = _latest_graph(announcement)

        announcement.status = AnnouncementStatus.REJECTED
        announcement.rejected_by_id = receipt.actor_id
        announcement.rejected_at = now
        announcement.rejected_reason = normalized_reason
        announcement.publish_at = None
        announcement.save(update_fields=[
            "status",
            "rejected_by",
            "rejected_at",
            "rejected_reason",
            "publish_at",
        ])
        _audit(
            event_type=MarketingAuditEvent.EventType.REJECTED,
            receipt=receipt,
            announcement=announcement,
            artifact=artifact,
            snapshot=snapshot,
            reason_code="operator_rejected",
            facts={
                "outbox_cancelled": len(rows),
                "reason_present": bool(normalized_reason),
            },
            now=now,
        )
        return {
            "outbox_cancelled": len(rows),
            "reason_present": bool(normalized_reason),
            "status": AnnouncementStatus.REJECTED,
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.REJECT,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload={"reason": normalized_reason},
        operation=operation,
        request_id=request_id,
    )
    return _result(execution)


def cancel_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    reason_code: str = "operator_cancelled",
    request_id: str = "",
    now: datetime | None = None,
) -> TransitionResult:
    now = _aware_now(now)
    safe_reason_code = _reason_code(reason_code)

    def operation(announcement, receipt):
        if announcement.status not in {
            AnnouncementStatus.APPROVED,
            AnnouncementStatus.PUBLISHING,
        }:
            raise RejectCommand(
                code="announcement_not_cancellable",
                detail="Este anúncio não está mais em uma etapa cancelável.",
                outcome={"status": announcement.status},
            )
        rows = _cancellable_rows(announcement, allow_empty=False)
        _cancel_rows(rows, receipt=receipt, at=now)
        artifact, snapshot = _latest_graph(announcement)

        announcement.status = AnnouncementStatus.CANCELLED
        announcement.publish_at = None
        announcement.save(update_fields=["status", "publish_at"])
        _audit(
            event_type=MarketingAuditEvent.EventType.CANCELLED,
            receipt=receipt,
            announcement=announcement,
            artifact=artifact,
            snapshot=snapshot,
            reason_code=safe_reason_code,
            facts={"outbox_cancelled": len(rows)},
            now=now,
        )
        return {
            "outbox_cancelled": len(rows),
            "status": AnnouncementStatus.CANCELLED,
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.CANCEL,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload={"reason_code": safe_reason_code},
        operation=operation,
        request_id=request_id,
    )
    return _result(execution)


def reschedule_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    publish_at: datetime,
    request_id: str = "",
    now: datetime | None = None,
) -> TransitionResult:
    now = _aware_now(now)
    _mode, normalized_publish_at = normalize_schedule(
        PUBLISH_SCHEDULED,
        publish_at=publish_at,
        now=now,
    )
    assert normalized_publish_at is not None

    def operation(announcement, receipt):
        if announcement.status != AnnouncementStatus.APPROVED or not announcement.publish_at:
            raise RejectCommand(
                code="announcement_not_reschedulable",
                detail="Somente um anúncio ainda agendado pode mudar de horário.",
                outcome={"status": announcement.status},
            )
        rows = _cancellable_rows(announcement, allow_empty=False)
        old_publish_at = announcement.publish_at
        delta = normalized_publish_at - old_publish_at
        for row in rows:
            row.available_at += delta
            row.updated_at = now
        MarketingOutbox.objects.bulk_update(rows, ["available_at", "updated_at"])
        artifact, snapshot = _latest_graph(announcement)

        announcement.publish_at = normalized_publish_at
        announcement.save(update_fields=["publish_at"])
        _audit(
            event_type=MarketingAuditEvent.EventType.RESCHEDULED,
            receipt=receipt,
            announcement=announcement,
            artifact=artifact,
            snapshot=snapshot,
            reason_code="operator_rescheduled",
            facts={
                "from": old_publish_at.isoformat(),
                "outbox_rescheduled": len(rows),
                "to": normalized_publish_at.isoformat(),
            },
            now=now,
        )
        return {
            "outbox_rescheduled": len(rows),
            "publish_at": normalized_publish_at.isoformat(),
            "status": AnnouncementStatus.APPROVED,
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.RESCHEDULE,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload={"publish_at": normalized_publish_at.isoformat()},
        operation=operation,
        request_id=request_id,
    )
    return _result(execution)


def expire_due(*, now: datetime | None = None) -> int:
    """Expire due review items one-by-one with a system receipt and audit event."""

    now = _aware_now(now)
    candidates = list(
        Announcement.objects.filter(
            status=AnnouncementStatus.PENDING_REVIEW,
            expires_at__isnull=False,
            expires_at__lte=now,
        ).values_list("pk", flat=True)
    )
    return sum(1 for announcement_id in candidates if _expire_one(announcement_id, now=now))


def _expire_one(announcement_id: int, *, now: datetime) -> bool:
    with transaction.atomic():
        announcement = (
            Announcement.objects.select_for_update()
            .filter(pk=announcement_id)
            .first()
        )
        if (
            announcement is None
            or announcement.status != AnnouncementStatus.PENDING_REVIEW
            or announcement.expires_at is None
            or announcement.expires_at > now
        ):
            return False
        base_version = announcement.version
        resource_ref = f"announcement:{announcement.pk}"
        raw_key = f"marketing-expire:{announcement.pk}:version:{base_version}"
        payload = {"expires_at": announcement.expires_at.isoformat()}
        key_hash, payload_hash = command_fingerprints(
            kind=MarketingCommandReceipt.Kind.EXPIRE,
            resource_ref=resource_ref,
            idempotency_key=raw_key,
            base_version=base_version,
            payload=payload,
        )
        existing = MarketingCommandReceipt.objects.filter(
            actor__isnull=True,
            actor_ref=SYSTEM_EXPIRY_ACTOR,
            idempotency_key_hash=key_hash,
        ).first()
        if existing is not None:
            return False

        receipt = MarketingCommandReceipt.objects.create(
            kind=MarketingCommandReceipt.Kind.EXPIRE,
            state=MarketingCommandReceipt.State.ACCEPTED,
            announcement=announcement,
            resource_ref=resource_ref,
            actor=None,
            actor_ref=SYSTEM_EXPIRY_ACTOR,
            idempotency_key_hash=key_hash,
            payload_hash=payload_hash,
            base_version=base_version,
            request_id="",
            retention_until=now + APPROVAL_RECORD_RETENTION,
        )
        rows = _cancellable_rows(announcement, allow_empty=True)
        _cancel_rows(rows, receipt=receipt, at=now)
        announcement.status = AnnouncementStatus.EXPIRED
        announcement.publish_at = None
        announcement.version += 1
        announcement.save(update_fields=["status", "publish_at", "version"])
        receipt.state = MarketingCommandReceipt.State.COMPLETED
        receipt.resulting_version = announcement.version
        receipt.outcome = {
            "outbox_cancelled": len(rows),
            "status": AnnouncementStatus.EXPIRED,
        }
        receipt.completed_at = now
        receipt.save(update_fields=[
            "state",
            "resulting_version",
            "outcome",
            "completed_at",
        ])
        artifact, snapshot = _latest_graph(announcement)
        _audit(
            event_type=MarketingAuditEvent.EventType.EXPIRED,
            receipt=receipt,
            announcement=announcement,
            artifact=artifact,
            snapshot=snapshot,
            reason_code="review_deadline_elapsed",
            facts={"outbox_cancelled": len(rows)},
            now=now,
            base_version=base_version,
        )
        return True


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing transitions require an aware clock.")
    return value


def _reason_code(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 64 or not all(
        char.islower() or char.isdigit() or char in {"_", "-"}
        for char in normalized
    ):
        raise MarketingContractError(
            code="invalid_reason_code",
            detail="O motivo técnico do cancelamento é inválido.",
            field_errors={"reason_code": ("Use letras minúsculas, números, _ ou -.",)},
        )
    return normalized


def _cancellable_rows(
    announcement: Announcement,
    *,
    allow_empty: bool,
) -> list[MarketingOutbox]:
    rows = list(
        MarketingOutbox.objects.select_for_update()
        .filter(announcement=announcement)
        .exclude(state=MarketingOutbox.State.CANCELLED)
        .order_by("pk")
    )
    unsafe = [row for row in rows if row.state != MarketingOutbox.State.PENDING]
    if unsafe:
        raise RejectCommand(
            code="dispatch_already_started",
            detail="A publicação já começou; não é seguro prometer cancelamento.",
            outcome={"started_lane_count": len(unsafe)},
        )
    if not rows and not allow_empty:
        raise RejectCommand(
            code="nothing_cancellable",
            detail="Não há publicação pendente que possa ser alterada.",
        )
    return rows


def _cancel_rows(
    rows: list[MarketingOutbox],
    *,
    receipt: MarketingCommandReceipt,
    at: datetime,
) -> None:
    if not rows:
        return
    MarketingOutbox.objects.filter(pk__in=[row.pk for row in rows]).update(
        state=MarketingOutbox.State.CANCELLED,
        cancelled_by_command=receipt,
        cancelled_at=at,
        lease_owner="",
        lease_until=None,
        updated_at=at,
    )


def _latest_graph(
    announcement: Announcement,
) -> tuple[MarketingContentArtifact | None, AudienceSnapshot | None]:
    artifact = (
        MarketingContentArtifact.objects.filter(announcement=announcement)
        .order_by("-version")
        .first()
    )
    snapshot = (
        AudienceSnapshot.objects.filter(announcement=announcement)
        .order_by("-version")
        .first()
    )
    return artifact, snapshot


def _audit(
    *,
    event_type: str,
    receipt: MarketingCommandReceipt,
    announcement: Announcement,
    artifact: MarketingContentArtifact | None,
    snapshot: AudienceSnapshot | None,
    reason_code: str,
    facts: dict,
    now: datetime,
    base_version: int | None = None,
) -> MarketingAuditEvent:
    base = announcement.version if base_version is None else base_version
    return MarketingAuditEvent.objects.create(
        event_type=event_type,
        command=receipt,
        announcement=announcement,
        actor_id=receipt.actor_id,
        actor_ref=receipt.actor_ref,
        snapshot=snapshot,
        artifact=artifact,
        base_version=base,
        resulting_version=base + 1,
        reason_code=reason_code,
        facts=facts,
        request_id=receipt.request_id,
        occurred_at=now,
        retention_until=now + APPROVAL_RECORD_RETENTION,
    )


def _result(execution: CommandExecution) -> TransitionResult:
    if execution.announcement is None:
        raise RuntimeError("Transition receipt has no Announcement.")
    affected = tuple(
        MarketingOutbox.objects.filter(cancelled_by_command=execution.receipt)
        .order_by("pk")
    )
    return TransitionResult(
        announcement=execution.announcement,
        receipt=execution.receipt,
        affected_outbox=affected,
        replayed=execution.replayed,
    )
