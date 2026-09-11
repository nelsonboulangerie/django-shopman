"""MKT-009 — receipts, monotonic versions, CAS and idempotent replay."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.backstage.projections.marketing import build_announcement
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    MarketingCommandReceipt,
)
from shopman.shop.services.marketing_commands import (
    MarketingCommandConflict,
    MarketingCommandRejected,
    RejectCommand,
    execute_announcement_command,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return get_user_model().objects.create_user(
        username="marketing-command-operator",
        password="irrelevant",
    )


@pytest.fixture
def announcement():
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta"},
        platforms=["instagram"],
    )


def _complete(*, actor, announcement, key, base_version=1, payload=None, calls=None):
    def operation(locked, _receipt):
        if calls is not None:
            calls.append(locked.pk)
        locked.status = AnnouncementStatus.APPROVED
        locked.save(update_fields=["status"])
        return {"status": "approved", "artifact_ref": "artifact:test:001"}

    return execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.APPROVE,
        announcement_id=announcement.pk,
        actor=actor,
        idempotency_key=key,
        base_version=base_version,
        payload=payload or {"publish_mode": "scheduled"},
        operation=operation,
        request_id="req_test_001",
    )


def test_command_completes_with_monotonic_version_and_safe_receipt(actor, announcement):
    raw_key = "idem-command-00000001"

    executed = _complete(actor=actor, announcement=announcement, key=raw_key)

    announcement.refresh_from_db()
    receipt = executed.receipt
    assert executed.replayed is False
    assert announcement.version == 2
    assert receipt.state == MarketingCommandReceipt.State.COMPLETED
    assert receipt.base_version == 1
    assert receipt.resulting_version == 2
    assert receipt.resource_ref == f"announcement:{announcement.pk}"
    assert receipt.outcome == {
        "status": "approved",
        "artifact_ref": "artifact:test:001",
    }
    assert receipt.idempotency_key_hash != raw_key
    assert raw_key not in str(receipt.__dict__)
    assert receipt.retention_until >= receipt.created_at + timedelta(days=1824)
    assert build_announcement(announcement).version == 2


def test_same_key_and_payload_returns_exact_receipt_without_second_mutation(actor, announcement):
    calls: list[int] = []
    key = "idem-command-00000002"

    first = _complete(
        actor=actor,
        announcement=announcement,
        key=key,
        calls=calls,
    )
    second = _complete(
        actor=actor,
        announcement=announcement,
        key=key,
        calls=calls,
    )

    assert second.replayed is True
    assert second.receipt.pk == first.receipt.pk
    assert second.receipt.outcome == first.receipt.outcome
    assert calls == [announcement.pk]
    assert MarketingCommandReceipt.objects.count() == 1


def test_same_key_with_different_payload_is_409_semantics_and_keeps_first_outcome(actor, announcement):
    key = "idem-command-00000003"
    first = _complete(actor=actor, announcement=announcement, key=key)

    with pytest.raises(MarketingCommandConflict) as caught:
        _complete(
            actor=actor,
            announcement=announcement,
            key=key,
            payload={"publish_mode": "now"},
        )

    assert caught.value.code == "idempotency_conflict"
    assert caught.value.receipt_ref == str(first.receipt.ref)
    assert MarketingCommandReceipt.objects.count() == 1
    assert MarketingCommandReceipt.objects.get().outcome == first.receipt.outcome


def test_distinct_key_with_stale_base_version_records_and_replays_same_conflict(actor, announcement):
    _complete(
        actor=actor,
        announcement=announcement,
        key="idem-command-00000004",
    )
    stale_key = "idem-command-00000005"

    with pytest.raises(MarketingCommandConflict) as first:
        _complete(
            actor=actor,
            announcement=announcement,
            key=stale_key,
            base_version=1,
        )
    with pytest.raises(MarketingCommandConflict) as replay:
        _complete(
            actor=actor,
            announcement=announcement,
            key=stale_key,
            base_version=1,
        )

    assert first.value.code == replay.value.code == "version_conflict"
    assert first.value.receipt_ref == replay.value.receipt_ref
    assert first.value.current_version == replay.value.current_version == 2
    conflict = MarketingCommandReceipt.objects.get(ref=first.value.receipt_ref)
    assert conflict.state == MarketingCommandReceipt.State.CONFLICT
    assert conflict.outcome == {"code": "version_conflict"}


def test_domain_rejection_rolls_back_callback_but_keeps_rejected_receipt(actor, announcement):
    def operation(locked, _receipt):
        locked.status = AnnouncementStatus.APPROVED
        locked.save(update_fields=["status"])
        raise RejectCommand(
            code="announcement_expired",
            detail="Este anúncio expirou.",
            outcome={"status": "expired"},
        )

    with pytest.raises(MarketingCommandRejected) as caught:
        execute_announcement_command(
            kind=MarketingCommandReceipt.Kind.APPROVE,
            announcement_id=announcement.pk,
            actor=actor,
            idempotency_key="idem-command-00000006",
            base_version=1,
            payload={"publish_mode": "scheduled"},
            operation=operation,
        )

    announcement.refresh_from_db()
    receipt = MarketingCommandReceipt.objects.get(ref=caught.value.receipt_ref)
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1
    assert receipt.state == MarketingCommandReceipt.State.REJECTED
    assert receipt.outcome == {
        "code": "announcement_expired",
        "status": "expired",
    }


def test_unexpected_failure_rolls_back_mutation_and_receipt(actor, announcement):
    def operation(locked, _receipt):
        locked.status = AnnouncementStatus.APPROVED
        locked.save(update_fields=["status"])
        raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        execute_announcement_command(
            kind=MarketingCommandReceipt.Kind.APPROVE,
            announcement_id=announcement.pk,
            actor=actor,
            idempotency_key="idem-command-00000007",
            base_version=1,
            payload={"publish_mode": "scheduled"},
            operation=operation,
        )

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1
    assert MarketingCommandReceipt.objects.count() == 0


@pytest.mark.parametrize(
    "outcome",
    [
        {"phone": "+5511999999999"},
        {"nested": {"recipient": "customer"}},
        {"body": "raw campaign copy"},
    ],
)
def test_receipt_rejects_pii_or_content_outcomes_and_rolls_back(actor, announcement, outcome):
    with pytest.raises(ValueError, match="sensível"):
        execute_announcement_command(
            kind=MarketingCommandReceipt.Kind.APPROVE,
            announcement_id=announcement.pk,
            actor=actor,
            idempotency_key=f"idem-command-pii-{next(iter(outcome))}-0001",
            base_version=1,
            payload={"publish_mode": "scheduled"},
            operation=lambda _locked, _receipt: outcome,
        )

    announcement.refresh_from_db()
    assert announcement.version == 1
    assert MarketingCommandReceipt.objects.count() == 0


def test_missing_resource_gets_a_replayable_rejected_receipt(actor):
    kwargs = {
        "kind": MarketingCommandReceipt.Kind.CANCEL,
        "announcement_id": 999_999,
        "actor": actor,
        "idempotency_key": "idem-command-00000008",
        "base_version": 1,
        "payload": {},
        "operation": lambda _locked, _receipt: {},
    }

    with pytest.raises(MarketingCommandRejected) as first:
        execute_announcement_command(**kwargs)
    with pytest.raises(MarketingCommandRejected) as replay:
        execute_announcement_command(**kwargs)

    assert first.value.code == replay.value.code == "announcement_not_found"
    assert first.value.receipt_ref == replay.value.receipt_ref
    assert MarketingCommandReceipt.objects.get().announcement_id is None


def test_inactive_actor_is_denied_before_receipt(actor, announcement):
    actor.is_active = False
    actor.save(update_fields=["is_active"])

    with pytest.raises(MarketingCommandRejected) as caught:
        _complete(
            actor=actor,
            announcement=announcement,
            key="idem-command-00000009",
        )

    assert caught.value.code == "invalid_actor"
    assert MarketingCommandReceipt.objects.count() == 0


def test_draft_edit_increments_version_and_can_refuse_a_stale_save(announcement):
    from shopman.shop.services.campaign import CampaignVersionConflict, update_content

    edited = update_content(announcement.pk, body="Primeira revisão", base_version=1)
    assert edited.version == 2

    with pytest.raises(CampaignVersionConflict) as caught:
        update_content(announcement.pk, body="Sobrescrita stale", base_version=1)

    announcement.refresh_from_db()
    assert caught.value.current_version == 2
    assert announcement.content["body"] == "Primeira revisão"
    assert announcement.version == 2


def test_receipt_timestamps_are_not_client_controlled(actor, announcement):
    before = timezone.now()
    result = _complete(
        actor=actor,
        announcement=announcement,
        key="idem-command-00000010",
    )
    after = timezone.now()

    assert before <= result.receipt.created_at <= after
    assert before <= result.receipt.completed_at <= after
