"""MKT-012 — durable outbox claim, lease, reconciliation and crash recovery."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.models import Announcement, AnnouncementStatus, MarketingOutbox
from shopman.shop.services import campaign
from shopman.shop.services.marketing_approval import PUBLISH_NOW, PUBLISH_SCHEDULED, approve_command
from shopman.shop.services.marketing_outbox import (
    MAX_ATTEMPTS,
    claim_due,
    process_due,
    publish_claim,
    reconcile,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return get_user_model().objects.create_user(
        username="outbox-operator",
        password="irrelevant",
    )


@pytest.fixture
def announcement():
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram", "facebook"],
    )


def _approve(actor, announcement, *, scheduled_at=None):
    return approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key=(
            "idem-outbox-approve-scheduled"
            if scheduled_at
            else "idem-outbox-approve-now-0001"
        ),
        base_version=1,
        publish_mode=PUBLISH_SCHEDULED if scheduled_at else PUBLISH_NOW,
        publish_at=scheduled_at,
        content={"body": "Fornada pronta"},
        platform_content={},
        platforms=["instagram", "facebook"],
    )


def test_claim_is_bounded_leased_and_not_visible_to_second_worker(actor, announcement):
    approved = _approve(actor, announcement)
    now = timezone.now()

    first = claim_due(worker_id="worker:first", now=now, limit=1, lease_seconds=60)
    second = claim_due(worker_id="worker:second", now=now, limit=2, lease_seconds=60)

    assert len(first) == len(second) == 1
    assert first[0].pk != second[0].pk
    assert first[0].attempts == second[0].attempts == 1
    assert first[0].lease_until == second[0].lease_until == now + timedelta(seconds=60)
    assert {first[0].pk, second[0].pk} == {row.pk for row in approved.outbox}


def test_stale_lease_is_observably_requeued_and_reclaimable(actor, announcement):
    _approve(actor, announcement)
    now = timezone.now()
    claimed = claim_due(worker_id="worker:crashed", now=now, limit=1)[0]

    report = reconcile(now=now + timedelta(seconds=61))
    reclaimed = claim_due(
        worker_id="worker:recovery",
        now=now + timedelta(seconds=61),
        limit=1,
    )[0]

    assert report.stale_requeued == 1
    assert reclaimed.pk == claimed.pk
    assert reclaimed.attempts == 2
    assert reclaimed.lease_owner == "worker:recovery"


def test_stale_lease_exhaustion_is_terminal_without_directive(actor, announcement):
    _approve(actor, announcement)
    now = timezone.now()
    row = MarketingOutbox.objects.order_by("pk").first()
    MarketingOutbox.objects.filter(pk=row.pk).update(
        state=MarketingOutbox.State.CLAIMED,
        attempts=MAX_ATTEMPTS,
        lease_owner="worker:gone",
        lease_until=now - timedelta(seconds=1),
    )

    report = reconcile(now=now)

    row.refresh_from_db()
    assert report.stale_failed == 1
    assert row.state == MarketingOutbox.State.FAILED
    assert row.last_error_code == "stale_lease_exhausted"
    assert Directive.objects.count() == 0


def test_publish_claim_hands_off_exact_graph_once_and_clears_lease(actor, announcement):
    approved = _approve(actor, announcement)
    now = timezone.now()
    row = claim_due(worker_id="worker:one", now=now, limit=1)[0]

    published = publish_claim(row.ref, worker_id="worker:one", now=now)
    replay = publish_claim(row.ref, worker_id="worker:one", now=now)

    directive = Directive.objects.get()
    announcement.refresh_from_db()
    assert published.pk == replay.pk == row.pk
    assert published.state == MarketingOutbox.State.DISPATCHED
    assert published.dispatch_ref == f"directive:{directive.pk}"
    assert published.lease_owner == ""
    assert published.lease_until is None
    assert directive.dedupe_key == f"marketing-outbox:{row.ref}"
    assert directive.payload == {
        "announcement_id": announcement.pk,
        "artifact_hash": approved.artifact.artifact_hash,
        "artifact_ref": str(approved.artifact.ref),
        "content_version": 2,
        "outbox_ref": str(row.ref),
        "platform": row.platform,
        "snapshot_ref": str(approved.snapshot.ref),
    }
    assert announcement.status == AnnouncementStatus.PUBLISHING


def test_failure_before_handoff_commit_requeues_without_queue_duplication(actor, announcement):
    _approve(actor, announcement)
    now = timezone.now()

    with patch(
        "shopman.shop.services.marketing_outbox.create_deduped",
        side_effect=RuntimeError("injected-before-commit"),
    ):
        report = process_due(worker_id="worker:retry", now=now, limit=1)

    row = MarketingOutbox.objects.order_by("pk").first()
    assert report.requeued == 1
    assert row.state == MarketingOutbox.State.PENDING
    assert row.last_error_code == "directive_handoff_failed"
    assert Directive.objects.count() == 0

    recovered = process_due(
        worker_id="worker:retry",
        now=row.available_at + timedelta(seconds=1),
        limit=1,
    )
    assert recovered.dispatched == 1
    assert Directive.objects.count() == 1


def test_non_dispatchable_announcement_fails_closed_before_queue(actor, announcement):
    _approve(actor, announcement)
    now = timezone.now()
    row = claim_due(worker_id="worker:guard", now=now, limit=1)[0]
    Announcement.objects.filter(pk=announcement.pk).update(
        status=AnnouncementStatus.CANCELLED
    )

    result = publish_claim(row.ref, worker_id="worker:guard", now=now)

    assert result.state == MarketingOutbox.State.FAILED
    assert result.last_error_code == "announcement_not_dispatchable"
    assert Directive.objects.count() == 0


def test_reconciler_links_preexisting_queue_instead_of_republishing(actor, announcement):
    approved = _approve(actor, announcement)
    row = MarketingOutbox.objects.order_by("pk").first()
    directive = Directive.objects.create(
        topic="announcement.publish",
        payload={
            "announcement_id": announcement.pk,
            "artifact_hash": approved.artifact.artifact_hash,
            "artifact_ref": str(approved.artifact.ref),
            "content_version": approved.artifact.version,
            "outbox_ref": str(row.ref),
            "platform": row.platform,
            "snapshot_ref": str(approved.snapshot.ref),
        },
        dedupe_key=f"marketing-outbox:{row.ref}",
    )

    report = reconcile()

    row.refresh_from_db()
    assert report.linked_existing == 1
    assert row.state == MarketingOutbox.State.DISPATCHED
    assert row.dispatch_ref == f"directive:{directive.pk}"
    assert Directive.objects.count() == 1


def test_reconciler_fails_closed_on_dedupe_identity_mismatch(actor, announcement):
    _approve(actor, announcement)
    row = MarketingOutbox.objects.order_by("pk").first()
    Directive.objects.create(
        topic="announcement.publish",
        payload={"outbox_ref": str(row.ref), "artifact_ref": "wrong"},
        dedupe_key=f"marketing-outbox:{row.ref}",
    )

    report = reconcile()

    row.refresh_from_db()
    assert report.directive_mismatch == 1
    assert row.state == MarketingOutbox.State.FAILED
    assert row.last_error_code == "directive_identity_mismatch"
    assert Directive.objects.get().status == Directive.Status.FAILED


def test_legacy_due_dispatcher_excludes_v2_scheduled_graph(actor, announcement):
    publish_at = timezone.now() + timedelta(hours=2)
    _approve(actor, announcement, scheduled_at=publish_at)

    assert campaign.dispatch_due(now=publish_at + timedelta(seconds=1)) == 0
    assert Directive.objects.count() == 0
    assert MarketingOutbox.objects.filter(state=MarketingOutbox.State.PENDING).count() == 2


@override_settings(SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED=False)
def test_management_command_is_safe_off_by_default(actor, announcement):
    _approve(actor, announcement)
    output = StringIO()

    call_command("process_marketing_outbox", stdout=output)

    assert "desativada" in output.getvalue()
    assert MarketingOutbox.objects.filter(state=MarketingOutbox.State.PENDING).count() == 2
    assert Directive.objects.count() == 0


@override_settings(SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED=True)
def test_management_command_processes_a_bounded_batch_when_enabled(actor, announcement):
    _approve(actor, announcement)

    call_command(
        "process_marketing_outbox",
        limit=1,
        worker_id="worker:command",
        stdout=StringIO(),
    )

    assert MarketingOutbox.objects.filter(
        state=MarketingOutbox.State.DISPATCHED
    ).count() == 1
    assert Directive.objects.count() == 1


@override_settings(
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED=False,
)
def test_force_cannot_bypass_safe_flag_in_production(actor, announcement):
    _approve(actor, announcement)

    with pytest.raises(CommandError, match="ambiente local"):
        call_command("process_marketing_outbox", force=True, stdout=StringIO())

    assert MarketingOutbox.objects.filter(state=MarketingOutbox.State.PENDING).count() == 2
    assert Directive.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_crash_after_handoff_commit_converges_without_second_directive():
    actor = get_user_model().objects.create_user(username="outbox-crash")
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram"],
    )
    _approve(actor, announcement)
    now = timezone.now()
    row = claim_due(worker_id="worker:crash", now=now, limit=1)[0]

    with patch(
        "shopman.shop.services.marketing_outbox._after_publish_commit",
        side_effect=RuntimeError("injected-after-commit"),
    ):
        with pytest.raises(RuntimeError, match="injected-after-commit"):
            publish_claim(row.ref, worker_id="worker:crash", now=now)

    row.refresh_from_db()
    assert row.state == MarketingOutbox.State.DISPATCHED
    assert Directive.objects.filter(dedupe_key=f"marketing-outbox:{row.ref}").count() == 1

    replay = publish_claim(row.ref, worker_id="worker:other", now=now)
    assert replay.state == MarketingOutbox.State.DISPATCHED
    assert Directive.objects.filter(dedupe_key=f"marketing-outbox:{row.ref}").count() == 1


@pytest.mark.django_db(transaction=True)
def test_outbox_schema_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0028_marketing_transactional_transitions")]
    after = [("shop", "0029_marketing_outbox_recovery")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                "shop_marketingoutbox",
            )
        }
    assert "dispatch_ref" not in columns
    assert "dispatched_at" not in columns

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                "shop_marketingoutbox",
            )
        }
    assert {"dispatch_ref", "dispatched_at"} <= columns

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
