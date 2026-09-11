"""MKT-011 — reject/cancel/reschedule/expire are transactional and audited."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingOutbox,
)
from shopman.shop.services.marketing_approval import (
    PUBLISH_NOW,
    PUBLISH_SCHEDULED,
    approve_command,
)
from shopman.shop.services.marketing_commands import (
    MarketingCommandConflict,
    MarketingCommandRejected,
)
from shopman.shop.services.marketing_transitions import (
    SYSTEM_EXPIRY_ACTOR,
    cancel_command,
    expire_due,
    reject_command,
    reschedule_command,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return get_user_model().objects.create_user(
        username="transition-operator",
        password="irrelevant",
    )


@pytest.fixture
def announcement():
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram", "google_business"],
    )


def _approve(actor, announcement, *, scheduled=False):
    publish_at = timezone.now() + timedelta(hours=2) if scheduled else None
    return approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key=(
            "idem-transition-approve-scheduled"
            if scheduled
            else "idem-transition-approve-now"
        ),
        base_version=1,
        publish_mode=PUBLISH_SCHEDULED if scheduled else PUBLISH_NOW,
        publish_at=publish_at,
        content={"body": "Fornada pronta"},
        platform_content={},
        platforms=["instagram", "google_business"],
    )


def test_reject_pending_is_versioned_audited_and_replayable(actor, announcement):
    first = reject_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-reject-0001",
        base_version=1,
        reason="Foto não representa a fornada",
    )
    replay = reject_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-reject-0001",
        base_version=1,
        reason="Foto não representa a fornada",
    )

    announcement.refresh_from_db()
    audit = MarketingAuditEvent.objects.get(command=first.receipt)
    assert announcement.status == AnnouncementStatus.REJECTED
    assert announcement.version == 2
    assert announcement.rejected_by_id == actor.pk
    assert announcement.rejected_reason == "Foto não representa a fornada"
    assert (audit.base_version, audit.resulting_version) == (1, 2)
    assert audit.reason_code == "operator_rejected"
    assert audit.decision_reason == "Foto não representa a fornada"
    assert audit.facts == {"outbox_cancelled": 0, "reason_present": True}
    assert replay.replayed is True
    assert replay.receipt.pk == first.receipt.pk


def test_reject_scheduled_cancels_every_not_started_lane_with_tombstone(actor, announcement):
    approved = _approve(actor, announcement, scheduled=True)

    rejected = reject_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-reject-0002",
        base_version=2,
        reason="Oferta cancelada",
    )

    announcement.refresh_from_db()
    rows = list(MarketingOutbox.objects.order_by("pk"))
    assert announcement.status == AnnouncementStatus.REJECTED
    assert announcement.version == 3
    assert all(row.state == MarketingOutbox.State.CANCELLED for row in rows)
    assert all(row.cancelled_by_command_id == rejected.receipt.pk for row in rows)
    assert all(row.cancelled_at is not None for row in rows)
    assert approved.receipt.pk != rejected.receipt.pk
    assert rejected.receipt.outcome["outbox_cancelled"] == 2


def test_cancel_now_wins_all_pending_lanes_and_is_idempotent(actor, announcement):
    _approve(actor, announcement)

    first = cancel_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-cancel-0001",
        base_version=2,
        reason="Campanha suspensa pelo operador",
    )
    replay = cancel_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-cancel-0001",
        base_version=2,
        reason="Campanha suspensa pelo operador",
    )

    announcement.refresh_from_db()
    audit = MarketingAuditEvent.objects.get(command=first.receipt)
    assert announcement.status == AnnouncementStatus.CANCELLED
    assert announcement.version == 3
    assert audit.decision_reason == "Campanha suspensa pelo operador"
    assert audit.facts["avoided_lane_count"] == 2
    assert audit.facts["irreversible_target_count"] == 0
    assert first.receipt.outcome == {
        "avoided_lane_count": 2,
        "irreversible_target_count": 0,
        "outbox_cancelled": 2,
        "status": AnnouncementStatus.CANCELLED,
    }
    assert replay.replayed is True
    assert {row.pk for row in replay.affected_outbox} == {
        row.pk for row in first.affected_outbox
    }


@pytest.mark.parametrize("started_state", [MarketingOutbox.State.CLAIMED, MarketingOutbox.State.DISPATCHED])
def test_cancel_never_claims_success_after_any_lane_started(
    actor, announcement, started_state
):
    _approve(actor, announcement)
    first = MarketingOutbox.objects.order_by("pk").first()
    started_fields = {"state": started_state}
    if started_state == MarketingOutbox.State.CLAIMED:
        started_fields.update(
            lease_owner="worker:test",
            lease_until=timezone.now() + timedelta(minutes=1),
        )
    else:
        started_fields.update(
            dispatch_ref=f"directive:test:{first.pk}",
            dispatched_at=timezone.now(),
        )
    MarketingOutbox.objects.filter(pk=first.pk).update(**started_fields)

    with pytest.raises(MarketingCommandRejected) as caught:
        cancel_command(
            announcement.pk,
            actor=actor,
            idempotency_key=f"idem-transition-cancel-{started_state}",
            base_version=2,
            reason="Campanha suspensa pelo operador",
        )

    announcement.refresh_from_db()
    assert caught.value.code == "dispatch_already_started"
    assert announcement.status == AnnouncementStatus.PUBLISHING
    assert announcement.version == 2
    assert MarketingOutbox.objects.filter(state=MarketingOutbox.State.CANCELLED).count() == 0
    assert MarketingCommandReceipt.objects.get(ref=caught.value.receipt_ref).state == "rejected"


def test_reschedule_preserves_relative_wave_delays_and_audits_both_instants(actor, announcement):
    approved = _approve(actor, announcement, scheduled=True)
    rows = list(MarketingOutbox.objects.order_by("pk"))
    old_publish_at = approved.announcement.publish_at
    MarketingOutbox.objects.filter(pk=rows[1].pk).update(
        available_at=rows[1].available_at + timedelta(minutes=15)
    )
    new_publish_at = old_publish_at + timedelta(hours=3)

    result = reschedule_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-reschedule-0001",
        base_version=2,
        publish_at=new_publish_at,
    )

    announcement.refresh_from_db()
    shifted = list(MarketingOutbox.objects.order_by("pk"))
    audit = MarketingAuditEvent.objects.get(command=result.receipt)
    assert announcement.publish_at == new_publish_at
    assert announcement.version == 3
    assert shifted[0].available_at == new_publish_at
    assert shifted[1].available_at == new_publish_at + timedelta(minutes=15)
    assert audit.facts == {
        "from": old_publish_at.isoformat(),
        "outbox_rescheduled": 2,
        "to": new_publish_at.isoformat(),
        "timezone": "America/Sao_Paulo",
    }


def test_reschedule_refuses_any_wave_at_or_after_expiry(actor, announcement):
    approved = _approve(actor, announcement, scheduled=True)
    old_publish_at = approved.announcement.publish_at
    expires_at = old_publish_at + timedelta(hours=4)
    Announcement.objects.filter(pk=announcement.pk).update(expires_at=expires_at)
    original_times = list(
        MarketingOutbox.objects.order_by("pk").values_list("available_at", flat=True)
    )

    with pytest.raises(MarketingCommandRejected) as caught:
        reschedule_command(
            announcement.pk,
            actor=actor,
            idempotency_key="idem-transition-expiry-0001",
            base_version=2,
            publish_at=timezone.localtime(expires_at),
            publish_timezone="America/Sao_Paulo",
        )

    assert caught.value.code == "delivery_wave_after_expiry"
    assert list(
        MarketingOutbox.objects.order_by("pk").values_list("available_at", flat=True)
    ) == original_times


def test_reschedule_refuses_a_whatsapp_wave_in_quiet_hours(actor, announcement):
    _approve(actor, announcement, scheduled=True)
    first = MarketingOutbox.objects.order_by("pk").first()
    MarketingOutbox.objects.filter(pk=first.pk).update(platform="whatsapp")
    original_times = list(
        MarketingOutbox.objects.order_by("pk").values_list("available_at", flat=True)
    )
    next_evening = (
        timezone.localtime(timezone.now())
        .replace(hour=21, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )

    with pytest.raises(MarketingCommandRejected) as caught:
        reschedule_command(
            announcement.pk,
            actor=actor,
            idempotency_key="idem-transition-quiet-00001",
            base_version=2,
            publish_at=next_evening,
            publish_timezone="America/Sao_Paulo",
        )

    assert caught.value.code == "delivery_wave_in_quiet_hours"
    assert list(
        MarketingOutbox.objects.order_by("pk").values_list("available_at", flat=True)
    ) == original_times


def test_cancel_then_reschedule_with_same_base_has_exactly_one_winner(actor, announcement):
    _approve(actor, announcement, scheduled=True)
    cancel_command(
        announcement.pk,
        actor=actor,
        idempotency_key="idem-transition-race-cancel",
        base_version=2,
        reason="Campanha suspensa pelo operador",
    )

    with pytest.raises(MarketingCommandConflict) as caught:
        reschedule_command(
            announcement.pk,
            actor=actor,
            idempotency_key="idem-transition-race-reschedule",
            base_version=2,
            publish_at=timezone.now() + timedelta(hours=8),
        )

    assert caught.value.code == "version_conflict"
    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.CANCELLED
    assert announcement.version == 3


def test_expiry_has_explicit_system_actor_version_receipt_and_audit(announcement):
    due = timezone.now()
    Announcement.objects.filter(pk=announcement.pk).update(expires_at=due - timedelta(seconds=1))

    assert expire_due(now=due) == 1
    assert expire_due(now=due) == 0

    announcement.refresh_from_db()
    receipt = MarketingCommandReceipt.objects.get(kind=MarketingCommandReceipt.Kind.EXPIRE)
    audit = MarketingAuditEvent.objects.get(command=receipt)
    assert announcement.status == AnnouncementStatus.EXPIRED
    assert announcement.version == 2
    assert receipt.actor_id is None
    assert receipt.actor_ref == SYSTEM_EXPIRY_ACTOR
    assert receipt.state == MarketingCommandReceipt.State.COMPLETED
    assert (receipt.base_version, receipt.resulting_version) == (1, 2)
    assert audit.actor_id is None
    assert audit.actor_ref == SYSTEM_EXPIRY_ACTOR
    assert audit.reason_code == "review_deadline_elapsed"


def test_expiry_crash_rolls_back_status_receipt_and_audit(announcement):
    due = timezone.now()
    Announcement.objects.filter(pk=announcement.pk).update(expires_at=due - timedelta(seconds=1))

    with patch.object(
        MarketingAuditEvent.objects,
        "create",
        side_effect=RuntimeError("injected-expiry-crash"),
    ):
        with pytest.raises(RuntimeError, match="injected-expiry-crash"):
            expire_due(now=due)

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1
    assert MarketingCommandReceipt.objects.count() == 0
    assert MarketingAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_transition_schema_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0027_marketing_approval_outbox")]
    after = [("shop", "0028_marketing_transactional_transitions")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    with connection.cursor() as cursor:
        before_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                "shop_marketingoutbox",
            )
        }
    assert "cancelled_at" not in before_columns
    assert "cancelled_by_command_id" not in before_columns

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    with connection.cursor() as cursor:
        after_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                "shop_marketingoutbox",
            )
        }
    assert {"cancelled_at", "cancelled_by_command_id"} <= after_columns

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
