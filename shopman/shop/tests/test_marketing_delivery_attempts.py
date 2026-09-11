"""MKT-014 — provider outcome taxonomy and conservative crash recovery."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.utils import timezone

from shopman.shop.models import DeliveryAttempt, DeliveryTarget
from shopman.shop.services import marketing_delivery_attempts as attempt_service
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
)
from shopman.shop.services.marketing_delivery_attempts import (
    execute_target,
    queue_target,
    reconcile_calling,
)
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
)
from shopman.shop.services.marketing_security import MarketingAuthorizationError
from shopman.shop.tests.marketing_fakes import (
    FakeProviderFailure,
    ProgrammedProvider,
    ProviderScenario,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = pytest.mark.django_db
WORKER_ID = "attempt-test-worker"


class CanonicalFakeAdapter:
    """Translate the adversarial harness into the runtime's safe vocabulary."""

    def __init__(self, *scenarios: ProviderScenario):
        self.provider = ProgrammedProvider(*scenarios)

    def send(self, *, artifact, target_key, idempotency_token):
        try:
            response = self.provider.send(
                artifact=artifact,
                target_key=target_key,
                idempotency_token=idempotency_token,
            )
        except FakeProviderFailure as exc:
            if exc.effect_happened:
                raise ProviderCallFailure(
                    kind=ProviderOutcomeKind.UNKNOWN,
                    code="response_lost",
                ) from None
            raise ProviderCallFailure(
                kind=ProviderOutcomeKind.NOT_ATTEMPTED,
                code="connection_failed_before_write",
            ) from None
        if response.accepted:
            return ProviderOutcome(
                kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
                code="provider_accepted",
                retryable=False,
                provider_receipt_ref=response.receipt_ref,
            )
        return ProviderOutcome(
            kind=ProviderOutcomeKind.FAILED_FINAL,
            code=response.rejection_code,
            retryable=False,
        )


class ExplodingProvider:
    def send(self, **_kwargs):
        raise RuntimeError("vendor-secret phone=+5543999999999")


class MalformedProvider:
    def send(self, **_kwargs):
        return ProviderOutcome(
            kind=ProviderOutcomeKind.FAILED_FINAL,
            code="UNSAFE vendor body",
            retryable=False,
        )


class RateLimitedProvider:
    def send(self, **_kwargs):
        raise ProviderCallFailure(
            kind=ProviderOutcomeKind.FAILED_RETRYABLE,
            code="rate_limited",
            retry_after_seconds=30,
        )


def _queued_target(*, suffix: str) -> DeliveryTarget:
    outbox, _members = _graph(
        platform="instagram",
        suffix=suffix,
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    target = DeliveryTarget.objects.get(outbox=outbox)
    queue_target(target.ref)
    claimed = claim_due_targets(worker_id=WORKER_ID)
    assert [item.pk for item in claimed.targets] == [target.pk]
    return claimed.targets[0]


def _artifact() -> ResolvedDispatchArtifact:
    return ResolvedDispatchArtifact(
        platform="instagram",
        body="Fornada pronta",
        content_version=2,
    )


def _execute(target, provider, *, token="attempt-token-0001", now=None):
    artifact = _artifact()
    return execute_target(
        target.ref,
        provider=provider,
        artifact=artifact,
        idempotency_token=token,
        request_hash=artifact.artifact_hash,
        worker_id=WORKER_ID,
        now=now,
    )


def test_provider_accept_is_persisted_and_same_token_replays_without_call():
    target = _queued_target(suffix="attempt-accept")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)

    first = _execute(target, adapter)
    replay = _execute(target, adapter)

    assert first.provider_called is True
    assert replay.provider_called is False
    assert replay.replayed is True
    assert len(adapter.provider.calls) == 1
    assert first.attempt.state == DeliveryAttempt.State.COMPLETED
    assert first.attempt.outcome_kind == ProviderOutcomeKind.ACCEPTED_UNCONFIRMED
    assert first.target.state == DeliveryTarget.State.ACCEPTED
    assert first.target.provider_receipt_ref.startswith("fake_")
    assert first.attempt.idempotency_token_hash != "attempt-token-0001"


def test_freeze_after_begin_but_before_provider_call_releases_without_effect(monkeypatch):
    target = _queued_target(suffix="attempt-freeze-last-boundary")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)
    checks = 0

    def freeze_on_last_check():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise MarketingAuthorizationError(
                code="marketing_frozen",
                detail="frozen",
                status_code=423,
            )

    monkeypatch.setattr(
        "shopman.shop.services.marketing_security.require_external_effects_enabled",
        freeze_on_last_check,
    )

    with pytest.raises(MarketingAuthorizationError) as caught:
        _execute(target, adapter)

    target.refresh_from_db()
    attempt = DeliveryAttempt.objects.get(target=target)
    assert caught.value.code == "marketing_frozen"
    assert adapter.provider.calls == []
    assert attempt.state == DeliveryAttempt.State.PREPARED
    assert target.state == DeliveryTarget.State.QUEUED
    assert target.lease_owner == ""


