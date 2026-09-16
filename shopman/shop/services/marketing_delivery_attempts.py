"""Persisted provider-attempt lifecycle with conservative unknown semantics."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from django.db import connection, transaction
from django.utils import timezone

from shopman.shop.models import AudienceSnapshotMember, DeliveryAttempt, DeliveryTarget
from shopman.shop.services.marketing_contracts import (
    DeliveryState,
    MarketingContractError,
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
    ensure_delivery_transition,
)

ATTEMPT_RETENTION = timedelta(days=365 * 5)
CALLING_STALE_SECONDS = 60
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_SAFE_RECEIPT_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
logger = logging.getLogger(__name__)


class DeliveryProvider(Protocol):
    def send(
        self,
        *,
        artifact: ResolvedDispatchArtifact,
        target_key: str,
        idempotency_token: str,
    ) -> ProviderOutcome: ...


@dataclass(frozen=True, slots=True)
class AttemptExecution:
    attempt: DeliveryAttempt
    target: DeliveryTarget
    provider_called: bool
    replayed: bool
    in_progress: bool = False


def deterministic_attempt_token(
    target_ref,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> str:
    """Derive the same provider token after a pre-boundary worker restart."""

    clock = _aware_now(now)
    safe_worker_id = _worker_id(worker_id)
    with transaction.atomic():
        target = DeliveryTarget.objects.select_for_update().get(ref=target_ref)
        _validate_claim(target, worker_id=safe_worker_id, now=clock)
        active = (
            DeliveryAttempt.objects.filter(
                target=target,
                state__in=(DeliveryAttempt.State.PREPARED, DeliveryAttempt.State.CALLING),
            )
            .order_by("ordinal")
            .first()
        )
        ordinal = active.ordinal if active is not None else target.attempt_count + 1
        return f"marketing:v1:{target.ref}:attempt:{ordinal}"


def queue_target(target_ref, *, now: datetime | None = None) -> DeliveryTarget:
    """Move only planned or explicitly retryable targets to the runnable queue."""

    clock = _aware_now(now)
    with transaction.atomic():
        target = DeliveryTarget.objects.select_for_update().get(ref=target_ref)
        current = DeliveryState(target.state)
        if current == DeliveryState.QUEUED:
            return target
        ensure_delivery_transition(current, DeliveryState.QUEUED)
        target.state = DeliveryTarget.State.QUEUED
        target.next_attempt_at = clock
        target.lease_owner = ""
        target.lease_until = None
        target.version += 1
        target.updated_at = clock
        target.save(
            update_fields=[
                "state",
                "next_attempt_at",
                "lease_owner",
                "lease_until",
                "version",
                "updated_at",
            ]
        )
        _schedule_aggregate(target.announcement_id)
        return target


def execute_target(
    target_ref,
    *,
    provider: DeliveryProvider,
    artifact: ResolvedDispatchArtifact,
    idempotency_token: str,
    request_hash: str,
    worker_id: str,
    now: datetime | None = None,
) -> AttemptExecution:
    """Call one provider at most once for this persisted attempt token."""

    clock = _aware_now(now)
    from shopman.shop.services.marketing_security import require_external_effects_enabled

    require_external_effects_enabled()
    safe_worker_id = _worker_id(worker_id)
    token_hash = _token_hash(idempotency_token)
    safe_request_hash = _request_hash(request_hash)
    attempt, target, replayed = _prepare_attempt(
        target_ref,
        artifact=artifact,
        worker_id=safe_worker_id,
        token_hash=token_hash,
        request_hash=safe_request_hash,
        now=clock,
    )
    if attempt.state == DeliveryAttempt.State.COMPLETED:
        return _observed_execution(AttemptExecution(attempt, target, provider_called=False, replayed=True))
    if attempt.state == DeliveryAttempt.State.CALLING:
        # Another worker (or this worker before losing its response) already
        # crossed the call boundary.  Waiting/reconciliation is safe; calling
        # again is not.
        return _observed_execution(
            AttemptExecution(
                attempt,
                target,
                provider_called=False,
                replayed=True,
                in_progress=True,
            )
        )

    try:
        attempt, target, began_call = _begin_call(
            attempt.ref,
            worker_id=safe_worker_id,
            now=clock,
        )
    except MarketingContractError as exc:
        if exc.code not in {
            "recipient_age_not_verified",
            "recipient_known_minor",
            "recipient_age_source_unavailable",
            "recipient_account_inactive",
            "recipient_identity_changed",
            "subscription_inactive",
            "subscription_unavailable",
        }:
            raise
        attempt, target = _settle_pre_provider_guard(
            attempt.ref,
            error=exc,
            now=clock,
        )
        if exc.retryable:
            raise
        return _observed_execution(
            AttemptExecution(
                attempt,
                target,
                provider_called=False,
                replayed=replayed,
            )
        )
    if not began_call:
        return _observed_execution(
            AttemptExecution(
                attempt,
                target,
                provider_called=False,
                replayed=True,
                in_progress=attempt.state == DeliveryAttempt.State.CALLING,
            )
        )
    try:
        # Last reversible check: this is intentionally adjacent to provider.send.
        require_external_effects_enabled()
    except MarketingContractError:
        _defer_frozen_call(attempt.ref, now=clock)
        raise
    try:
        outcome = provider.send(
            artifact=artifact,
            target_key=target.target_fingerprint,
            idempotency_token=idempotency_token,
        )
    except ProviderCallFailure as exc:
        outcome = exc.as_outcome()
    except Exception:
        logger.warning("marketing.delivery_provider_outcome_unclassified")
        # At this boundary an unclassified exception may have happened after
        # bytes were written.  Persist uncertainty, never raw exception text.
        outcome = ProviderOutcome(
            kind=ProviderOutcomeKind.UNKNOWN,
            code="unclassified_provider_failure",
            retryable=False,
        )

    try:
        normalized = _validated_outcome(outcome)
    except (TypeError, ValueError):
        normalized = ProviderOutcome(
            kind=ProviderOutcomeKind.UNKNOWN,
            code="invalid_provider_response",
            retryable=False,
        )
    attempt, target = _complete_attempt(attempt.ref, outcome=normalized, now=clock)
    return _observed_execution(
        AttemptExecution(
            attempt,
            target,
            provider_called=True,
            replayed=replayed,
        )
    )


def execute_approved_target(
    target_ref,
    *,
    provider: DeliveryProvider,
    idempotency_token: str,
    worker_id: str,
    now: datetime | None = None,
) -> AttemptExecution:
    """Canonical worker entrypoint: derive bytes only from sealed approval evidence."""

    from shopman.shop.services import marketing_facts
    from shopman.shop.services.marketing_artifacts import (
        resolve_target_dispatch_artifact,
    )

    target = DeliveryTarget.objects.select_related("artifact").get(ref=target_ref)
    try:
        marketing_facts.validate_for_dispatch(target.artifact, now=now)
    except MarketingContractError as exc:
        _settle_invalid_facts(target.ref, error=exc, now=_aware_now(now))
        raise
    artifact = resolve_target_dispatch_artifact(target)
    return execute_target(
        target_ref,
        provider=provider,
        artifact=artifact,
        idempotency_token=idempotency_token,
        request_hash=artifact.artifact_hash,
        worker_id=worker_id,
        now=now,
    )


def _settle_invalid_facts(
    target_ref,
    *,
    error: MarketingContractError,
    now: datetime,
) -> None:
    """Release a degraded source or expire a factual drift before provider I/O."""

    with transaction.atomic():
        target = DeliveryTarget.objects.select_for_update().get(ref=target_ref)
        if target.state != DeliveryTarget.State.QUEUED:
            return
        target.lease_owner = ""
        target.lease_until = None
        target.last_error_code = error.code
        if error.retryable:
            target.next_attempt_at = now + timedelta(seconds=30)
        else:
            ensure_delivery_transition(
                DeliveryState(target.state),
                DeliveryState.EXPIRED,
            )
            target.state = DeliveryTarget.State.EXPIRED
            target.settled_at = now
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=[
                "state",
                "lease_owner",
                "lease_until",
                "next_attempt_at",
                "last_error_code",
                "settled_at",
                "version",
                "updated_at",
            ]
        )
        _schedule_aggregate(target.announcement_id)


def _defer_frozen_call(attempt_ref, *, now: datetime) -> None:
    """Return a boundary-not-crossed attempt to a safely reclaimable state."""

    with transaction.atomic():
        attempt = DeliveryAttempt.objects.select_for_update().get(ref=attempt_ref)
        target = DeliveryTarget.objects.select_for_update().get(pk=attempt.target_id)
        if attempt.state != DeliveryAttempt.State.CALLING:
            return
        attempt.state = DeliveryAttempt.State.PREPARED
        attempt.save(update_fields=["state", "updated_at"])
        target.state = DeliveryTarget.State.QUEUED
        target.lease_owner = ""
        target.lease_until = None
        target.next_attempt_at = now + timedelta(seconds=30)
        target.last_error_code = "marketing_frozen"
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=[
                "state",
                "lease_owner",
                "lease_until",
                "next_attempt_at",
                "last_error_code",
                "version",
                "updated_at",
            ]
        )


def _settle_pre_provider_guard(
    attempt_ref,
    *,
    error: MarketingContractError,
    now: datetime,
) -> tuple[DeliveryAttempt, DeliveryTarget]:
    """Persist a last-boundary denial without pretending the provider ran."""

    with transaction.atomic():
        attempt = DeliveryAttempt.objects.select_for_update().get(ref=attempt_ref)
        target = DeliveryTarget.objects.select_for_update().get(pk=attempt.target_id)
        if attempt.state != DeliveryAttempt.State.PREPARED:
            return attempt, target

        attempt.state = DeliveryAttempt.State.COMPLETED
        attempt.outcome_kind = ProviderOutcomeKind.NOT_ATTEMPTED.value
        attempt.error_code = error.code
        attempt.completed_at = now
        attempt.save(
            update_fields=[
                "state",
                "outcome_kind",
                "error_code",
                "completed_at",
                "updated_at",
            ]
        )

        terminal = not error.retryable
        if terminal and target.state == DeliveryTarget.State.QUEUED:
            next_state = DeliveryState.SUPPRESSED
            ensure_delivery_transition(DeliveryState(target.state), next_state)
            target.state = next_state.value
        target.lease_owner = ""
        target.lease_until = None
        target.last_error_code = error.code
        target.next_attempt_at = now + timedelta(seconds=30)
        if terminal:
            target.settled_at = target.settled_at or now
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=[
                "state",
                "lease_owner",
                "lease_until",
                "next_attempt_at",
                "last_error_code",
                "settled_at",
                "version",
                "updated_at",
            ]
        )
        _schedule_aggregate(target.announcement_id)
        return attempt, target


def reconcile_calling(
    *,
    now: datetime | None = None,
    stale_seconds: int = CALLING_STALE_SECONDS,
    limit: int = 100,
) -> int:
    """Turn abandoned post-boundary calls into unknown without invoking provider."""

    clock = _aware_now(now)
    cutoff = clock - timedelta(seconds=max(10, int(stale_seconds)))
    safe_limit = max(1, min(int(limit), 1_000))
    query = DeliveryAttempt.objects.filter(
        state=DeliveryAttempt.State.CALLING,
        started_at__lte=cutoff,
    ).order_by("started_at", "pk")
    if connection.features.has_select_for_update_skip_locked:
        query = query.select_for_update(skip_locked=True)
    else:
        query = query.select_for_update()
    reconciled = 0
    with transaction.atomic():
        refs = list(query.values_list("ref", flat=True)[:safe_limit])
        for attempt_ref in refs:
            attempt, target = _complete_attempt(
                attempt_ref,
                outcome=ProviderOutcome(
                    kind=ProviderOutcomeKind.UNKNOWN,
                    code="call_completion_lost",
                    retryable=False,
                ),
                now=clock,
            )
            _observed_execution(
                AttemptExecution(
                    attempt,
                    target,
                    provider_called=False,
                    replayed=False,
                )
            )
            reconciled += 1
    return reconciled


def _observed_execution(execution: AttemptExecution) -> AttemptExecution:
    from shopman.shop.services.marketing_observability import (
        record_delivery_execution,
    )

    record_delivery_execution(
        platform=execution.target.platform,
        outcome=execution.attempt.outcome_kind,
        replayed=execution.replayed,
        target_ref=str(execution.target.ref),
        attempt_ref=str(execution.attempt.ref),
    )
    return execution


def _prepare_attempt(
    target_ref,
    *,
    artifact: ResolvedDispatchArtifact,
    worker_id: str,
    token_hash: str,
    request_hash: str,
    now: datetime,
) -> tuple[DeliveryAttempt, DeliveryTarget, bool]:
    with transaction.atomic():
        target = DeliveryTarget.objects.select_for_update().select_related("artifact").get(ref=target_ref)
        _validate_artifact(target, artifact, request_hash)
        existing = DeliveryAttempt.objects.filter(
            target=target,
            idempotency_token_hash=token_hash,
        ).first()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise MarketingContractError(
                    code="delivery_attempt_idempotency_conflict",
                    detail="O token desta tentativa pertence a outro payload.",
                )
            if existing.state == DeliveryAttempt.State.PREPARED:
                _validate_claim(target, worker_id=worker_id, now=now)
            return existing, target, True
        if target.state != DeliveryTarget.State.QUEUED:
            raise MarketingContractError(
                code="delivery_target_not_queued",
                detail="O target não está disponível para uma nova tentativa.",
            )
        _validate_claim(target, worker_id=worker_id, now=now)
        if DeliveryAttempt.objects.filter(
            target=target,
            state__in=(DeliveryAttempt.State.PREPARED, DeliveryAttempt.State.CALLING),
        ).exists():
            raise MarketingContractError(
                code="delivery_attempt_in_progress",
                detail="Já existe uma tentativa ativa para este target.",
            )
        ordinal = target.attempt_count + 1
        attempt = DeliveryAttempt.objects.create(
            target=target,
            ordinal=ordinal,
            state=DeliveryAttempt.State.PREPARED,
            idempotency_token_hash=token_hash,
            request_hash=request_hash,
            started_at=now,
            retention_until=now + ATTEMPT_RETENTION,
        )
        target.attempt_count = ordinal
        target.version += 1
        target.updated_at = now
        target.save(update_fields=["attempt_count", "version", "updated_at"])
        return attempt, target, False


def _begin_call(
    attempt_ref,
    *,
    worker_id: str,
    now: datetime,
) -> tuple[DeliveryAttempt, DeliveryTarget, bool]:
    with transaction.atomic():
        # Descobrir o titular sem lock permite adquirir a cerca canônica na
        # ordem Customer -> Attempt -> Target. A exclusão usa Customer ->
        # Target; compartilhar a ordem elimina a janela em que um envio direto
        # poderia cruzar o provider depois do recibo de exclusão.
        identity = (
            DeliveryAttempt.objects.filter(ref=attempt_ref)
            .values(
                "target_id",
                "target__member_id",
                "target__member__customer_id",
            )
            .first()
        )
        if identity is None:
            raise DeliveryAttempt.DoesNotExist
        customer_id = identity["target__member__customer_id"]
        if customer_id is not None:
            from shopman.guestman.models import Customer

            customer = Customer.objects.select_for_update().filter(pk=customer_id).only("pk", "is_active").first()
            if customer is None or not customer.is_active:
                raise MarketingContractError(
                    code="recipient_account_inactive",
                    detail="A conta destinatária não está mais ativa.",
                )
        attempt = DeliveryAttempt.objects.select_for_update().select_related("target").get(ref=attempt_ref)
        if attempt.state != DeliveryAttempt.State.PREPARED:
            return attempt, attempt.target, False
        # Do not join the nullable ``member`` relation under FOR UPDATE:
        # PostgreSQL refuses to lock the nullable side of an outer join.
        target = DeliveryTarget.objects.select_for_update().get(pk=attempt.target_id)
        current_customer_id = None
        if target.member_id is not None:
            current_customer_id = (
                AudienceSnapshotMember.objects.filter(pk=target.member_id).values_list("customer_id", flat=True).first()
            )
        if current_customer_id != customer_id:
            raise MarketingContractError(
                code="recipient_identity_changed",
                detail="A identidade destinatária mudou antes do envio.",
            )
        if target.state != DeliveryTarget.State.QUEUED:
            raise MarketingContractError(
                code="delivery_target_not_queued",
                detail="O target mudou antes da chamada ao provider.",
            )
        _validate_claim(target, worker_id=worker_id, now=now)
        _validate_recipient_age_at_provider_boundary(target, now=now)
        ensure_delivery_transition(DeliveryState(target.state), DeliveryState.SENDING)
        attempt.state = DeliveryAttempt.State.CALLING
        attempt.save(update_fields=["state", "updated_at"])
        target.state = DeliveryTarget.State.SENDING
        target.lease_owner = ""
        target.lease_until = None
        target.last_attempt_at = now
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=[
                "state",
                "lease_owner",
                "lease_until",
                "last_attempt_at",
                "version",
                "updated_at",
            ]
        )
        return attempt, target, True


def _validate_recipient_age_at_provider_boundary(
    target: DeliveryTarget,
    *,
    now: datetime,
) -> None:
    """Re-read age evidence immediately before crossing the provider boundary."""

    from shopman.shop.services.marketing_capabilities import persisted_identity

    delivery_kind, _delivery_format = persisted_identity(target)
    if delivery_kind == "publication":
        return

    member = target.member
    if member is None:
        raise MarketingContractError(
            code="recipient_age_not_verified",
            detail="A idade do destinatário não pôde ser comprovada.",
        )

    from shopman.shop.services.marketing_age import (
        canonical_birthday_for_customer_id,
        is_known_adult,
        is_known_minor,
    )

    try:
        birthday = canonical_birthday_for_customer_id(member.customer_id)
    except Exception as exc:
        raise MarketingContractError(
            code="recipient_age_source_unavailable",
            detail="A fonte canônica de idade está temporariamente indisponível.",
            retryable=True,
        ) from exc
    reasons = frozenset(member.reasons or [])
    is_alert_delivery = bool("alerts" in reasons and member.subscription_ref)
    if is_alert_delivery:
        if is_known_minor(birthday):
            raise MarketingContractError(
                code="recipient_known_minor",
                detail="A data de nascimento canônica indica menoridade.",
            )
        try:
            from shopman.shop.adapters.audience_sources import (
                active_alert_subscription_refs,
            )

            active_refs = active_alert_subscription_refs(
                {member.subscription_ref},
                now=now,
            )
        except Exception as exc:
            raise MarketingContractError(
                code="subscription_unavailable",
                detail="A prova específica do aviso está temporariamente indisponível.",
                retryable=True,
            ) from exc
        if member.subscription_ref not in active_refs:
            raise MarketingContractError(
                code="subscription_inactive",
                detail="A inscrição específica do aviso não está mais ativa.",
            )
        return

    if not is_known_adult(birthday):
        raise MarketingContractError(
            code="recipient_age_not_verified",
            detail="O cadastro não comprova idade igual ou superior a 18 anos.",
        )


def _complete_attempt(
    attempt_ref,
    *,
    outcome: ProviderOutcome,
    now: datetime,
) -> tuple[DeliveryAttempt, DeliveryTarget]:
    with transaction.atomic():
        attempt = DeliveryAttempt.objects.select_for_update().get(ref=attempt_ref)
        target = DeliveryTarget.objects.select_for_update().get(pk=attempt.target_id)
        if attempt.state == DeliveryAttempt.State.COMPLETED:
            return attempt, target
        if attempt.state != DeliveryAttempt.State.CALLING:
            raise MarketingContractError(
                code="delivery_call_not_started",
                detail="A tentativa ainda não cruzou o boundary do provider.",
            )
        target_state = _target_state(outcome.kind)
        ensure_delivery_transition(DeliveryState(target.state), target_state)
        safe_code = _safe_code(outcome.code)
        safe_receipt = _safe_receipt(outcome.provider_receipt_ref)

        attempt.state = DeliveryAttempt.State.COMPLETED
        attempt.outcome_kind = outcome.kind.value
        attempt.provider_receipt_ref = safe_receipt
        attempt.error_code = safe_code
        attempt.retry_after_seconds = outcome.retry_after_seconds
        attempt.completed_at = now
        attempt.save(
            update_fields=[
                "state",
                "outcome_kind",
                "provider_receipt_ref",
                "error_code",
                "retry_after_seconds",
                "completed_at",
                "updated_at",
            ]
        )
        target.state = target_state.value
        target.last_error_code = (
            safe_code
            if outcome.kind
            not in {
                ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
                ProviderOutcomeKind.CONFIRMED,
            }
            else ""
        )
        target.provider_receipt_ref = safe_receipt
        target.provider_ref_retention_until = now + timedelta(days=180) if safe_receipt else None
        target.settled_at = None if target_state in {DeliveryState.FAILED_RETRYABLE, DeliveryState.UNKNOWN} else now
        target.version += 1
        target.updated_at = now
        target.save(
            update_fields=[
                "state",
                "last_error_code",
                "provider_receipt_ref",
                "provider_ref_retention_until",
                "settled_at",
                "version",
                "updated_at",
            ]
        )
        _schedule_aggregate(target.announcement_id)
        return attempt, target


def _validated_outcome(value) -> ProviderOutcome:
    if not isinstance(value, ProviderOutcome):
        raise TypeError("provider must return ProviderOutcome")
    _safe_code(value.code)
    _safe_receipt(value.provider_receipt_ref)
    if value.retry_after_seconds is not None and not 0 < value.retry_after_seconds <= 86_400:
        raise ValueError("invalid retry_after_seconds")
    return value


def _validate_artifact(
    target: DeliveryTarget,
    artifact: ResolvedDispatchArtifact,
    request_hash: str,
) -> None:
    if not isinstance(artifact, ResolvedDispatchArtifact):
        raise MarketingContractError(
            code="invalid_delivery_artifact",
            detail="O payload resolvido da tentativa é inválido.",
        )
    if artifact.platform != target.platform or artifact.content_version != target.artifact.version:
        raise MarketingContractError(
            code="delivery_artifact_mismatch",
            detail="O payload resolvido não pertence à versão e plataforma aprovadas.",
        )
    from shopman.shop.services.marketing_artifacts import (
        resolve_target_dispatch_artifact,
    )

    approved = resolve_target_dispatch_artifact(target)
    if not hmac.compare_digest(artifact.artifact_hash, approved.artifact_hash):
        raise MarketingContractError(
            code="delivery_artifact_mismatch",
            detail="O payload resolvido diverge do conteúdo aprovado.",
        )
    if not hmac.compare_digest(artifact.artifact_hash, request_hash):
        raise MarketingContractError(
            code="delivery_request_hash_mismatch",
            detail="O hash da tentativa não corresponde ao payload resolvido.",
        )


def _target_state(kind: ProviderOutcomeKind) -> DeliveryState:
    return {
        ProviderOutcomeKind.NOT_ATTEMPTED: DeliveryState.FAILED_RETRYABLE,
        ProviderOutcomeKind.ACCEPTED_UNCONFIRMED: DeliveryState.ACCEPTED,
        ProviderOutcomeKind.CONFIRMED: DeliveryState.CONFIRMED,
        ProviderOutcomeKind.FAILED_RETRYABLE: DeliveryState.FAILED_RETRYABLE,
        ProviderOutcomeKind.FAILED_FINAL: DeliveryState.FAILED_FINAL,
        ProviderOutcomeKind.UNKNOWN: DeliveryState.UNKNOWN,
    }[kind]


def _token_hash(value: str) -> str:
    token = str(value or "")
    if not 16 <= len(token) <= 200 or any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise MarketingContractError(
            code="invalid_delivery_idempotency_token",
            detail="O token interno da tentativa é inválido.",
        )
    # Attempt tokens are high-entropy internal identifiers rather than PII.
    # A stable one-way digest keeps replay valid across fingerprint-key rotation.
    return hashlib.sha256(f"marketing-delivery-attempt:{token}".encode()).hexdigest()


def _request_hash(value: str) -> str:
    normalized = str(value or "")
    if not _HASH_RE.fullmatch(normalized):
        raise MarketingContractError(
            code="invalid_delivery_request_hash",
            detail="O hash do payload da tentativa é inválido.",
        )
    return normalized


def _validate_claim(target: DeliveryTarget, *, worker_id: str, now: datetime) -> None:
    if target.lease_owner != worker_id or target.lease_until is None or target.lease_until <= now:
        raise MarketingContractError(
            code="delivery_target_not_leased",
            detail="O worker não possui um lease ativo para este target.",
        )


def _worker_id(value: str) -> str:
    normalized = str(value or "")
    if not _WORKER_ID_RE.fullmatch(normalized):
        raise MarketingContractError(
            code="invalid_delivery_worker_id",
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
        raise ValueError("Marketing delivery attempts require an aware clock.")
    return value


def _schedule_aggregate(announcement_id: int) -> None:
    from shopman.shop.services.marketing_delivery_aggregate import (
        schedule_delivery_refresh,
    )

    schedule_delivery_refresh(announcement_id)
