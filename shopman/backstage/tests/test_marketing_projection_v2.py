"""MKT-021 — canonical, versioned and presentation-free Marketing projection."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.utils import timezone
from pydantic import TypeAdapter

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.marketing_v2 import (
    CONTRACT,
    MarketingEnvelopeV2,
    build_announcement,
    build_board,
    schema,
)
from shopman.shop.models import Announcement, AnnouncementStatus, DeliveryTarget
from shopman.shop.services.marketing_delivery_worker import fanout_in_chunks
from shopman.shop.tests.test_marketing_delivery_ledger import _graph

pytestmark = pytest.mark.django_db

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts/projections/marketing_v2.schema.json"
FORBIDDEN_PROPERTIES = {
    "approved_by",
    "audience_members",
    "body",
    "copy",
    "detail",
    "member",
    "members",
    "platform_results",
    "provider_error",
    "rejected_by",
    "rejected_reason",
    "status_label",
    "trigger_context",
    "trigger_label",
}


def _property_names(value: object) -> set[str]:
    if is_dataclass(value):
        return {
            item.name
            for item in fields(value)
        } | {
            nested
            for item in fields(value)
            for nested in _property_names(getattr(value, item.name))
        }
    if isinstance(value, dict):
        return set(value) | {
            nested for item in value.values() for nested in _property_names(item)
        }
    if isinstance(value, tuple | list):
        return {nested for item in value for nested in _property_names(item)}
    return set()


def test_projection_schema_is_the_committed_golden():
    rendered = json.dumps(schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    assert SCHEMA_PATH.exists()
    assert rendered == SCHEMA_PATH.read_text(encoding="utf-8")


def test_projection_excludes_presentation_copy_pii_membership_and_legacy_results():
    outbox, members = _graph(
        suffix="projection-no-pii",
        target_keys=("customer-one",),
    )
    private_marker = "private.person@example.test"
    Announcement.objects.filter(pk=outbox.announcement_id).update(
        approved_by=outbox.command.actor,
        content={"body": f"Do not project {private_marker}"},
        trigger_context={
            "customer_name": "Pessoa Privada",
            "phone": "+5543999999999",
            "email": private_marker,
            "sku": "SKU-SAFE-01",
        },
        platform_results={"whatsapp": {"detail": private_marker}},
    )
    announcement = Announcement.objects.select_related("rule", "template").get(
        pk=outbox.announcement_id
    )

    envelope = build_announcement(announcement)
    payload = projection_data(envelope)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert _property_names(envelope).isdisjoint(FORBIDDEN_PROPERTIES)
    assert not any(name.endswith("_label") for name in _property_names(envelope))
    assert private_marker not in serialized
    assert "Pessoa Privada" not in serialized
    assert "+5543999999999" not in serialized
    assert members[0].target_key not in serialized
    assert "Fornada pronta" not in serialized
    assert payload["data"]["announcement"]["facts"]["product_ref"] == "product:SKU-SAFE-01"
    assert payload["data"]["announcement"]["decision_actor_policy"] == "operator"
    assert payload["data"]["announcement"]["artifact"]["artifact_hash"]
    assert "payload" not in payload["data"]["announcement"]["artifact"]

    validated = TypeAdapter(MarketingEnvelopeV2).validate_python(payload)
    assert validated.contract == CONTRACT


def test_legacy_json_cannot_inject_pii_through_audience_metadata():
    now = timezone.now()
    private_marker = "private.person@example.test"
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        audience={
            "eligible_count": 3,
            "excluded_by_reason": {
                "global_optout": 1,
                private_marker: 2,
            },
            "policy_version": private_marker,
            "calculated_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
    )

    payload = projection_data(build_announcement(announcement, now=now))
    audience = payload["data"]["announcement"]["audience"]

    assert private_marker not in json.dumps(payload)
    assert audience["policy_version"] == ""
    assert audience["excluded_by_reason"] == {
        "global_optout": 1,
        "unclassified": 2,
    }


def test_board_uses_ledger_counters_and_keeps_accepted_distinct_from_confirmed():
    outbox, members = _graph(
        suffix="projection-counts",
        target_keys=("accepted", "confirmed", "failed", "unknown"),
    )
    fanout_in_chunks(outbox.ref, member_ids=[member.pk for member in members])
    targets = list(DeliveryTarget.objects.filter(outbox=outbox).order_by("pk"))
    now = timezone.now()
    states = (
        DeliveryTarget.State.ACCEPTED,
        DeliveryTarget.State.CONFIRMED,
        DeliveryTarget.State.FAILED_FINAL,
        DeliveryTarget.State.UNKNOWN,
    )
    for target, state in zip(targets, states, strict=True):
        target.state = state
        target.settled_at = now
    DeliveryTarget.objects.bulk_update(targets, ["state", "settled_at"])
    Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Reviewable content"},
        audience={
            "eligible_count": 5000,
            "calculated_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        expires_at=now + timedelta(minutes=5),
    )

    payload = projection_data(build_board(now=now))
    counters = payload["data"]["counters"]
    delivery = next(
        item["delivery"]
        for item in payload["data"]["recent"]
        if item["ref"] == f"announcement:{outbox.announcement_id}"
    )

    assert counters == {
        "pending_decision_count": 1,
        "accepted_unconfirmed_targets_today": 1,
        "confirmed_targets_today": 1,
        "failed_final_targets_today": 1,
        "unknown_targets_open": 1,
    }
    assert delivery["counts"]["accepted"] == 1
    assert delivery["counts"]["confirmed"] == 1
    assert sum(delivery["counts"].values()) == delivery["target_count"] == 4
    assert "audience_reached_today" not in json.dumps(payload)
    assert "published_today" not in json.dumps(payload)


@override_settings(TIME_ZONE="America/Sao_Paulo")
def test_board_daily_counters_always_use_the_canonical_shop_day():
    before_midnight, before_members = _graph(
        suffix="counter-before-shop-midnight",
        target_keys=("before",),
    )
    after_midnight, after_members = _graph(
        suffix="counter-after-shop-midnight",
        target_keys=("after",),
    )
    fanout_in_chunks(
        before_midnight.ref,
        member_ids=[member.pk for member in before_members],
    )
    fanout_in_chunks(
        after_midnight.ref,
        member_ids=[member.pk for member in after_members],
    )
    DeliveryTarget.objects.filter(outbox=before_midnight).update(
        state=DeliveryTarget.State.CONFIRMED,
        settled_at=datetime(2026, 9, 10, 2, 30, tzinfo=UTC),
    )
    DeliveryTarget.objects.filter(outbox=after_midnight).update(
        state=DeliveryTarget.State.CONFIRMED,
        settled_at=datetime(2026, 9, 10, 3, 30, tzinfo=UTC),
    )

    with timezone.override(ZoneInfo("Asia/Tokyo")):
        payload = projection_data(
            build_board(now=datetime(2026, 9, 10, 12, tzinfo=UTC))
        )

    assert payload["data"]["counters"]["confirmed_targets_today"] == 1


def test_board_query_budget_does_not_grow_with_announcement_count(
    django_assert_num_queries,
):
    now = timezone.now()
    Announcement.objects.bulk_create(
        Announcement(
            status=AnnouncementStatus.PENDING_REVIEW,
            content={"body": f"announcement {index}"},
            audience={
                "eligible_count": index,
                "calculated_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
            },
            expires_at=now + timedelta(minutes=5),
        )
        for index in range(75)
    )

    with django_assert_num_queries(6):
        envelope = build_board(now=now)

    assert len(envelope.data.pending) == 75


def test_board_resource_version_does_not_churn_with_the_wall_clock():
    now = timezone.now()
    Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Stable resource"},
        audience={
            "eligible_count": 1,
            "calculated_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        expires_at=now + timedelta(minutes=5),
    )

    first = build_board(now=now)
    second = build_board(now=now + timedelta(seconds=2))

    assert first.resource_version == second.resource_version
    assert first.generated_at != second.generated_at
    assert first.data.pending[0].age_seconds != second.data.pending[0].age_seconds


def test_expired_pending_is_projected_as_expired_without_a_read_side_write():
    now = timezone.now()
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Expired content"},
        expires_at=now - timedelta(seconds=1),
    )

    payload = projection_data(build_announcement(announcement, now=now))
    announcement.refresh_from_db()

    assert payload["data"]["announcement"]["state"] == AnnouncementStatus.EXPIRED
    assert payload["data"]["announcement"]["reason_code"] == "review_window_expired"
    assert payload["data"]["announcement"]["expires_in_seconds"] == 0
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW


def test_v2_endpoints_are_additive_and_keep_the_read_capability(client):
    operator = get_user_model().objects.create_user(
        username="projection-reader",
        is_staff=True,
    )
    operator.user_permissions.add(Permission.objects.get(codename="view_marketing"))
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Never returned on the board"},
    )
    client.force_login(operator)

    board_response = client.get("/api/v1/backstage/marketing/v2/")
    detail_response = client.get(
        f"/api/v1/backstage/marketing/v2/announcements/{announcement.pk}/"
    )

    assert board_response.status_code == 200
    assert board_response.json()["contract"] == CONTRACT
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["kind"] == "announcement_detail"
    assert client.get("/api/v1/backstage/marketing/").status_code == 200
