"""MKT-016 — mathematically closed, ledger-derived delivery truth."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from shopman.guestman import ConsentService

from shopman.shop.models import (
    Announcement,
    AnnouncementDeliveryState,
    AnnouncementStatus,
    DeliveryTarget,
    MarketingOutbox,
)
from shopman.shop.services.marketing_delivery_aggregate import (
    delivery_summary,
    refresh_announcement_delivery,
)
from shopman.shop.services.marketing_delivery_attempts import queue_target
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
)
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = pytest.mark.django_db


def _fanout_with_states(*, suffix: str, states: tuple[str, ...]):
    outbox, members = _graph(
        platform="whatsapp",
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
                DeliveryTarget.State.PLANNED,
                DeliveryTarget.State.QUEUED,
                DeliveryTarget.State.SENDING,
                DeliveryTarget.State.FAILED_RETRYABLE,
            }
            else now
        )
    DeliveryTarget.objects.bulk_update(targets, ["state", "settled_at"])
    return outbox, targets


def test_incomplete_fanout_is_pending_and_cannot_look_successful():
    outbox, members = _graph(
        platform="whatsapp",
        suffix="aggregate-fanout",
        target_keys=("one", "two", "three"),
    )
    fanout_in_chunks(
        outbox.ref,
        member_ids=[member.pk for member in members],
        chunk_size=1,
        max_chunks=1,
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)
    outbox.announcement.refresh_from_db()

    assert summary.state == AnnouncementDeliveryState.FANOUT_PENDING
    assert summary.targets_total == 1
    assert summary.fanout_expected == 3
    assert summary.fanout_materialized == 1
    assert summary.counts_close is True
    assert outbox.announcement.status == AnnouncementStatus.PUBLISHING
    assert outbox.announcement.delivery_settled_at is None


def test_all_accepted_is_succeeded_but_explicitly_unconfirmed():
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-accepted",
        states=(DeliveryTarget.State.ACCEPTED,) * 3,
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)
    outbox.announcement.refresh_from_db()
    platform = summary.platforms[0]

    assert summary.state == AnnouncementDeliveryState.SUCCEEDED
    assert platform.accepted_unconfirmed == 3
    assert platform.confirmed == 0
    assert summary.counts_close is True
    assert outbox.announcement.status == AnnouncementStatus.SETTLED
    assert outbox.announcement.status != AnnouncementStatus.PUBLISHED
    assert outbox.announcement.delivery_settled_at is not None


def test_partial_success_and_final_failure_stays_completed_with_failures():
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-partial",
        states=(
            DeliveryTarget.State.ACCEPTED,
            DeliveryTarget.State.CONFIRMED,
            DeliveryTarget.State.FAILED_FINAL,
        ),
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)
    outbox.announcement.refresh_from_db()

    assert summary.state == AnnouncementDeliveryState.COMPLETED_WITH_FAILURES
    assert summary.counts[DeliveryTarget.State.ACCEPTED] == 1
    assert summary.counts[DeliveryTarget.State.CONFIRMED] == 1
    assert summary.counts[DeliveryTarget.State.FAILED_FINAL] == 1
    assert summary.counts_close is True
    assert outbox.announcement.status == AnnouncementStatus.SETTLED
    assert outbox.announcement.status != AnnouncementStatus.PUBLISHED


def test_unknown_has_priority_and_legacy_json_cannot_overrule_it():
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-unknown",
        states=(
            DeliveryTarget.State.ACCEPTED,
            DeliveryTarget.State.UNKNOWN,
            DeliveryTarget.State.QUEUED,
        ),
    )
    original_legacy = {"whatsapp": {"status": "sent", "sent": 3, "failed": 0}}
    Announcement.objects.filter(pk=outbox.announcement_id).update(
        platform_results=original_legacy
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)
    announcement = Announcement.objects.get(pk=outbox.announcement_id)

    assert summary.state == AnnouncementDeliveryState.UNKNOWN
    assert summary.counts[DeliveryTarget.State.UNKNOWN] == 1
    assert announcement.status == AnnouncementStatus.SETTLED
    assert announcement.status != AnnouncementStatus.PUBLISHED
    assert announcement.platform_results == original_legacy


def test_retryable_target_keeps_delivery_open():
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-retryable",
        states=(
            DeliveryTarget.State.ACCEPTED,
            DeliveryTarget.State.FAILED_RETRYABLE,
        ),
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)
    outbox.announcement.refresh_from_db()

    assert summary.state == AnnouncementDeliveryState.DELIVERING
    assert outbox.announcement.status == AnnouncementStatus.PUBLISHING
    assert outbox.announcement.delivery_settled_at is None


def test_general_state_combines_platforms_without_hiding_partial():
    outbox, _members = _graph(
        platform="instagram",
        approved_platforms=("instagram", "google_business"),
        suffix="aggregate-platforms",
        target_keys=(),
    )
    google_outbox = MarketingOutbox.objects.create(
        command=outbox.command,
        announcement=outbox.announcement,
        snapshot=outbox.snapshot,
        artifact=outbox.artifact,
        platform="google_business",
        state=MarketingOutbox.State.DISPATCHED,
        available_at=outbox.available_at,
        dispatch_ref="directive:aggregate:google",
        dispatched_at=outbox.dispatched_at,
    )
    fanout_in_chunks(outbox.ref)
    fanout_in_chunks(google_outbox.ref)
    DeliveryTarget.objects.filter(outbox=outbox).update(
        state=DeliveryTarget.State.ACCEPTED,
        settled_at=timezone.now(),
    )
    DeliveryTarget.objects.filter(outbox=google_outbox).update(
        state=DeliveryTarget.State.FAILED_FINAL,
        settled_at=timezone.now(),
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)

    assert summary.state == AnnouncementDeliveryState.COMPLETED_WITH_FAILURES
    assert {item.platform: item.state for item in summary.platforms} == {
        "google_business": AnnouncementDeliveryState.COMPLETED_WITH_FAILURES,
        "instagram": AnnouncementDeliveryState.SUCCEEDED,
    }
    assert summary.targets_total == 2
    assert summary.counts_close is True


@pytest.mark.parametrize(
    ("target_state", "aggregate_state"),
    [
        (DeliveryTarget.State.CANCELLED, AnnouncementDeliveryState.CANCELLED),
        (DeliveryTarget.State.EXPIRED, AnnouncementDeliveryState.EXPIRED),
    ],
)
def test_uniform_cancelled_or_expired_targets_have_distinct_state(
    target_state,
    aggregate_state,
):
    outbox, _targets = _fanout_with_states(
        suffix=f"aggregate-{target_state}",
        states=(target_state, target_state),
    )

    summary = refresh_announcement_delivery(outbox.announcement_id)

    assert summary.state == aggregate_state
    assert summary.state != AnnouncementDeliveryState.SUCCEEDED


def test_historical_published_json_without_ledger_is_untracked_not_success():
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PUBLISHED,
        content={"body": "legado"},
        platforms=["instagram"],
        platform_results={"instagram": {"status": "pending_manual"}},
        published_at=timezone.now(),
    )

    summary = refresh_announcement_delivery(announcement.pk)
    replay = refresh_announcement_delivery(announcement.pk)
    announcement.refresh_from_db()

    assert summary.state == AnnouncementDeliveryState.LEGACY_UNTRACKED
    assert replay.state == AnnouncementDeliveryState.LEGACY_UNTRACKED
    assert summary.platforms[0].state == AnnouncementDeliveryState.LEGACY_UNTRACKED
    assert announcement.delivery_state == AnnouncementDeliveryState.LEGACY_UNTRACKED
    assert announcement.status == AnnouncementStatus.SETTLED
    assert announcement.status != AnnouncementStatus.PUBLISHED


def test_target_mutation_schedules_aggregate_refresh_after_commit(
    django_capture_on_commit_callbacks,
):
    outbox, members = _graph(
        platform="whatsapp",
        suffix="aggregate-on-commit",
        target_keys=("one",),
    )
    customer = members[0].customer
    ConsentService.grant_consent(
        customer.ref,
        "whatsapp",
        source="aggregate-test",
    )
    fanout_in_chunks(outbox.ref, member_ids=[members[0].pk])
    target = DeliveryTarget.objects.get(outbox=outbox)
    queue_target(target.ref)
    ConsentService.revoke_consent(customer.ref, "whatsapp")

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        claim_due_targets(worker_id="aggregate-on-commit-worker")

    outbox.announcement.refresh_from_db()
    assert len(callbacks) == 1
    assert outbox.announcement.delivery_state == (
        AnnouncementDeliveryState.COMPLETED_WITH_FAILURES
    )
    assert outbox.announcement.status == AnnouncementStatus.SETTLED


def test_aggregate_of_100_targets_uses_three_queries(django_assert_num_queries):
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-query-budget",
        states=(DeliveryTarget.State.CONFIRMED,) * 100,
    )

    with django_assert_num_queries(3):
        summary = delivery_summary(outbox.announcement_id)

    assert summary.targets_total == 100
    assert summary.counts_close is True
    assert summary.counts[DeliveryTarget.State.CONFIRMED] == 100


def test_database_rejects_impossible_aggregate_and_unknown_target_state():
    outbox, _targets = _fanout_with_states(
        suffix="aggregate-constraints",
        states=(DeliveryTarget.State.PLANNED,),
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Announcement.objects.filter(pk=outbox.announcement_id).update(
                delivery_state=AnnouncementDeliveryState.UNKNOWN,
                delivery_settled_at=None,
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryTarget.objects.filter(outbox=outbox).update(state="invented")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MarketingOutbox.objects.filter(pk=outbox.pk).update(state="invented")


@pytest.mark.django_db(transaction=True)
def test_aggregate_migration_marks_legacy_and_reapplies_cleanly():
    published_at = timezone.now() - timedelta(days=1)
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PUBLISHED,
        content={"body": "histórico"},
        platforms=["instagram"],
        platform_results={"instagram": {"status": "published"}},
        published_at=published_at,
    )
    before = [("shop", "0032_marketing_delivery_leases")]
    after = [("shop", "0033_marketing_delivery_aggregate")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    apps = executor.loader.project_state(after).apps
    MigratedAnnouncement = apps.get_model("shop", "Announcement")
    migrated = MigratedAnnouncement.objects.get(pk=announcement.pk)
    assert migrated.delivery_state == "legacy_untracked"
    assert migrated.delivery_settled_at == published_at

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
