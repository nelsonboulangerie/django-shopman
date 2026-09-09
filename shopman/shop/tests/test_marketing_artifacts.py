"""MKT-025 — one immutable artifact from preview through provider boundary."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.shop.models import Announcement, AnnouncementStatus, DeliveryTarget, MarketingOutbox
from shopman.shop.services import campaign
from shopman.shop.services.marketing_approval import approve_command
from shopman.shop.services.marketing_artifacts import (
    resolve_approved_dispatch_artifact,
    resolve_dispatch_artifact,
)
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderOutcome,
    ProviderOutcomeKind,
)
from shopman.shop.services.marketing_delivery_attempts import (
    execute_approved_target,
    queue_target,
)
from shopman.shop.services.marketing_delivery_worker import (
    claim_due_targets,
    fanout_in_chunks,
)

pytestmark = pytest.mark.django_db


class CapturingProvider:
    def __init__(self):
        self.artifact = None

    def send(self, *, artifact, target_key, idempotency_token):
        self.artifact = artifact
        return ProviderOutcome(
            kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
            code="provider_accepted",
            retryable=False,
            provider_receipt_ref="receipt-artifact-001",
        )


def test_pure_resolver_is_stable_immutable_and_recipient_free():
    values = {
        "platform": "instagram",
        "content": {
            "body": "Croissant saiu do forno ✨",
            "hashtags": ["feitohoje", "croissant"],
            "link": "https://example.test/p/croissant",
        },
        "platform_content": {},
        "content_version": 2,
    }

    first = resolve_dispatch_artifact(**values)
    second = resolve_dispatch_artifact(**values)

    assert first == second
    assert first.artifact_hash == second.artifact_hash
    assert len(first.artifact_hash) == 64
    serialized = first.canonical_bytes()
    assert b"recipient" not in serialized
    assert b"customer" not in serialized
    with pytest.raises(AttributeError):
        first.body = "mutated"  # type: ignore[misc]


def test_preview_approved_evidence_and_provider_receive_the_exact_same_hash():
    preview = campaign.preview(
        "Croissant saiu do forno ✨",
        platform="instagram",
        content_version=2,
    )
    preview_artifact = preview["artifact"]
    actor = get_user_model().objects.create_user(username="artifact-operator")
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "before review"},
        platforms=["instagram"],
    )
    result = approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key="artifact-approval-0001",
        base_version=1,
        publish_mode="now",
        content={
            "body": preview_artifact["body"],
            "hashtags": preview_artifact["hashtags"],
            "link": preview_artifact["link"],
            "image_url": preview_artifact["image_url"],
        },
        platform_content={},
        platforms=["instagram"],
    )
    approved = resolve_approved_dispatch_artifact(
        result.artifact,
        platform="instagram",
    )

    now = timezone.now()
    outbox = result.outbox[0]
    MarketingOutbox.objects.filter(pk=outbox.pk).update(
        state=MarketingOutbox.State.DISPATCHED,
        dispatch_ref="directive:artifact-proof",
        dispatched_at=now,
    )
    fanout_in_chunks(outbox.ref, now=now)
    target = DeliveryTarget.objects.get(outbox=outbox)
    queue_target(target.ref, now=now)
    claimed = claim_due_targets(worker_id="artifact-proof-worker", now=now)
    assert [item.pk for item in claimed.targets] == [target.pk]

    provider = CapturingProvider()
    execution = execute_approved_target(
        target.ref,
        provider=provider,
        idempotency_token="artifact-attempt-0001",
        worker_id="artifact-proof-worker",
        now=now,
    )

    assert preview["artifact_hash"] == approved.artifact_hash
    assert provider.artifact == approved
    assert provider.artifact.artifact_hash == preview["artifact_hash"]
    assert execution.attempt.request_hash == preview["artifact_hash"]


def test_approved_resolver_fails_closed_if_sealed_payload_is_tampered():
    actor = get_user_model().objects.create_user(username="artifact-tamper")
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "before review"},
        platforms=["instagram"],
    )
    result = approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key="artifact-tamper-0001",
        base_version=1,
        publish_mode="now",
        content={"body": "Approved bytes"},
        platform_content={},
        platforms=["instagram"],
    )
    payload = json.loads(json.dumps(result.artifact.payload))
    payload["resolved_artifacts"]["instagram"]["body"] = "tampered"
    result.artifact.payload = payload

    with pytest.raises(MarketingContractError) as caught:
        resolve_approved_dispatch_artifact(result.artifact, platform="instagram")
    assert caught.value.code == "artifact_hash_mismatch"