def test_provider_rejection_is_a_final_failure():
    target = _queued_target(suffix="attempt-reject")

    result = _execute(
        target,
        CanonicalFakeAdapter(ProviderScenario.REJECT),
    )

    assert result.target.state == DeliveryTarget.State.FAILED_FINAL
    assert result.attempt.outcome_kind == ProviderOutcomeKind.FAILED_FINAL
    assert result.target.last_error_code == "provider_rejected"


def test_rate_limit_preserves_retry_after_and_retryable_state():
    target = _queued_target(suffix="attempt-rate-limit")

    result = _execute(target, RateLimitedProvider())

    assert result.target.state == DeliveryTarget.State.FAILED_RETRYABLE
    assert result.attempt.outcome_kind == ProviderOutcomeKind.FAILED_RETRYABLE
    assert result.attempt.retry_after_seconds == 30
    assert result.attempt.error_code == "rate_limited"


def test_failure_before_write_is_retryable_with_a_new_attempt_only():
    target = _queued_target(suffix="attempt-before")
    adapter = CanonicalFakeAdapter(
        ProviderScenario.FAIL_BEFORE_CALL,
        ProviderScenario.ACCEPT,
    )

    failed = _execute(target, adapter, token="attempt-token-before-1")
    queue_target(target.ref)
    queued = claim_due_targets(worker_id=WORKER_ID).targets[0]
    succeeded = _execute(queued, adapter, token="attempt-token-before-2")

    assert failed.target.state == DeliveryTarget.State.FAILED_RETRYABLE
    assert failed.attempt.outcome_kind == ProviderOutcomeKind.NOT_ATTEMPTED
    assert succeeded.target.state == DeliveryTarget.State.ACCEPTED
    assert succeeded.attempt.ordinal == 2
    assert DeliveryTarget.objects.count() == 1
    assert DeliveryAttempt.objects.count() == 2
    assert len(adapter.provider.effects) == 1


def test_effect_happened_response_lost_stays_unknown_without_blind_retry():
    target = _queued_target(suffix="attempt-lost")
    adapter = CanonicalFakeAdapter(ProviderScenario.EFFECT_HAPPENED_RESPONSE_LOST)

    result = _execute(target, adapter, token="attempt-token-lost-01")

    assert len(adapter.provider.effects) == 1
    assert result.target.state == DeliveryTarget.State.UNKNOWN
    assert result.attempt.outcome_kind == ProviderOutcomeKind.UNKNOWN
    assert result.attempt.provider_receipt_ref == ""
    with pytest.raises(MarketingContractError) as caught:
        queue_target(target.ref)
    assert caught.value.code == "invalid_delivery_transition"

    replay = _execute(target, adapter, token="attempt-token-lost-01")
    assert replay.provider_called is False
    assert len(adapter.provider.effects) == 1


def test_completed_replay_survives_target_fingerprint_key_rotation():
    target = _queued_target(suffix="attempt-key-rotation")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)
    first = _execute(target, adapter, token="attempt-token-key-rotation")

    with override_settings(
        SHOPMAN_MARKETING_TARGET_HMAC_KEY="rotated-test-only-key",
        SHOPMAN_MARKETING_TARGET_HMAC_KEY_VERSION=2,
    ):
        replay = _execute(target, adapter, token="attempt-token-key-rotation")

    assert replay.attempt.pk == first.attempt.pk
    assert replay.provider_called is False
    assert len(adapter.provider.calls) == 1


def test_unclassified_exception_becomes_sanitized_unknown():
    target = _queued_target(suffix="attempt-exception")

    result = _execute(target, ExplodingProvider())

    persisted = json.dumps(
        {
            "attempt": {
                field.name: getattr(result.attempt, field.attname)
                for field in result.attempt._meta.concrete_fields
            },
            "target": {
                field.name: getattr(result.target, field.attname)
                for field in result.target._meta.concrete_fields
            },
        },
        default=str,
    )
    assert result.target.state == DeliveryTarget.State.UNKNOWN
    assert result.attempt.error_code == "unclassified_provider_failure"
    assert "vendor-secret" not in persisted
    assert "+5543999999999" not in persisted


def test_malformed_provider_response_becomes_unknown_without_raw_detail():
    target = _queued_target(suffix="attempt-malformed")

    result = _execute(target, MalformedProvider())

    assert result.target.state == DeliveryTarget.State.UNKNOWN
    assert result.attempt.error_code == "invalid_provider_response"
    assert "UNSAFE" not in result.attempt.error_code


