"""MKT-013 — protected DeliveryTarget/Attempt schema and uniqueness."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AudienceSnapshot,
    AudienceSnapshotMember,
    DeliveryAttempt,
    DeliveryTarget,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    MarketingOutbox,
)
from shopman.shop.services.marketing_approval import canonical_artifact_bytes
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_delivery_ledger import (
    MAX_TARGETS_PER_COMMAND,
    ensure_targets,
)

pytestmark = pytest.mark.django_db


def _graph(
    *,
    platform="whatsapp",
    suffix="one",
    target_keys=("member-a", "member-b"),
    approved_platforms=None,
):
    now = timezone.now()
    platforms = list(approved_platforms or (platform,))
    actor = get_user_model().objects.create_user(username=f"ledger-{suffix}")
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PUBLISHING,
        content={"body": "Fornada pronta"},
        platforms=platforms,
        version=2,
    )
    command = MarketingCommandReceipt.objects.create(
        kind=MarketingCommandReceipt.Kind.APPROVE,
        state=MarketingCommandReceipt.State.COMPLETED,
        announcement=announcement,
        resource_ref=f"announcement:{announcement.pk}",
        actor=actor,
        actor_ref=f"user:{actor.pk}",
        idempotency_key_hash=hashlib.sha256(f"idem-{suffix}".encode()).hexdigest(),
        payload_hash=hashlib.sha256(f"payload-{suffix}".encode()).hexdigest(),
        base_version=1,
        resulting_version=2,
        outcome={"publish_mode": "now"},
        completed_at=now,
        retention_until=now + timedelta(days=365 * 5),
    )
    artifact_payload = {
        "content": {"body": "Fornada pronta"},
        "content_version": 2,
        "platform_content": {},
        "platforms": platforms,
        "schema_version": 1,
    }
    artifact = MarketingContentArtifact.objects.create(
        announcement=announcement,
        version=2,
        payload=artifact_payload,
        artifact_hash=hashlib.sha256(
            canonical_artifact_bytes(artifact_payload)
        ).hexdigest(),
        retention_until=now + timedelta(days=365 * 5),
    )
    snapshot = AudienceSnapshot.objects.create(
        announcement=announcement,
        version=2,
        summary={"total": len(target_keys)},
        rule_summary={},
        rule_hash="1" * 64,
        cohort_hash="2" * 64,
        policy_version="marketing-audience.v1",
        calculated_at=now,
        expires_at=now + timedelta(minutes=5),
        retention_until=now + timedelta(days=90),
    )
    members = []
    for index, target_key in enumerate(target_keys):
        customer = Customer.objects.create(
            ref=f"LEDGER-{suffix}-{index}",
            first_name="Pessoa",
            phone=f"+55439{announcement.pk:06d}{index:02d}",
        )
        members.append(AudienceSnapshotMember.objects.create(
            snapshot=snapshot,
            customer=customer,
            target_key=hashlib.sha256(target_key.encode()).hexdigest(),
            reasons=["consent"],
        ))
    outbox = MarketingOutbox.objects.create(
        command=command,
        announcement=announcement,
        snapshot=snapshot,
        artifact=artifact,
        platform=platform,
        wave_key="all" if platform == "whatsapp" else "",
        state=MarketingOutbox.State.DISPATCHED,
        available_at=now,
        dispatch_ref=f"directive:ledger:{suffix}",
        dispatched_at=now,
    )
    return outbox, tuple(members)


def test_two_workers_materialize_the_same_targets_once():
    outbox, members = _graph()
    member_ids = [member.pk for member in members]

    first = ensure_targets(outbox.ref, member_ids=member_ids)
    second = ensure_targets(outbox.ref, member_ids=reversed(member_ids))

    assert [target.pk for target in first] == [target.pk for target in second]
    assert DeliveryTarget.objects.count() == 2
    assert all(target.outbox_id == outbox.pk for target in first)
    assert len({target.target_fingerprint for target in first}) == 2


def test_database_unique_prevents_duplicate_logical_target():
    outbox, members = _graph()
    target = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryTarget.objects.create(
                outbox=outbox,
                announcement=outbox.announcement,
                snapshot=outbox.snapshot,
                artifact=outbox.artifact,
                member=members[0],
                platform=outbox.platform,
                wave_key=outbox.wave_key,
                target_fingerprint=target.target_fingerprint,
                fingerprint_key_version=target.fingerprint_key_version,
                next_attempt_at=outbox.available_at,
                identity_retention_until=target.identity_retention_until,
                record_retention_until=target.record_retention_until,
            )


def test_target_fingerprint_is_scoped_and_key_versioned():
    first_outbox, first_members = _graph(suffix="scope-a", target_keys=("same",))
    second_outbox, second_members = _graph(suffix="scope-b", target_keys=("same",))

    first = ensure_targets(first_outbox.ref, member_ids=[first_members[0].pk])[0]
    with override_settings(
        SHOPMAN_MARKETING_TARGET_HMAC_KEY="rotated-test-only-key",
        SHOPMAN_MARKETING_TARGET_HMAC_KEY_VERSION=2,
    ):
        second = ensure_targets(second_outbox.ref, member_ids=[second_members[0].pk])[0]

    assert first.target_fingerprint != second.target_fingerprint
    assert (first.fingerprint_key_version, second.fingerprint_key_version) == (1, 2)
    assert len(first.target_fingerprint) == len(second.target_fingerprint) == 64


@override_settings(
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_MARKETING_TARGET_HMAC_KEY="",
)
def test_missing_protected_key_fails_closed():
    outbox, members = _graph(suffix="missing-key", target_keys=("one",))

    with pytest.raises(MarketingContractError) as caught:
        ensure_targets(outbox.ref, member_ids=[members[0].pk])

    assert caught.value.code == "target_hmac_key_unavailable"
    assert DeliveryTarget.objects.count() == 0


def test_public_platform_has_one_non_recipient_target():
    outbox, _members = _graph(platform="instagram", suffix="public", target_keys=())

    first = ensure_targets(outbox.ref)
    replay = ensure_targets(outbox.ref)

    assert len(first) == len(replay) == 1
    assert first[0].pk == replay[0].pk
    assert first[0].member_id is None
    assert first[0].platform == "instagram"


def test_member_from_another_snapshot_is_rejected():
    outbox, _members = _graph(suffix="inside", target_keys=("inside",))
    _other_outbox, other_members = _graph(suffix="outside", target_keys=("outside",))

    with pytest.raises(MarketingContractError) as caught:
        ensure_targets(outbox.ref, member_ids=[other_members[0].pk])

    assert caught.value.code == "delivery_member_outside_snapshot"
    assert DeliveryTarget.objects.count() == 0


def test_same_member_cannot_enter_two_waves():
    outbox, members = _graph(suffix="waves", target_keys=("one",))
    first = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]
    second_outbox = MarketingOutbox.objects.create(
        command=outbox.command,
        announcement=outbox.announcement,
        snapshot=outbox.snapshot,
        artifact=outbox.artifact,
        platform="whatsapp",
        wave_key="vip",
        state=MarketingOutbox.State.DISPATCHED,
        available_at=outbox.available_at,
        dispatch_ref="directive:ledger:waves-two",
        dispatched_at=outbox.dispatched_at,
    )

    with pytest.raises(MarketingContractError) as caught:
        ensure_targets(second_outbox.ref, member_ids=[members[0].pk])

    assert caught.value.code == "delivery_wave_collision"
    assert DeliveryTarget.objects.get().pk == first.pk


def test_target_cap_is_checked_before_membership_query():
    outbox, _members = _graph(
        platform="whatsapp",
        suffix="cap",
        target_keys=(),
    )

    with pytest.raises(MarketingContractError) as caught:
        ensure_targets(
            outbox.ref,
            member_ids=range(1, MAX_TARGETS_PER_COMMAND + 2),
        )

    assert caught.value.code == "delivery_target_cap_exceeded"


def test_attempt_uniques_prevent_duplicate_ordinal_and_token():
    outbox, _members = _graph(platform="instagram", suffix="attempt", target_keys=())
    target = ensure_targets(outbox.ref)[0]
    now = timezone.now()
    common = {
        "target": target,
        "state": DeliveryAttempt.State.PREPARED,
        "request_hash": "a" * 64,
        "started_at": now,
        "retention_until": now + timedelta(days=365 * 5),
    }
    DeliveryAttempt.objects.create(
        **common,
        ordinal=1,
        idempotency_token_hash="b" * 64,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryAttempt.objects.create(
                **common,
                ordinal=1,
                idempotency_token_hash="c" * 64,
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryAttempt.objects.create(
                **common,
                ordinal=2,
                idempotency_token_hash="b" * 64,
            )


def test_ledger_rows_never_copy_contact_or_content():
    outbox, members = _graph(suffix="privacy", target_keys=("private",))
    phone = members[0].customer.phone
    target = ensure_targets(outbox.ref, member_ids=[members[0].pk])[0]

    serialized = json.dumps(
        {
            field.name: getattr(target, field.attname)
            for field in target._meta.concrete_fields
        },
        default=str,
    )
    field_names = {field.name for field in target._meta.concrete_fields}
    assert phone not in serialized
    assert "Fornada pronta" not in serialized
    assert not ({"phone", "email", "recipient", "content", "body"} & field_names)


@pytest.mark.django_db(transaction=True)
def test_delivery_ledger_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0029_marketing_outbox_recovery")]
    after = [("shop", "0030_marketing_delivery_ledger")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    tables = set(connection.introspection.table_names())
    assert "shop_deliverytarget" not in tables
    assert "shop_deliveryattempt" not in tables

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    tables = set(connection.introspection.table_names())
    assert {"shop_deliverytarget", "shop_deliveryattempt"} <= tables

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
