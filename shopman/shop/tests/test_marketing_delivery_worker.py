"""MKT-015 — bounded fan-out, leases and pre-send suppression."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    ConsentProofStatus,
)

from shopman.shop.models import DeliveryTarget
from shopman.shop.services import marketing_delivery_attempts as attempt_service
from shopman.shop.services import marketing_delivery_worker as worker_service
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderOutcome,
    ProviderOutcomeKind,
    ResolvedDispatchArtifact,
)
from shopman.shop.services.marketing_delivery_attempts import (
    deterministic_attempt_token,
    execute_target,
    queue_target,
)
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db


class CountingAcceptedProvider:
    def __init__(self):
        self.calls = 0

    def send(self, **_kwargs):
        self.calls += 1
        return ProviderOutcome(
            kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
            code="provider_accepted",
            retryable=False,
            provider_receipt_ref=f"fake_claim_{self.calls}",
        )


def test_row_lock_targets_only_the_base_table_when_backend_supports_of(monkeypatch):
    class QueryProbe:
        kwargs = None

        def select_for_update(self, **kwargs):
            self.kwargs = kwargs
            return self

    query = QueryProbe()
    monkeypatch.setattr(
        worker_service.connection.features,
        "has_select_for_update_of",
        True,
    )
    monkeypatch.setattr(
        worker_service.connection.features,
        "has_select_for_update_skip_locked",
        True,
    )

    assert worker_service._select_for_update(query) is query
    assert query.kwargs == {"of": ("self",), "skip_locked": True}


def _fanout_whatsapp(*, suffix: str, count: int, opted_in: bool = False):
    outbox, members = _graph(
        platform="whatsapp",
        suffix=suffix,
        target_keys=tuple(f"member-{index}" for index in range(count)),
    )
    if opted_in:
        for member in members:
            ConsentService.grant_consent(
                member.customer.ref,
                "whatsapp",
                source="delivery-worker-test",
            )
    report = fanout_in_chunks(
        outbox.ref,
        member_ids=[member.pk for member in members],
    )
    return outbox, members, report


def _queue_all(outbox):
    for target in DeliveryTarget.objects.filter(outbox=outbox):
        queue_target(target.ref)


def _artifact(platform: str) -> ResolvedDispatchArtifact:
    return ResolvedDispatchArtifact(
        platform=platform,
        body="Fornada pronta",
        content_version=2,
    )


def _next_quiet_time() -> datetime:
    local = timezone.now().astimezone(ZoneInfo("America/Sao_Paulo"))
    return (local + timedelta(days=1)).replace(
        hour=21,
        minute=0,
        second=0,
        microsecond=0,
    )


def _next_allowed_time() -> datetime:
    local = timezone.now().astimezone(ZoneInfo("America/Sao_Paulo"))
    return (local + timedelta(days=1)).replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    )


def test_fanout_progress_is_derived_and_bounded_without_operator_cursor():
    outbox, members = _graph(
        platform="whatsapp",
        suffix="fanout-bounded",
        target_keys=tuple(f"member-{index}" for index in range(205)),
    )
    member_ids = [member.pk for member in members]

    first = fanout_in_chunks(
        outbox.ref,
        member_ids=member_ids,
        chunk_size=50,
        max_chunks=2,
    )
    _queue_all(outbox)
    assert claim_due_targets(worker_id="worker-before-complete").examined == 0
    second = fanout_in_chunks(
        outbox.ref,
        member_ids=reversed(member_ids),
        chunk_size=50,
        max_chunks=2,
    )
    third = fanout_in_chunks(
        outbox.ref,
        member_ids=member_ids,
        chunk_size=50,
        max_chunks=2,
    )

    assert (first.created, first.remaining, first.complete) == (100, 105, False)
    assert (second.existing, second.created, second.remaining) == (100, 100, 5)
    assert (third.existing, third.created, third.remaining, third.complete) == (
        200,
        5,
        0,
        True,
    )
    assert DeliveryTarget.objects.filter(outbox=outbox).count() == 205


def test_kill_between_chunks_commits_progress_and_replay_finishes(monkeypatch):
    outbox, members = _graph(
        platform="whatsapp",
        suffix="fanout-kill",
        target_keys=tuple(f"member-{index}" for index in range(80)),
    )
    member_ids = [member.pk for member in members]
    real_ensure = worker_service.ensure_targets
    calls = 0

    def kill_second_chunk(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("worker killed between chunks")
        return real_ensure(*args, **kwargs)

    monkeypatch.setattr(worker_service, "ensure_targets", kill_second_chunk)
    with pytest.raises(RuntimeError, match="killed between chunks"):
        fanout_in_chunks(
            outbox.ref,
            member_ids=member_ids,
            chunk_size=25,
        )
    assert DeliveryTarget.objects.filter(outbox=outbox).count() == 25
    _queue_all(outbox)
    assert claim_due_targets(worker_id="worker-after-kill").examined == 0

    monkeypatch.setattr(worker_service, "ensure_targets", real_ensure)
    recovered = fanout_in_chunks(
        outbox.ref,
        member_ids=member_ids,
        chunk_size=25,
    )
    assert (recovered.existing, recovered.created, recovered.remaining) == (25, 55, 0)
    assert recovered.complete is True
    assert DeliveryTarget.objects.filter(outbox=outbox).count() == 80


def test_full_selection_is_validated_before_first_chunk():
    outbox, members = _graph(
        platform="whatsapp",
        suffix="fanout-invalid",
        target_keys=("inside",),
    )

    with pytest.raises(MarketingContractError) as caught:
        fanout_in_chunks(
            outbox.ref,
            member_ids=[members[0].pk, members[0].pk + 999_999],
            chunk_size=1,
        )

    assert caught.value.code == "delivery_member_outside_snapshot"
    assert DeliveryTarget.objects.count() == 0


def test_same_lane_cannot_resume_with_a_different_selection():
    outbox, members = _graph(
        platform="whatsapp",
        suffix="fanout-selection-conflict",
        target_keys=("one", "two", "three", "four"),
    )
    first_selection = [members[0].pk, members[1].pk]
    changed_selection = [members[2].pk, members[3].pk]
    fanout_in_chunks(outbox.ref, member_ids=first_selection)

    with pytest.raises(MarketingContractError) as caught:
        fanout_in_chunks(outbox.ref, member_ids=changed_selection)

    outbox.refresh_from_db()
    assert caught.value.code == "delivery_fanout_selection_conflict"
    assert len(outbox.fanout_selection_hash) == 64
    assert outbox.fanout_expected == outbox.fanout_materialized == 2
    assert DeliveryTarget.objects.filter(outbox=outbox).count() == 2


def test_public_fanout_is_one_target_and_replay_is_a_noop():
    outbox, _members = _graph(
        platform="instagram",
        suffix="fanout-public",
        target_keys=(),
    )

    first = fanout_in_chunks(outbox.ref)
    replay = fanout_in_chunks(outbox.ref)

    assert (first.requested, first.created, first.complete) == (1, 1, True)
    assert (replay.existing, replay.created, replay.complete) == (1, 0, True)
    assert DeliveryTarget.objects.count() == 1


def test_revocation_after_fanout_suppresses_before_claim_and_provider():
    outbox, members, _report = _fanout_whatsapp(
        suffix="claim-revoked",
        count=1,
        opted_in=True,
    )
    target = DeliveryTarget.objects.get(outbox=outbox)
    queue_target(target.ref)
    ConsentService.revoke_consent(members[0].customer.ref, "whatsapp")
    provider = CountingAcceptedProvider()

    claimed = claim_due_targets(
        worker_id="worker-revoked",
        now=_next_quiet_time(),
    )

    target.refresh_from_db()
    assert claimed.targets == ()
    assert claimed.suppressed == 1
    assert target.state == DeliveryTarget.State.SUPPRESSED
    assert target.last_error_code == "global_optout"
    with pytest.raises(MarketingContractError) as caught:
        artifact = _artifact("whatsapp")
        execute_target(
            target.ref,
            provider=provider,
            artifact=artifact,
            idempotency_token="attempt-token-revoked",
            request_hash=artifact.artifact_hash,
            worker_id="worker-revoked",
        )
    assert caught.value.code == "delivery_target_not_queued"
    assert provider.calls == 0


def test_legacy_unverified_optin_is_suppressed_by_batched_recheck():
    outbox, members, _report = _fanout_whatsapp(
        suffix="claim-legacy",
        count=1,
    )
    customer = members[0].customer
    CommunicationConsent.objects.create(
        customer=customer,
        channel="whatsapp",
        status="opted_in",
        proof_status=ConsentProofStatus.LEGACY_UNVERIFIED,
        source="legacy_import",
    )
    _queue_all(outbox)

    report = claim_due_targets(worker_id="worker-legacy")

    target = DeliveryTarget.objects.get(outbox=outbox)
    assert ConsentService.get_customer_statuses("whatsapp", {customer.ref}) == {
        customer.ref: "pending"
    }
    assert report.suppressed == 1
    assert target.state == DeliveryTarget.State.SUPPRESSED
    assert target.last_error_code == "missing_consent"


def test_consent_outage_defers_without_lease_or_false_zero():
    outbox, _members, _report = _fanout_whatsapp(
        suffix="claim-consent-outage",
        count=1,
        opted_in=True,
    )
    _queue_all(outbox)
    now = timezone.now()

    with patch(
        "shopman.guestman.ConsentService.get_customer_statuses",
        side_effect=RuntimeError("consent store unavailable"),
    ):
        report = claim_due_targets(worker_id="worker-outage", now=now)

    target = DeliveryTarget.objects.get(outbox=outbox)
    assert (report.examined, report.deferred, report.suppressed) == (1, 1, 0)
    assert target.state == DeliveryTarget.State.QUEUED
    assert target.lease_owner == ""
    assert target.lease_until is None
    assert target.last_error_code == "consent_unavailable"
    assert target.next_attempt_at == now + timedelta(seconds=30)


def test_delayed_whatsapp_worker_waits_until_the_next_allowed_shop_time():
    outbox, _members, _report = _fanout_whatsapp(
        suffix="claim-quiet-hours",
        count=1,
        opted_in=True,
    )
    _queue_all(outbox)
    quiet_now = _next_quiet_time()

    deferred = claim_due_targets(
        worker_id="worker-quiet-hours",
        now=quiet_now,
    )

    target = DeliveryTarget.objects.get(outbox=outbox)
    assert (deferred.examined, deferred.deferred) == (1, 1)
    assert deferred.targets == ()
    assert target.last_error_code == "quiet_hours_active"
    assert target.next_attempt_at == quiet_now + timedelta(hours=11)

    opened = claim_due_targets(
        worker_id="worker-opening-hours",
        now=target.next_attempt_at,
    )

    assert [item.pk for item in opened.targets] == [target.pk]


def test_revoked_specific_subscription_is_suppressed_before_claim():
    outbox, members, _report = _fanout_whatsapp(
        suffix="claim-subscription",
        count=1,
    )
    customer = members[0].customer
    subscription = stock_alerts.subscribe("SKU-WORKER", customer=customer)
    member = members[0]
    member.subscription_ref = subscription.ref
    member.reasons = ["alerts"]
    member.save(update_fields=["subscription_ref", "reasons"])
    stock_alerts.revoke(
        subscription.ref,
        sku=subscription.sku,
        customer=customer,
    )
    _queue_all(outbox)

    report = claim_due_targets(
        worker_id="worker-subscription",
        now=_next_quiet_time(),
    )

    target = DeliveryTarget.objects.get(outbox=outbox)
    assert report.suppressed == 1
    assert target.state == DeliveryTarget.State.SUPPRESSED
    assert target.last_error_code == "subscription_inactive"


def test_expired_announcement_expires_public_target_before_claim():
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-expired",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    _queue_all(outbox)
    now = timezone.now()
    outbox.announcement.expires_at = now - timedelta(seconds=1)
    outbox.announcement.save(update_fields=["expires_at"])

    report = claim_due_targets(worker_id="worker-expired", now=now)

    target = DeliveryTarget.objects.get(outbox=outbox)
    assert report.expired == 1
    assert report.targets == ()
    assert target.state == DeliveryTarget.State.EXPIRED
    assert target.last_error_code == "announcement_expired_before_send"


def test_settled_announcement_claims_only_a_previously_attempted_retry():
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-settled-selective-retry",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    _queue_all(outbox)
    target = DeliveryTarget.objects.get(outbox=outbox)
    outbox.announcement.status = "settled"
    outbox.announcement.save(update_fields=["status"])

    initial = claim_due_targets(worker_id="worker-settled-initial")
    target.refresh_from_db()
    assert initial.targets == ()
    assert initial.deferred == 1
    assert target.last_error_code == "announcement_not_dispatchable"

    target.attempt_count = 1
    target.next_attempt_at = timezone.now()
    target.save(update_fields=["attempt_count", "next_attempt_at"])

    retry = claim_due_targets(worker_id="worker-settled-retry")
    assert [item.pk for item in retry.targets] == [target.pk]


def test_active_lease_fences_other_worker_and_is_cleared_at_call_boundary():
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-fence",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    _queue_all(outbox)
    first = claim_due_targets(worker_id="worker-one", lease_seconds=60)
    provider = CountingAcceptedProvider()
    target = first.targets[0]

    assert claim_due_targets(worker_id="worker-two").examined == 0
    artifact = _artifact("instagram")
    with pytest.raises(MarketingContractError) as caught:
        execute_target(
            target.ref,
            provider=provider,
            artifact=artifact,
            idempotency_token="attempt-token-wrong-worker",
            request_hash=artifact.artifact_hash,
            worker_id="worker-two",
        )
    assert caught.value.code == "delivery_target_not_leased"
    assert provider.calls == 0

    result = execute_target(
        target.ref,
        provider=provider,
        artifact=artifact,
        idempotency_token="attempt-token-right-worker",
        request_hash=artifact.artifact_hash,
        worker_id="worker-one",
    )
    assert result.target.state == DeliveryTarget.State.ACCEPTED
    assert result.target.lease_owner == ""
    assert result.target.lease_until is None
    assert provider.calls == 1


def test_stale_lease_is_reclaimed_but_unexpired_lease_is_not():
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-stale",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    _queue_all(outbox)
    now = timezone.now()

    first = claim_due_targets(
        worker_id="worker-stale-one",
        now=now,
        lease_seconds=10,
    )
    blocked = claim_due_targets(
        worker_id="worker-stale-two",
        now=now + timedelta(seconds=9),
    )
    reclaimed = claim_due_targets(
        worker_id="worker-stale-two",
        now=now + timedelta(seconds=11),
    )

    assert len(first.targets) == 1
    assert blocked.examined == 0
    assert len(reclaimed.targets) == 1
    assert reclaimed.stale_reclaimed == 1
    assert reclaimed.targets[0].lease_owner == "worker-stale-two"


def test_new_worker_reconstructs_prepared_attempt_token_after_stale_lease(monkeypatch):
    now = timezone.now()
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-prepared-recovery",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref, now=now)
    _queue_all(outbox)
    first = claim_due_targets(
        worker_id="worker-prepared-one",
        now=timezone.now(),
        lease_seconds=10,
    )
    target = first.targets[0]
    first_clock = target.lease_until - timedelta(seconds=10)
    token = deterministic_attempt_token(
        target.ref,
        worker_id="worker-prepared-one",
        now=first_clock,
    )
    artifact = _artifact("instagram")
    real_begin = attempt_service._begin_call

    def stop_before_boundary(*_args, **_kwargs):
        raise RuntimeError("worker stopped before call")

    monkeypatch.setattr(attempt_service, "_begin_call", stop_before_boundary)
    with pytest.raises(RuntimeError, match="stopped before call"):
        execute_target(
            target.ref,
            provider=CountingAcceptedProvider(),
            artifact=artifact,
            idempotency_token=token,
            request_hash=artifact.artifact_hash,
            worker_id="worker-prepared-one",
            now=first_clock,
        )

    second_clock = target.lease_until + timedelta(seconds=1)
    reclaimed = claim_due_targets(
        worker_id="worker-prepared-two",
        now=second_clock,
        lease_seconds=10,
    )
    recovered_token = deterministic_attempt_token(
        target.ref,
        worker_id="worker-prepared-two",
        now=second_clock,
    )
    assert recovered_token == token
    assert reclaimed.stale_reclaimed == 1

    monkeypatch.setattr(attempt_service, "_begin_call", real_begin)
    provider = CountingAcceptedProvider()
    result = execute_target(
        target.ref,
        provider=provider,
        artifact=artifact,
        idempotency_token=recovered_token,
        request_hash=artifact.artifact_hash,
        worker_id="worker-prepared-two",
        now=second_clock,
    )
    assert result.target.state == DeliveryTarget.State.ACCEPTED
    assert result.attempt.ordinal == 1
    assert provider.calls == 1


def test_claim_limit_applies_backpressure_across_workers():
    outbox, _members, _report = _fanout_whatsapp(
        suffix="claim-limit",
        count=12,
        opted_in=True,
    )
    _queue_all(outbox)
    allowed_now = _next_allowed_time()

    first = claim_due_targets(worker_id="worker-limit-one", limit=5, now=allowed_now)
    second = claim_due_targets(worker_id="worker-limit-two", limit=5, now=allowed_now)
    third = claim_due_targets(worker_id="worker-limit-three", limit=5, now=allowed_now)

    assert [len(report.targets) for report in (first, second, third)] == [5, 5, 2]
    assert DeliveryTarget.objects.filter(lease_owner="worker-limit-one").count() == 5
    assert DeliveryTarget.objects.filter(lease_owner="worker-limit-two").count() == 5
    assert DeliveryTarget.objects.filter(lease_owner="worker-limit-three").count() == 2


def test_claim_of_100_recipients_stays_within_query_budget(django_assert_max_num_queries):
    outbox, _members, _report = _fanout_whatsapp(
        suffix="claim-query-budget",
        count=100,
        opted_in=True,
    )
    _queue_all(outbox)

    with django_assert_max_num_queries(10):
        report = claim_due_targets(
            worker_id="worker-query-budget",
            limit=100,
            now=_next_allowed_time(),
        )

    assert len(report.targets) == 100
    assert report.deferred == report.suppressed == 0


def test_database_rejects_lease_outside_queued_state():
    outbox, _members = _graph(
        platform="instagram",
        suffix="claim-constraint",
        target_keys=(),
    )
    fanout_in_chunks(outbox.ref)
    target = DeliveryTarget.objects.get(outbox=outbox)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryTarget.objects.filter(pk=target.pk).update(
                lease_owner="invalid-worker",
                lease_until=timezone.now() + timedelta(minutes=1),
            )


@pytest.mark.django_db(transaction=True)
def test_delivery_lease_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0031_marketing_attempt_outcomes")]
    after = [("shop", "0032_marketing_delivery_leases")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor,
            DeliveryTarget._meta.db_table,
        )
    assert "shop_delivery_target_lease_state_ck" not in constraints

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor,
            DeliveryTarget._meta.db_table,
        )
    assert "shop_delivery_target_lease_state_ck" in constraints

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