def test_prepared_attempt_recovers_safely_before_the_provider_boundary(monkeypatch):
    target = _queued_target(suffix="attempt-prepared")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)
    real_begin = attempt_service._begin_call

    def crash_before_boundary(*_args, **_kwargs):
        raise RuntimeError("worker stopped before provider boundary")

    monkeypatch.setattr(attempt_service, "_begin_call", crash_before_boundary)
    with pytest.raises(RuntimeError, match="before provider boundary"):
        _execute(target, adapter, token="attempt-token-prepared")

    attempt = DeliveryAttempt.objects.get()
    target.refresh_from_db()
    assert attempt.state == DeliveryAttempt.State.PREPARED
    assert target.state == DeliveryTarget.State.QUEUED
    assert adapter.provider.calls == []

    monkeypatch.setattr(attempt_service, "_begin_call", real_begin)
    recovered = _execute(target, adapter, token="attempt-token-prepared")
    assert recovered.target.state == DeliveryTarget.State.ACCEPTED
    assert len(adapter.provider.calls) == 1


def test_crash_after_effect_before_commit_reconciles_to_unknown(monkeypatch):
    started_at = timezone.now()
    target = _queued_target(suffix="attempt-after-effect")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)
    real_complete = attempt_service._complete_attempt

    def lose_commit(*_args, **_kwargs):
        raise RuntimeError("database unavailable after provider response")

    monkeypatch.setattr(attempt_service, "_complete_attempt", lose_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        _execute(
            target,
            adapter,
            token="attempt-token-after-effect",
            now=started_at,
        )

    attempt = DeliveryAttempt.objects.get()
    target.refresh_from_db()
    assert attempt.state == DeliveryAttempt.State.CALLING
    assert target.state == DeliveryTarget.State.SENDING
    assert len(adapter.provider.effects) == 1

    monkeypatch.setattr(attempt_service, "_complete_attempt", real_complete)
    assert reconcile_calling(now=started_at + timedelta(seconds=61)) == 1
    attempt.refresh_from_db()
    target.refresh_from_db()
    assert attempt.outcome_kind == ProviderOutcomeKind.UNKNOWN
    assert attempt.error_code == "call_completion_lost"
    assert target.state == DeliveryTarget.State.UNKNOWN
    assert len(adapter.provider.effects) == 1


def test_worker_that_loses_call_boundary_never_calls_provider(monkeypatch):
    target = _queued_target(suffix="attempt-boundary-race")
    adapter = CanonicalFakeAdapter(ProviderScenario.ACCEPT)
    real_begin = attempt_service._begin_call

    def competing_worker_won(*args, **kwargs):
        attempt, locked_target, _began = real_begin(*args, **kwargs)
        return attempt, locked_target, False

    monkeypatch.setattr(attempt_service, "_begin_call", competing_worker_won)
    result = _execute(target, adapter, token="attempt-token-race-01")

    assert result.in_progress is True
    assert result.provider_called is False
    assert adapter.provider.calls == []
    assert DeliveryAttempt.objects.get().state == DeliveryAttempt.State.CALLING


def test_artifact_mismatch_fails_before_creating_an_attempt():
    target = _queued_target(suffix="attempt-artifact")
    artifact = ResolvedDispatchArtifact(
        platform="whatsapp",
        body="payload errado",
        content_version=2,
    )

    with pytest.raises(MarketingContractError) as caught:
        execute_target(
            target.ref,
            provider=CanonicalFakeAdapter(ProviderScenario.ACCEPT),
            artifact=artifact,
            idempotency_token="attempt-token-artifact",
            request_hash=artifact.artifact_hash,
            worker_id=WORKER_ID,
        )

    assert caught.value.code == "delivery_artifact_mismatch"
    assert DeliveryAttempt.objects.count() == 0


def test_provider_call_failure_allows_only_failure_taxonomy():
    retryable = ProviderCallFailure(
        kind=ProviderOutcomeKind.FAILED_RETRYABLE,
        code="rate_limited",
        retry_after_seconds=30,
    ).as_outcome()

    assert retryable.retryable is True
    assert retryable.retry_after_seconds == 30
    with pytest.raises(ValueError, match="outcome de falha"):
        ProviderCallFailure(
            kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
            code="not_a_failure",
        )


@pytest.mark.django_db(transaction=True)
def test_attempt_state_migration_preserves_old_rows_conservatively():
    target = _queued_target(suffix="attempt-migration")
    attempt = DeliveryAttempt.objects.create(
        target=target,
        ordinal=1,
        state=DeliveryAttempt.State.PREPARED,
        idempotency_token_hash="b" * 64,
        request_hash="a" * 64,
        started_at=timezone.now(),
        retention_until=timezone.now() + timedelta(days=365 * 5),
    )
    before = [("shop", "0030_marketing_delivery_ledger")]
    after = [("shop", "0031_marketing_attempt_outcomes")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    OldAttempt = old_apps.get_model("shop", "DeliveryAttempt")
    assert OldAttempt.objects.get(pk=attempt.pk).state == "started"

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    NewAttempt = new_apps.get_model("shop", "DeliveryAttempt")
    assert NewAttempt.objects.get(pk=attempt.pk).state == "calling"

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
