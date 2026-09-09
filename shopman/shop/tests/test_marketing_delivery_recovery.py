"""MKT-017 — selective retry and lookup-only reconciliation."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from shopman.shop.models import (
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingAuditEvent,
    MarketingCommandReceipt,
)
from shopman.shop.services.marketing_commands import MarketingCommandRejected
from shopman.shop.services.marketing_contracts import (
    ProviderOutcome,
    ProviderOutcomeKind,
)
from shopman.shop.services.marketing_delivery_recovery import (
    claim_reconciliations,
    execute_reconciliation,
    request_reconciliation_command,
    retry_failed_command,
)
from shopman.shop.services.marketing_delivery_worker import fanout_in_chunks
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = pytest.mark.django_db
WORKER_ID = "recovery-test-worker"


class LookupOnlyProvider:
    def __init__(self, outcome: ProviderOutcome):
        self.outcome = outcome
        self.lookups = []
        self.sends = []

    def lookup(self, **kwargs):
        self.lookups.append(kwargs)
        return self.outcome

    def send(self, **kwargs):  # pragma: no cover - must never be reachable
        self.sends.append(kwargs)
        raise AssertionError("reconciliation must never send")


class ExplodingLookupProvider:
    def __init__(self):
        self.lookups = 0

    def lookup(self, **_kwargs):
        self.lookups += 1
        raise RuntimeError("vendor-secret phone=+5543999999999")


def _actor(suffix: str, *permissions: str):
    actor = get_user_model().objects.create_user(
        username=f"recovery-{suffix}",
        password="x",
        is_staff=True,
    )
    actor.user_permissions.add(
        *Permission.objects.filter(codename__in=permissions)
    )
    return actor


def _targets(*, suffix: str, states: tuple[str, ...]):
    outbox, members = _graph(
        suffix=suffix,
        target_keys=tuple(f"member-{index}" for index in range(len(states))),
    )
    fanout_in_chunks(outbox.ref, member_ids=[member.pk for member in members])
    targets = list(DeliveryTarget.objects.filter(outbox=outbox).order_by("pk"))
    now = timezone.now()
    for target, state in zip(targets, states, strict=True):
        target.state = state
        target.settled_at = (
            None
            if state
            in {
                DeliveryTarget.State.QUEUED,
                DeliveryTarget.State.FAILED_RETRYABLE,
                DeliveryTarget.State.UNKNOWN,
            }
            else now
        )
    DeliveryTarget.objects.bulk_update(targets, ["state", "settled_at"])
    for index, target in enumerate(targets, start=1):
        if target.state not in {
            DeliveryTarget.State.FAILED_RETRYABLE,
            DeliveryTarget.State.UNKNOWN,
        }:
            continue
        outcome = (
            ProviderOutcomeKind.UNKNOWN.value
            if target.state == DeliveryTarget.State.UNKNOWN
            else ProviderOutcomeKind.FAILED_RETRYABLE.value
        )
        DeliveryAttempt.objects.create(
            target=target,
            ordinal=1,
            state=DeliveryAttempt.State.COMPLETED,
            outcome_kind=outcome,
            idempotency_token_hash=f"{index:064x}",
            request_hash=f"{index + 100:064x}",
            error_code=(
                "response_lost"
                if outcome == ProviderOutcomeKind.UNKNOWN.value
                else "rate_limited"
            ),
            started_at=now,
            completed_at=now,
            retention_until=now + timedelta(days=365 * 5),
        )
        target.attempt_count = 1
        target.save(update_fields=["attempt_count"])
    return outbox.announcement, targets


def _outcome(kind: ProviderOutcomeKind, *, receipt="") -> ProviderOutcome:
    return ProviderOutcome(
        kind=kind,
        code={
            ProviderOutcomeKind.CONFIRMED: "provider_confirmed",
            ProviderOutcomeKind.ACCEPTED_UNCONFIRMED: "provider_accepted",
            ProviderOutcomeKind.FAILED_FINAL: "provider_rejected",
            ProviderOutcomeKind.NOT_ATTEMPTED: "provider_found_no_effect",
            ProviderOutcomeKind.FAILED_RETRYABLE: "provider_found_no_effect",
            ProviderOutcomeKind.UNKNOWN: "provider_still_unknown",
        }[kind],
        retryable=kind
        in {
            ProviderOutcomeKind.NOT_ATTEMPTED,
            ProviderOutcomeKind.FAILED_RETRYABLE,
        },
        provider_receipt_ref=receipt,
    )


def test_retry_queues_only_retryable_and_replay_changes_nothing_twice():
    announcement, targets = _targets(
        suffix="retry-selective",
        states=(
            DeliveryTarget.State.FAILED_RETRYABLE,
            DeliveryTarget.State.ACCEPTED,
            DeliveryTarget.State.CONFIRMED,
            DeliveryTarget.State.UNKNOWN,
        ),
    )
    actor = _actor("retry")
    original_versions = {target.pk: target.version for target in targets}

    first = retry_failed_command(
        announcement.pk,
        actor=actor,
        idempotency_key="retry-command-key-0001",
        base_version=announcement.version,
    )
    replay = retry_failed_command(
        announcement.pk,
        actor=actor,
        idempotency_key="retry-command-key-0001",
        base_version=announcement.version,
    )

    current = list(DeliveryTarget.objects.order_by("pk"))
    assert [target.state for target in current] == [
        DeliveryTarget.State.QUEUED,
        DeliveryTarget.State.ACCEPTED,
        DeliveryTarget.State.CONFIRMED,
        DeliveryTarget.State.UNKNOWN,
    ]
    assert current[0].version == original_versions[current[0].pk] + 1
    assert all(
        target.version == original_versions[target.pk] for target in current[1:]
    )
    assert first.affected_count == replay.affected_count == 1
    assert replay.replayed is True
    assert first.receipt.pk == replay.receipt.pk
    assert DeliveryAttempt.objects.count() == 2
    audit = MarketingAuditEvent.objects.get(command=first.receipt)
    assert audit.event_type == MarketingAuditEvent.EventType.DELIVERY_RETRIED
    assert audit.facts["queued_count"] == 1
    assert "target" not in json.dumps(audit.facts)


def test_retry_rejects_when_selection_has_no_safe_failure():
    announcement, targets = _targets(
        suffix="retry-none",
        states=(DeliveryTarget.State.ACCEPTED, DeliveryTarget.State.UNKNOWN),
    )
    actor = _actor("retry-none")

    with pytest.raises(MarketingCommandRejected) as caught:
        retry_failed_command(
            announcement.pk,
            actor=actor,
            idempotency_key="retry-command-key-none",
            base_version=announcement.version,
        )

    assert caught.value.code == "nothing_retryable"
    assert list(DeliveryTarget.objects.values_list("state", flat=True)) == [
        target.state for target in targets
    ]
    assert MarketingCommandReceipt.objects.filter(
        kind=MarketingCommandReceipt.Kind.RETRY_DELIVERY,
        state=MarketingCommandReceipt.State.REJECTED,
    ).count() == 1


def test_reconcile_command_persists_lookup_work_without_provider_call():
    announcement, targets = _targets(
        suffix="reconcile-intent",
        states=(DeliveryTarget.State.UNKNOWN, DeliveryTarget.State.ACCEPTED),
    )
    actor = _actor("reconcile-intent")

    result = request_reconciliation_command(
        announcement.pk,
        actor=actor,
        idempotency_key="reconcile-command-0001",
        base_version=announcement.version,
    )

    job = DeliveryReconciliation.objects.get()
    assert result.affected_count == 1
    assert job.target_id == targets[0].pk
    assert job.attempt.outcome_kind == ProviderOutcomeKind.UNKNOWN.value
    assert job.state == DeliveryReconciliation.State.PENDING
    assert targets[1].reconciliations.count() == 0
    assert MarketingAuditEvent.objects.get(
        command=result.receipt
    ).event_type == MarketingAuditEvent.EventType.RECONCILIATION_REQUESTED


@pytest.mark.parametrize(
    ("provider_kind", "target_state"),
    [
        (ProviderOutcomeKind.ACCEPTED_UNCONFIRMED, DeliveryTarget.State.ACCEPTED),
        (ProviderOutcomeKind.CONFIRMED, DeliveryTarget.State.CONFIRMED),
        (ProviderOutcomeKind.FAILED_FINAL, DeliveryTarget.State.FAILED_FINAL),
        (ProviderOutcomeKind.NOT_ATTEMPTED, DeliveryTarget.State.FAILED_RETRYABLE),
        (ProviderOutcomeKind.UNKNOWN, DeliveryTarget.State.UNKNOWN),
    ],
)
def test_lookup_monotonically_resolves_unknown_without_send(
    provider_kind,
    target_state,
):
    announcement, _targets_list = _targets(
        suffix=f"lookup-{provider_kind.value}",
        states=(DeliveryTarget.State.UNKNOWN,),
    )
    actor = _actor(f"lookup-{provider_kind.value}")
    request_reconciliation_command(
        announcement.pk,
        actor=actor,
        idempotency_key=f"reconcile-{provider_kind.value}-key",
        base_version=announcement.version,
    )
    job = claim_reconciliations(worker_id=WORKER_ID).reconciliations[0]
    provider = LookupOnlyProvider(
        _outcome(
            provider_kind,
            receipt=("receipt-123" if provider_kind == ProviderOutcomeKind.CONFIRMED else ""),
        )
    )

    result = execute_reconciliation(
        job.ref,
        provider=provider,
        worker_id=WORKER_ID,
    )
    replay = execute_reconciliation(
        job.ref,
        provider=provider,
        worker_id=WORKER_ID,
    )

    assert result.target.state == target_state
    assert result.reconciliation.state == DeliveryReconciliation.State.COMPLETED
    assert len(provider.lookups) == 1
    assert provider.sends == []
    assert replay.replayed is True
    assert replay.provider_called is False


def test_lookup_outage_is_sanitized_and_safely_requeued():
    now = timezone.now()
    announcement, _targets_list = _targets(
        suffix="lookup-outage",
        states=(DeliveryTarget.State.UNKNOWN,),
    )
    actor = _actor("lookup-outage")
    request_reconciliation_command(
        announcement.pk,
        actor=actor,
        idempotency_key="reconcile-outage-key",
        base_version=announcement.version,
        now=now,
    )
    job = claim_reconciliations(worker_id=WORKER_ID, now=now).reconciliations[0]
    provider = ExplodingLookupProvider()

    result = execute_reconciliation(
        job.ref,
        provider=provider,
        worker_id=WORKER_ID,
        now=now,
    )

    assert result.deferred is True
    assert result.target.state == DeliveryTarget.State.UNKNOWN
    assert result.reconciliation.state == DeliveryReconciliation.State.PENDING
    assert result.reconciliation.last_error_code == "provider_lookup_unavailable"
    assert result.reconciliation.available_at == now + timedelta(seconds=30)
    persisted = json.dumps(
        {
            field.name: getattr(result.reconciliation, field.attname)
            for field in result.reconciliation._meta.concrete_fields
        },
        default=str,
    )
    assert "vendor-secret" not in persisted
    assert "+5543999999999" not in persisted


def test_abandoned_reconciliation_lease_is_recovered_without_send():
    now = timezone.now()
    announcement, _targets_list = _targets(
        suffix="lookup-lease",
        states=(DeliveryTarget.State.UNKNOWN,),
    )
    actor = _actor("lookup-lease")
    request_reconciliation_command(
        announcement.pk,
        actor=actor,
        idempotency_key="reconcile-lease-key",
        base_version=announcement.version,
        now=now,
    )

    first = claim_reconciliations(worker_id="worker-one", now=now)
    blocked = claim_reconciliations(
        worker_id="worker-two",
        now=now + timedelta(seconds=30),
    )
    recovered = claim_reconciliations(
        worker_id="worker-two",
        now=now + timedelta(seconds=61),
    )

    assert len(first.reconciliations) == 1
    assert blocked.reconciliations == ()
    assert len(recovered.reconciliations) == 1
    assert recovered.stale_reclaimed == 1
    assert recovered.reconciliations[0].lease_owner == "worker-two"
    assert recovered.reconciliations[0].lookup_attempts == 2


def test_recovery_api_enforces_distinct_capabilities(client):
    announcement, _targets_list = _targets(
        suffix="api",
        states=(DeliveryTarget.State.FAILED_RETRYABLE, DeliveryTarget.State.UNKNOWN),
    )
    observer = _actor("api-observer", "view_marketing")
    operator = _actor(
        "api-operator",
        "view_marketing",
        "retry_failed_marketing",
        "reconcile_unknown_marketing",
    )
    base = f"/api/v1/backstage/marketing/announcements/{announcement.pk}"

    client.force_login(observer)
    actions_response = client.get(f"{base}/delivery-actions/")
    assert actions_response.status_code == 200
    assert [action["enabled"] for action in actions_response.json()["actions"]] == [
        False,
        False,
    ]
    assert client.post(
        f"{base}/retry-deliveries/",
        data={"base_version": announcement.version},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="retry-api-key-0001",
    ).status_code == 403

    client.force_login(operator)
    retry_response = client.post(
        f"{base}/retry-deliveries/",
        data={"base_version": announcement.version},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="retry-api-key-0001",
    )
    retry_confirmation = retry_response.json()["confirmation"]
    assert retry_response.status_code == 428
    assert retry_confirmation["step_up"] == "password"
    step_up = client.post(
        "/api/v1/backstage/marketing/security/step-up/",
        data={"method": "password", "credential": "x"},
        content_type="application/json",
    )
    assert step_up.status_code == 200
    retry_response = client.post(
        f"{base}/retry-deliveries/",
        data={
            "base_version": announcement.version,
            "confirmation_token": retry_confirmation["token"],
            "typed_confirmation": retry_confirmation["typed_phrase"],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="retry-api-key-0001",
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["receipt"]["outcome"]["queued_count"] == 1

    announcement.refresh_from_db()
    reconcile_response = client.post(
        f"{base}/reconcile-deliveries/",
        data={"base_version": announcement.version},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="reconcile-api-key-0001",
    )
    reconciliation_confirmation = reconcile_response.json()["confirmation"]
    assert reconcile_response.status_code == 428
    assert reconciliation_confirmation["step_up"] == "totp"
    assert DeliveryReconciliation.objects.count() == 0

    from django_otp.oath import totp
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.create(user=operator, name="recovery", confirmed=True)
    token = str(
        totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    ).zfill(device.digits)
    step_up = client.post(
        "/api/v1/backstage/marketing/security/step-up/",
        data={"method": "totp", "credential": token},
        content_type="application/json",
    )
    assert step_up.status_code == 200
    reconcile_response = client.post(
        f"{base}/reconcile-deliveries/",
        data={
            "base_version": announcement.version,
            "confirmation_token": reconciliation_confirmation["token"],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="reconcile-api-key-0001",
    )
    assert reconcile_response.status_code == 200
    assert reconcile_response.json()["receipt"]["outcome"]["lookup_count"] == 1
    assert DeliveryReconciliation.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_reconciliation_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0033_marketing_delivery_aggregate")]
    after = [("shop", "0034_marketing_delivery_recovery")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    assert "shop_deliveryreconciliation" not in set(
        connection.introspection.table_names()
    )

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    assert "shop_deliveryreconciliation" in set(
        connection.introspection.table_names()
    )

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    assert "shop_deliveryreconciliation" not in set(
        connection.introspection.table_names()
    )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
