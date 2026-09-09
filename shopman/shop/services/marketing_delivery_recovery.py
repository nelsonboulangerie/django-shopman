"""Selective delivery retry and lookup-only reconciliation commands.

Operator commands choose a platform scope, never recipient identities.  The
server locks the Announcement and selects only the currently eligible targets.
Retry can queue ``failed_retryable``; uncertainty creates a durable lookup job
whose provider protocol intentionally has no ``send`` method.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AudienceSnapshot,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingContentArtifact,
)
from shopman.shop.services.marketing_approval import APPROVAL_RECORD_RETENTION
from shopman.shop.services.marketing_commands import (
    CommandExecution,
    RejectCommand,
    execute_announcement_command,
)
from shopman.shop.services.marketing_contracts import (
    DeliveryState,
    MarketingContractError,
    ProviderOutcome,
    ProviderOutcomeKind,
    ensure_delivery_transition,
)

RECONCILIATION_RETRY_SECONDS = 30
DEFAULT_RECONCILIATION_LIMIT = 100
DEFAULT_RECONCILIATION_LEASE_SECONDS = 60
_PLATFORM_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_SAFE_RECEIPT_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = logging.getLogger(__name__)


class DeliveryLookupProvider(Protocol):
    """Read-only provider capability used for uncertain effects."""

    def lookup(
        self,
        *,
        target_key: str,
        idempotency_token: str,
        provider_receipt_ref: str,
    ) -> ProviderOutcome: ...


@dataclass(frozen=True, slots=True)
class RecoveryCommandResult:
    announcement: Announcement
    receipt: MarketingCommandReceipt
    affected_count: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class DeliveryRecoveryAction:
    action: str
    method: str
    href: str
    enabled: bool
    disabled_reason: str
    eligible_count: int
    required_permission: str
    confirmation_required: bool
    creates_external_effect: bool


@dataclass(frozen=True, slots=True)
class ReconciliationClaimReport:
    reconciliations: tuple[DeliveryReconciliation, ...]
    stale_reclaimed: int


@dataclass(frozen=True, slots=True)
class ReconciliationExecution:
    reconciliation: DeliveryReconciliation
    target: DeliveryTarget
    provider_called: bool
    replayed: bool
    deferred: bool = False


def retry_failed_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    platforms=(),
    request_id: str = "",
    now: datetime | None = None,
    authorization: Callable[[object, MarketingCommandReceipt], None] | None = None,
) -> RecoveryCommandResult:
    """Queue only proven retryable failures in the requested platform scope."""

    clock = _aware_now(now)
    requested = _platforms(platforms)

    def operation(announcement, receipt):
        selected_platforms = _selected_platforms(announcement, requested)
        query = DeliveryTarget.objects.select_for_update().filter(
            announcement=announcement,
            state=DeliveryTarget.State.FAILED_RETRYABLE,
        )
        if selected_platforms:
            query = query.filter(platform__in=selected_platforms)
        targets = list(query.order_by("platform", "pk"))
        if not targets:
            raise RejectCommand(
                code="nothing_retryable",
                detail="Não há falha segura para tentar novamente nesta seleção.",
                outcome={"platforms": list(selected_platforms)},
            )
        if DeliveryAttempt.objects.filter(
            target_id__in=[target.pk for target in targets],
            state__in=(DeliveryAttempt.State.PREPARED, DeliveryAttempt.State.CALLING),
        ).exists():
            raise RejectCommand(
                code="delivery_attempt_in_progress",
                detail="Uma tentativa desta seleção ainda está em andamento.",
            )

        selection_hash = _selection_hash(targets)
        artifact, _snapshot = _latest_graph(announcement)
        if authorization is not None:
            from shopman.shop.services.marketing_security import (
                ACTION_RETRY,
                authorization_context,
            )

            authorization(
                authorization_context(
                    action=ACTION_RETRY,
                    resource_ref=f"announcement:{announcement.pk}",
                    base_version=announcement.version,
                    artifact_hash=artifact.artifact_hash if artifact else "",
                    audience_hash=selection_hash,
                    audience_count=len(targets),
                    platforms=selected_platforms,
                    consequence="retries_only_proven_safe_failures_now",
                ),
                receipt,
            )
        for target in targets:
            ensure_delivery_transition(
                DeliveryState(target.state),
                DeliveryState.QUEUED,
            )
            target.state = DeliveryTarget.State.QUEUED
            target.next_attempt_at = clock
            target.lease_owner = ""
            target.lease_until = None
            target.last_error_code = ""
            target.settled_at = None
            target.version += 1
            target.updated_at = clock
        DeliveryTarget.objects.bulk_update(targets, [
            "state",
            "next_attempt_at",
            "lease_owner",
            "lease_until",
            "last_error_code",
            "settled_at",
            "version",
            "updated_at",
        ])
        _audit(
            event_type=MarketingAuditEvent.EventType.DELIVERY_RETRIED,
            receipt=receipt,
            announcement=announcement,
            reason_code="operator_retry_failed",
            facts={
                "queued_count": len(targets),
                "platforms": list(selected_platforms),
                "selection_hash": selection_hash,
            },
            now=clock,
        )
        _schedule_aggregate(announcement.pk)
        return {
            "queued_count": len(targets),
            "platforms": list(selected_platforms),
            "selection_hash": selection_hash,
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.RETRY_DELIVERY,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload={"platforms": list(requested)},
        operation=operation,
        request_id=request_id,
    )
    return _command_result(execution, "queued_count")


def request_reconciliation_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    platforms=(),
    request_id: str = "",
    now: datetime | None = None,
    authorization: Callable[[object, MarketingCommandReceipt], None] | None = None,
) -> RecoveryCommandResult:
    """Persist lookup jobs for unknown targets without calling a provider."""

    clock = _aware_now(now)
    requested = _platforms(platforms)

    def operation(announcement, receipt):
        selected_platforms = _selected_platforms(announcement, requested)
        query = DeliveryTarget.objects.select_for_update().filter(
            announcement=announcement,
            state=DeliveryTarget.State.UNKNOWN,
        )
        if selected_platforms:
            query = query.filter(platform__in=selected_platforms)
        unknown_targets = list(query.order_by("platform", "pk"))
        if not unknown_targets:
            raise RejectCommand(
                code="nothing_reconcilable",
                detail="Não há resultado desconhecido nesta seleção.",
                outcome={"platforms": list(selected_platforms)},
            )

        target_ids = [target.pk for target in unknown_targets]
        active_target_ids = set(
            DeliveryReconciliation.objects.select_for_update()
            .filter(
                target_id__in=target_ids,
                state__in=(
                    DeliveryReconciliation.State.PENDING,
                    DeliveryReconciliation.State.CLAIMED,
                ),
            )
            .values_list("target_id", flat=True)
        )
        latest_unknown_attempts: dict[int, DeliveryAttempt] = {}
        for attempt in (
            DeliveryAttempt.objects.filter(
                target_id__in=target_ids,
                state=DeliveryAttempt.State.COMPLETED,
                outcome_kind=ProviderOutcomeKind.UNKNOWN.value,
            )
            .order_by("target_id", "-ordinal")
        ):
            latest_unknown_attempts.setdefault(attempt.target_id, attempt)

        eligible = [
            target
            for target in unknown_targets
            if target.pk not in active_target_ids
            and target.pk in latest_unknown_attempts
        ]
        if not eligible:
            code = (
                "reconciliation_already_pending"
                if active_target_ids
                else "unknown_without_attempt"
            )
            detail = (
                "A reconciliação desta seleção já está em andamento."
                if active_target_ids
                else "O resultado desconhecido não tem tentativa consultável."
            )
            raise RejectCommand(code=code, detail=detail)

        selection_hash = _selection_hash(eligible)
        artifact, _snapshot = _latest_graph(announcement)
        if authorization is not None:
            from shopman.shop.services.marketing_security import (
                ACTION_RECONCILE,
                authorization_context,
            )

            authorization(
                authorization_context(
                    action=ACTION_RECONCILE,
                    resource_ref=f"announcement:{announcement.pk}",
                    base_version=announcement.version,
                    artifact_hash=artifact.artifact_hash if artifact else "",
                    audience_hash=selection_hash,
                    audience_count=len(eligible),
                    platforms=selected_platforms,
                    consequence="lookup_only_unknown_provider_outcomes",
                ),
                receipt,
            )
        DeliveryReconciliation.objects.bulk_create([
            DeliveryReconciliation(
                command=receipt,
                target=target,
                attempt=latest_unknown_attempts[target.pk],
                available_at=clock,
                retention_until=clock + APPROVAL_RECORD_RETENTION,
            )
            for target in eligible
        ])
        _audit(
            event_type=MarketingAuditEvent.EventType.RECONCILIATION_REQUESTED,
            receipt=receipt,
            announcement=announcement,
            reason_code="operator_reconcile_unknown",
            facts={
                "already_pending_count": len(active_target_ids),
                "lookup_count": len(eligible),
                "platforms": list(selected_platforms),
                "selection_hash": selection_hash,
                "without_attempt_count": len(unknown_targets)
                - len(active_target_ids)
                - len(eligible),
            },
            now=clock,
        )
        return {
            "already_pending_count": len(active_target_ids),
            "lookup_count": len(eligible),
            "platforms": list(selected_platforms),
            "selection_hash": selection_hash,
            "without_attempt_count": len(unknown_targets)
            - len(active_target_ids)
            - len(eligible),
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.RECONCILE_DELIVERY,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload={"platforms": list(requested)},
        operation=operation,
        request_id=request_id,
    )
    return _command_result(execution, "lookup_count")


def resolve_delivery_recovery_actions(
    announcement: Announcement,
    *,
    actor,
) -> tuple[DeliveryRecoveryAction, DeliveryRecoveryAction]:
    """Resolve authority and eligibility once so browser clients never infer it."""

    retry_count = DeliveryTarget.objects.filter(
        announcement=announcement,
        state=DeliveryTarget.State.FAILED_RETRYABLE,
    ).count()
    reconcilable_ids = DeliveryTarget.objects.filter(
        announcement=announcement,
        state=DeliveryTarget.State.UNKNOWN,
        attempts__state=DeliveryAttempt.State.COMPLETED,
        attempts__outcome_kind=ProviderOutcomeKind.UNKNOWN.value,
    ).values_list("pk", flat=True).distinct()
    active_ids = DeliveryReconciliation.objects.filter(
        target_id__in=reconcilable_ids,
        state__in=(
            DeliveryReconciliation.State.PENDING,
            DeliveryReconciliation.State.CLAIMED,
        ),
    ).values_list("target_id", flat=True)
    reconcile_count = reconcilable_ids.exclude(pk__in=active_ids).count()
    pending_count = active_ids.count()
    base = f"/api/v1/backstage/marketing/announcements/{announcement.pk}"
    return (
        _action(
            action="retry_failed",
            href=f"{base}/retry-deliveries/",
            eligible_count=retry_count,
            actor=actor,
            permission="shop.retry_failed_marketing",
            no_eligible_reason="no_retryable_failures",
            confirmation_required=True,
            creates_external_effect=True,
        ),
        _action(
            action="reconcile_unknown",
            href=f"{base}/reconcile-deliveries/",
            eligible_count=reconcile_count,
            actor=actor,
            permission="shop.reconcile_unknown_marketing",
            no_eligible_reason=(
                "reconciliation_pending" if pending_count else "no_unknown_results"
            ),
            confirmation_required=True,
            creates_external_effect=False,
        ),
    )


def claim_reconciliations(
    *,
    worker_id: str,
    now: datetime | None = None,
    limit: int = DEFAULT_RECONCILIATION_LIMIT,
    lease_seconds: int = DEFAULT_RECONCILIATION_LEASE_SECONDS,
) -> ReconciliationClaimReport:
    """Lease due lookup jobs and recover abandoned lookup leases."""

    clock = _aware_now(now)
    safe_worker_id = _worker_id(worker_id)
    safe_limit = max(1, min(int(limit), 1_000))
    safe_lease = max(10, min(int(lease_seconds), 15 * 60))
    with transaction.atomic():
        query = DeliveryReconciliation.objects.filter(
            Q(state=DeliveryReconciliation.State.PENDING)
            | Q(
                state=DeliveryReconciliation.State.CLAIMED,
                lease_until__lte=clock,
            ),
            available_at__lte=clock,
        ).order_by("available_at", "pk")
        if connection.features.has_select_for_update_skip_locked:
            query = query.select_for_update(skip_locked=True)
        else:
            query = query.select_for_update()
        rows = list(query[:safe_limit])
        stale_reclaimed = sum(
            row.state == DeliveryReconciliation.State.CLAIMED for row in rows
        )
        for row in rows:
            row.state = DeliveryReconciliation.State.CLAIMED
            row.lease_owner = safe_worker_id
            row.lease_until = clock + timedelta(seconds=safe_lease)
            row.lookup_attempts += 1
            row.last_error_code = ""
            row.updated_at = clock
        if rows:
            DeliveryReconciliation.objects.bulk_update(rows, [
                "state",
                "lease_owner",
                "lease_until",
                "lookup_attempts",
                "last_error_code",
                "updated_at",
            ])
        return ReconciliationClaimReport(tuple(rows), stale_reclaimed)


def execute_reconciliation(
    reconciliation_ref,
    *,
    provider: DeliveryLookupProvider,
    worker_id: str,
    now: datetime | None = None,
) -> ReconciliationExecution:
    """Perform one idempotent lookup and monotonically resolve its target."""

    clock = _aware_now(now)
    safe_worker_id = _worker_id(worker_id)
    with transaction.atomic():
        reconciliation = (
            DeliveryReconciliation.objects.select_for_update()
            .select_related("target", "attempt")
            .get(ref=reconciliation_ref)
        )
        if reconciliation.state == DeliveryReconciliation.State.COMPLETED:
            return ReconciliationExecution(
                reconciliation,
                reconciliation.target,
                provider_called=False,
                replayed=True,
            )
        _validate_reconciliation_claim(
            reconciliation,
            worker_id=safe_worker_id,
            now=clock,
        )
        target_key = reconciliation.target.target_fingerprint
        attempt_token = (
            f"marketing:v1:{reconciliation.target.ref}:"
            f"attempt:{reconciliation.attempt.ordinal}"
        )
        provider_receipt_ref = reconciliation.attempt.provider_receipt_ref

    try:
        outcome = provider.lookup(
            target_key=target_key,
            idempotency_token=attempt_token,
            provider_receipt_ref=provider_receipt_ref,
        )
        normalized = _validated_lookup_outcome(outcome)
    except Exception:
        logger.warning("marketing.reconciliation_provider_lookup_failed")
        reconciliation, target = _defer_reconciliation(
            reconciliation.ref,
            worker_id=safe_worker_id,
            now=clock,
        )
        return ReconciliationExecution(
            reconciliation,
            target,
            provider_called=True,
            replayed=False,
            deferred=True,
        )

    reconciliation, target = _complete_reconciliation(
        reconciliation.ref,
        outcome=normalized,
        worker_id=safe_worker_id,
        now=clock,
    )
    return ReconciliationExecution(
        reconciliation,
        target,
        provider_called=True,
        replayed=False,
    )


def _complete_reconciliation(
    reconciliation_ref,
    *,
    outcome: ProviderOutcome,
    worker_id: str,
    now: datetime,
) -> tuple[DeliveryReconciliation, DeliveryTarget]:
    with transaction.atomic():
        reconciliation = DeliveryReconciliation.objects.select_for_update().get(
            ref=reconciliation_ref
        )
        target = DeliveryTarget.objects.select_for_update().get(
            pk=reconciliation.target_id
        )
        if reconciliation.state == DeliveryReconciliation.State.COMPLETED:
            return reconciliation, target
        _validate_reconciliation_claim(
            reconciliation,
            worker_id=worker_id,
            now=now,
        )
        resolved_state = _lookup_target_state(outcome.kind)
        current_state = DeliveryState(target.state)
        should_apply = current_state == DeliveryState.UNKNOWN or (
            current_state == DeliveryState.ACCEPTED
            and resolved_state == DeliveryState.CONFIRMED
        )
        if should_apply:
            ensure_delivery_transition(current_state, resolved_state)
            target.state = resolved_state.value
            target.last_error_code = (
                ""
                if resolved_state
                in {DeliveryState.ACCEPTED, DeliveryState.CONFIRMED}
                else _safe_code(outcome.code)
            )
            safe_receipt = _safe_receipt(outcome.provider_receipt_ref)
            if safe_receipt:
                target.provider_receipt_ref = safe_receipt
                target.provider_ref_retention_until = now + timedelta(days=180)
            target.settled_at = (
                None
                if resolved_state
                in {DeliveryState.FAILED_RETRYABLE, DeliveryState.UNKNOWN}
                else now
            )
            target.version += 1
            target.updated_at = now
            target.save(update_fields=[
                "state",
                "last_error_code",
                "provider_receipt_ref",
                "provider_ref_retention_until",
                "settled_at",
                "version",
                "updated_at",
            ])

        reconciliation.state = DeliveryReconciliation.State.COMPLETED
        reconciliation.lease_owner = ""
        reconciliation.lease_until = None
        reconciliation.outcome_kind = outcome.kind.value
        reconciliation.provider_receipt_ref = _safe_receipt(
            outcome.provider_receipt_ref
        )
        reconciliation.last_error_code = _safe_code(outcome.code)
        reconciliation.completed_at = now
        reconciliation.updated_at = now
        reconciliation.save(update_fields=[
            "state",
            "lease_owner",
            "lease_until",
            "outcome_kind",
            "provider_receipt_ref",
            "last_error_code",
            "completed_at",
            "updated_at",
        ])
        _schedule_aggregate(target.announcement_id)
        return reconciliation, target


def _defer_reconciliation(
    reconciliation_ref,
    *,
    worker_id: str,
    now: datetime,
) -> tuple[DeliveryReconciliation, DeliveryTarget]:
    with transaction.atomic():
        reconciliation = (
            DeliveryReconciliation.objects.select_for_update()
            .select_related("target")
            .get(ref=reconciliation_ref)
        )
        if reconciliation.state == DeliveryReconciliation.State.COMPLETED:
            return reconciliation, reconciliation.target
        _validate_reconciliation_claim(
            reconciliation,
            worker_id=worker_id,
            now=now,
        )
        reconciliation.state = DeliveryReconciliation.State.PENDING
        reconciliation.available_at = now + timedelta(
            seconds=RECONCILIATION_RETRY_SECONDS
        )
        reconciliation.lease_owner = ""
        reconciliation.lease_until = None
        reconciliation.last_error_code = "provider_lookup_unavailable"
        reconciliation.updated_at = now
        reconciliation.save(update_fields=[
            "state",
            "available_at",
            "lease_owner",
            "lease_until",
            "last_error_code",
            "updated_at",
        ])
        return reconciliation, reconciliation.target


def _lookup_target_state(kind: ProviderOutcomeKind) -> DeliveryState:
    return {
        ProviderOutcomeKind.NOT_ATTEMPTED: DeliveryState.FAILED_RETRYABLE,
        ProviderOutcomeKind.ACCEPTED_UNCONFIRMED: DeliveryState.ACCEPTED,
        ProviderOutcomeKind.CONFIRMED: DeliveryState.CONFIRMED,
        ProviderOutcomeKind.FAILED_RETRYABLE: DeliveryState.FAILED_RETRYABLE,
        ProviderOutcomeKind.FAILED_FINAL: DeliveryState.FAILED_FINAL,
        ProviderOutcomeKind.UNKNOWN: DeliveryState.UNKNOWN,
    }[kind]


def _validated_lookup_outcome(value) -> ProviderOutcome:
    if not isinstance(value, ProviderOutcome):
        raise TypeError("lookup provider must return ProviderOutcome")
    _safe_code(value.code)
    _safe_receipt(value.provider_receipt_ref)
    if (
        value.retry_after_seconds is not None
        and not 0 < value.retry_after_seconds <= 86_400
    ):
        raise ValueError("invalid retry_after_seconds")
    return value


def _selected_platforms(
    announcement: Announcement,
    requested: tuple[str, ...],
) -> tuple[str, ...]:
    approved = tuple(dict.fromkeys(str(value) for value in announcement.platforms))
    if not requested:
        return approved
    missing = sorted(set(requested) - set(approved))
    if missing:
        raise RejectCommand(
            code="platform_outside_announcement",
            detail="A seleção inclui plataforma fora do anúncio aprovado.",
            outcome={"invalid_platforms": missing},
            field_errors={"platforms": ("Use somente plataformas deste anúncio.",)},
        )
    return requested


def _platforms(values) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise MarketingContractError(
            code="invalid_platforms",
            detail="Plataformas devem ser uma lista.",
            field_errors={"platforms": ("Envie uma lista de identificadores.",)},
        )
    try:
        normalized = tuple(
            dict.fromkeys(str(value or "").strip() for value in values)
        )
    except TypeError as exc:
        raise MarketingContractError(
            code="invalid_platforms",
            detail="Plataformas devem ser uma lista.",
            field_errors={"platforms": ("Envie uma lista de identificadores.",)},
        ) from exc
    if len(normalized) > 10 or any(
        not _PLATFORM_RE.fullmatch(platform) for platform in normalized
    ):
        raise MarketingContractError(
            code="invalid_platforms",
            detail="A seleção de plataformas é inválida.",
            field_errors={"platforms": ("Use identificadores conhecidos.",)},
        )
    return normalized


def _selection_hash(targets: list[DeliveryTarget]) -> str:
    refs = ":".join(sorted(str(target.ref) for target in targets))
    return hashlib.sha256(f"marketing-recovery:v1:{refs}".encode()).hexdigest()


def _latest_graph(
    announcement: Announcement,
) -> tuple[MarketingContentArtifact | None, AudienceSnapshot | None]:
    return (
        MarketingContentArtifact.objects.filter(announcement=announcement)
        .order_by("-version")
        .first(),
        AudienceSnapshot.objects.filter(announcement=announcement)
        .order_by("-version")
        .first(),
    )


def _audit(
    *,
    event_type: str,
    receipt: MarketingCommandReceipt,
    announcement: Announcement,
    reason_code: str,
    facts: dict,
    now: datetime,
) -> MarketingAuditEvent:
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
    return MarketingAuditEvent.objects.create(
        event_type=event_type,
        command=receipt,
        announcement=announcement,
        actor_id=receipt.actor_id,
        actor_ref=receipt.actor_ref,
        snapshot=snapshot,
        artifact=artifact,
        base_version=announcement.version,
        resulting_version=announcement.version + 1,
        reason_code=reason_code,
        facts=facts,
        request_id=receipt.request_id,
        occurred_at=now,
        retention_until=now + APPROVAL_RECORD_RETENTION,
    )


def _command_result(
    execution: CommandExecution,
    count_key: str,
) -> RecoveryCommandResult:
    if execution.announcement is None:
        raise RuntimeError("Recovery receipt has no Announcement.")
    return RecoveryCommandResult(
        announcement=execution.announcement,
        receipt=execution.receipt,
        affected_count=int((execution.receipt.outcome or {}).get(count_key, 0)),
        replayed=execution.replayed,
    )


def _action(
    *,
    action: str,
    href: str,
    eligible_count: int,
    actor,
    permission: str,
    no_eligible_reason: str,
    confirmation_required: bool,
    creates_external_effect: bool,
) -> DeliveryRecoveryAction:
    allowed = bool(getattr(actor, "has_perm", lambda _code: False)(permission))
    enabled = eligible_count > 0 and allowed
    disabled_reason = ""
    if not eligible_count:
        disabled_reason = no_eligible_reason
    elif not allowed:
        disabled_reason = "missing_capability"
    return DeliveryRecoveryAction(
        action=action,
        method="POST",
        href=href,
        enabled=enabled,
        disabled_reason=disabled_reason,
        eligible_count=eligible_count,
        required_permission=permission,
        confirmation_required=confirmation_required,
        creates_external_effect=creates_external_effect,
    )


def _validate_reconciliation_claim(
    reconciliation: DeliveryReconciliation,
    *,
    worker_id: str,
    now: datetime,
) -> None:
    if (
        reconciliation.state != DeliveryReconciliation.State.CLAIMED
        or reconciliation.lease_owner != worker_id
        or reconciliation.lease_until is None
        or reconciliation.lease_until <= now
    ):
        raise MarketingContractError(
            code="reconciliation_not_leased",
            detail="O worker não possui um lease ativo para esta reconciliação.",
        )


def _worker_id(value: str) -> str:
    normalized = str(value or "")
    if not _WORKER_ID_RE.fullmatch(normalized):
        raise MarketingContractError(
            code="invalid_reconciliation_worker_id",
            detail="A identidade técnica do worker é inválida.",
        )
    return normalized


def _safe_code(value: str) -> str:
    normalized = str(value or "")
    if not _SAFE_CODE_RE.fullmatch(normalized):
        raise ValueError("provider code is not allowlisted")
    return normalized


def _safe_receipt(value: str) -> str:
    normalized = str(value or "")
    if normalized and not _SAFE_RECEIPT_RE.fullmatch(normalized):
        raise ValueError("provider receipt ref is not allowlisted")
    return normalized


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing delivery recovery requires an aware clock.")
    return value


def _schedule_aggregate(announcement_id: int) -> None:
    from shopman.shop.services.marketing_delivery_aggregate import (
        schedule_delivery_refresh,
    )

    schedule_delivery_refresh(announcement_id)
