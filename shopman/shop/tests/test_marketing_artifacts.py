"""MKT-025 — one immutable artifact from preview through provider boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.shop.models import Announcement, AnnouncementStatus, DeliveryTarget, MarketingOutbox
from shopman.shop.services import campaign
from shopman.shop.services.marketing_approval import approve_command
from shopman.shop.services.marketing_artifacts import (
    resolve_all_dispatch_artifacts,
    resolve_approved_dispatch_artifact,
    resolve_dispatch_artifact,
    resolved_payloads,
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
GOLDEN_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "marketing"
    / "resolved_dispatch_artifacts.v2.json"
)


@pytest.fixture(autouse=True)
def trusted_artifact_origins(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.example"
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("cdn.example", "example.test")


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
            "link": "https://shop.example/produto/croissant",
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


def test_multichannel_variants_match_the_golden_and_inherit_only_absent_fields():
    class Template:
        platform_variants = {
            "instagram": {
                "body": "{{product_name}} no forno ✨",
                "hashtags": ["{{tag}}", "instacroissant"],
                "post_type": "FEED",
            },
            "google_business": {"post_type": "OFFER"},
            "whatsapp": {
                "body": "{{product_name}} quentinho. Peça agora: {{link}}",
                "template_name": "fornada_v3",
            },
        }

    variables = {
        "link": "https://shop.example/produto/croissant",
        "product_name": "Croissant Tradicional",
        "tag": "feitohoje",
    }
    content = {
        "body": "Croissant Tradicional acabou de sair do forno ✨",
        "hashtags": ["feitohoje", "croissant"],
        "image_url": "https://cdn.example/croissant.jpg",
        "link": variables["link"],
        "variables": variables,
    }
    platforms = ["instagram", "google_business", "whatsapp"]
    platform_content = campaign._platform_content(
        Template(),
        content,
        platforms=platforms,
    )

    actual = resolved_payloads(resolve_all_dispatch_artifacts(
        platforms=platforms,
        content=content,
        platform_content=platform_content,
        content_version=7,
        facts_hash="a" * 64,
    ))

    assert actual == json.loads(GOLDEN_PATH.read_text())
    assert actual["instagram"]["body"] == "Croissant Tradicional no forno ✨"
    assert actual["google_business"]["body"] == content["body"]
    assert actual["whatsapp"]["provider_fields"] == {
        "template_name": "fornada_v3"
    }


def test_unknown_variant_variable_points_to_the_exact_nested_field():
    class Template:
        platform_variants = {
            "instagram": {"body": "Olá {{unknown_product}}"},
        }

    with pytest.raises(MarketingContractError) as caught:
        campaign._platform_content(
            Template(),
            {"variables": {"product_name": "Croissant"}},
        )

    assert caught.value.code == "unknown_template_variable"
    assert caught.value.field_errors == {
        "platform_variants.instagram.body": (
            "Variável não reconhecida: unknown_product.",
        )
    }


@pytest.mark.parametrize("provider_field", ["flow_id", "access_token", "credentials"])
def test_content_cannot_choose_flow_or_credentials(provider_field):
    with pytest.raises(MarketingContractError) as caught:
        resolve_dispatch_artifact(
            platform="whatsapp",
            content={"body": "Fornada pronta"},
            platform_content={"whatsapp": {provider_field: "operator-controlled"}},
            content_version=1,
        )

    assert caught.value.code == "invalid_provider_field"
    assert f"platform_content.whatsapp.{provider_field}" in caught.value.field_errors


def test_server_owned_flow_binding_changes_the_exact_artifact_hash():
    common = {
        "platform": "whatsapp",
        "content": {"body": "Fornada pronta"},
        "platform_content": {},
        "content_version": 3,
        "flow_version": 7,
        "flow_catalog_hash": "a" * 64,
    }

    first = resolve_dispatch_artifact(flow_ref="content_flow_a", **common)
    second = resolve_dispatch_artifact(flow_ref="content_flow_b", **common)

    assert first.artifact_hash != second.artifact_hash
    assert first.as_payload()["flow_ref"] == "content_flow_a"


def test_non_whatsapp_artifact_cannot_carry_a_flow_binding():
    with pytest.raises(MarketingContractError) as caught:
        resolve_dispatch_artifact(
            platform="instagram",
            content={"body": "Fornada pronta"},
            platform_content={},
            content_version=3,
            flow_ref="content_flow_a",
            flow_version=2,
            flow_catalog_hash="a" * 64,
        )

    assert caught.value.code == "flow_binding_platform_mismatch"


def test_preview_approved_evidence_and_provider_receive_the_exact_same_hash():
    preview = campaign.preview(
        "Croissant saiu do forno ✨",
        platform="instagram",
        content_version=2,
    )
    preview_artifact = preview["artifact"]
    actor = get_user_model().objects.create_user(username="artifact-operator")
    approved_content = {
        "body": preview_artifact["body"],
        "hashtags": preview_artifact["hashtags"],
        "link": preview_artifact["link"],
        "image_url": preview_artifact["image_url"],
        "facts": preview["facts"],
    }
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content=approved_content,
        platforms=["instagram"],
    )
    result = approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key="artifact-approval-0001",
        base_version=1,
        publish_mode="now",
        content=approved_content,
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
