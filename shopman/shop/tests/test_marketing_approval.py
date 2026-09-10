"""MKT-010 — approval seals content, cohort, audit and outbox atomically."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Directive

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    MarketingAISuggestion,
    MarketingAISuggestionEvent,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    MarketingOutbox,
    NotificationTemplate,
    Trigger,
)
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services import marketing_ai
from shopman.shop.services.marketing_approval import (
    PUBLISH_NOW,
    PUBLISH_SCHEDULED,
    approve_command,
    canonical_artifact_bytes,
)
from shopman.shop.services.marketing_artifacts import (
    SCHEMA_VERSION,
    resolve_all_dispatch_artifacts,
    resolved_payloads,
)
from shopman.shop.services.marketing_commands import MarketingCommandRejected
from shopman.shop.services.marketing_contracts import MarketingContractError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def trusted_approval_origins(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://example.test"
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("example.test",)


@pytest.fixture
def actor():
    return get_user_model().objects.create_user(
        username="approval-operator",
        password="irrelevant",
    )


@pytest.fixture
def announcement():
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Texto anterior", "hashtags": []},
        platform_content={},
        platforms=["instagram"],
        trigger_context={"sku": "CRO-001"},
    )


def _approve(
    *,
    actor,
    announcement,
    key="idem-approval-00000001",
    content=None,
    platform_content=None,
    platforms=None,
    publish_mode=PUBLISH_NOW,
    publish_at=None,
    publish_timezone="",
    now=None,
    ai_suggestion_ref="",
):
    return approve_command(
        announcement.pk,
        actor=actor,
        idempotency_key=key,
        base_version=1,
        publish_mode=publish_mode,
        publish_at=publish_at,
        publish_timezone=publish_timezone,
        content=content
        or {
            "body": "Croissant saiu do forno.",
            "hashtags": ["feitohoje"],
            "image_url": "https://example.test/croissant.jpg",
            "link": "https://example.test/produto/croissant",
        },
        platform_content=platform_content or {},
        platforms=platforms or ["instagram", "google_business"],
        request_id="req_approval_001",
        ai_suggestion_ref=ai_suggestion_ref,
        now=now,
    )


def test_approval_records_whether_ai_copy_was_edited(actor):
    product = Product.objects.create(
        sku="AI-001",
        name="Croissant",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    template = AnnouncementTemplate.objects.create(
        name="Fornada IA",
        body="{{product_name}} saiu do forno.",
        use_ai_generation=True,
    )
    rule = Campaign.objects.create(
        name="Fornada IA",
        trigger=Trigger.PRODUCTION_FINISHED,
        template=template,
        platforms=["instagram"],
        requires_approval=True,
    )
    announcement = campaign_service._create_announcement(rule, {"sku": product.sku})
    _, facts_hash = marketing_ai._current_facts(announcement)
    suggestion = MarketingAISuggestion.objects.create(
        announcement=announcement,
        requested_by=actor,
        actor_ref=f"user:{actor.pk}",
        state=MarketingAISuggestion.State.GENERATED,
        outcome_code="schema_valid",
        base_version=announcement.version,
        provider_ref="anthropic",
        model_ref="test-model",
        policy_version="marketing-ai-v2.1",
        facts_hash=facts_hash,
        prompt_hash="a" * 64,
        suggestion_hash=marketing_ai.content_hash("Sugestão original", ["feitohoje"]),
        body_hash=marketing_ai._field_hash("body", "Sugestão original"),
        hashtags_hash=marketing_ai._field_hash("hashtags", ["feitohoje"]),
        retention_until=timezone.now() + timedelta(days=365),
    )

    result = _approve(
        actor=actor,
        announcement=announcement,
        content={
            **announcement.content,
            "body": "Sugestão editada",
            "hashtags": ["feitohoje"],
        },
        platforms=["instagram"],
        ai_suggestion_ref=str(suggestion.ref),
    )

    event = MarketingAISuggestionEvent.objects.get(command=result.receipt)
    assert event.suggestion == suggestion
    assert event.event_type == MarketingAISuggestionEvent.EventType.APPROVED_EDITED
    assert event.diff_fields == ["body"]
    assert event.result_hash


def test_approval_commits_one_connected_graph_without_provider_or_directive(actor, announcement):
    result = _approve(actor=actor, announcement=announcement)

    announcement.refresh_from_db()
    audit = MarketingAuditEvent.objects.get(command=result.receipt)
    assert result.replayed is False
    assert announcement.status == AnnouncementStatus.PUBLISHING
    assert announcement.version == 2
    assert announcement.approved_by_id == actor.pk
    assert result.receipt.state == MarketingCommandReceipt.State.COMPLETED
    assert result.receipt.resulting_version == 2
    assert result.receipt.outcome["audience_count"] == 0
    assert result.receipt.outcome["platforms"] == [
        "instagram",
        "google_business",
    ]
    assert result.artifact.announcement_id == announcement.pk
    assert result.artifact.version == result.snapshot.version == 2
    assert result.snapshot.announcement_id == announcement.pk
    assert audit.announcement_id == announcement.pk
    assert audit.actor_id == actor.pk
    assert audit.artifact_id == result.artifact.pk
    assert audit.snapshot_id == result.snapshot.pk
    assert (audit.base_version, audit.resulting_version) == (1, 2)
    assert audit.facts == {
        "audience_count": 0,
        "outbox_count": 2,
        "platform_count": 2,
        "publish_at": "",
        "publish_mode": "now",
        "publish_timezone": "America/Sao_Paulo",
    }
    assert {entry.platform for entry in result.outbox} == {
        "instagram",
        "google_business",
    }
    assert all(entry.state == MarketingOutbox.State.PENDING for entry in result.outbox)
    assert all(entry.command_id == result.receipt.pk for entry in result.outbox)
    assert all(entry.artifact_id == result.artifact.pk for entry in result.outbox)
    assert all(entry.snapshot_id == result.snapshot.pk for entry in result.outbox)
    assert Directive.objects.count() == 0


def test_artifact_hash_matches_exact_canonical_approved_bytes(actor, announcement):
    content = {
        "body": "Pão de queijo às 17h — quentinho.",
        "hashtags": ["pãodequeijo", "feitohoje"],
        "image_url": "https://example.test/pao.jpg",
        "link": "https://example.test/produto/pao-de-queijo",
    }
    variants = {"instagram": {"body": "Pão de queijo às 17h ✨"}}

    decision_time = timezone.now()
    result = _approve(
        actor=actor,
        announcement=announcement,
        content=content,
        platform_content=variants,
        now=decision_time,
    )

    expected_payload = {
        "content": content,
        "content_version": 2,
        "platform_content": variants,
        "platforms": ["instagram", "google_business"],
        "resolved_artifacts": resolved_payloads(
            resolve_all_dispatch_artifacts(
                platforms=["instagram", "google_business"],
                content=content,
                platform_content=variants,
                content_version=2,
            )
        ),
        "schema_version": SCHEMA_VERSION,
        "schedule": {
            "effective_at": "",
            "publish_at": "",
            "publish_mode": "now",
            "timezone": "America/Sao_Paulo",
        },
    }
    expected_bytes = canonical_artifact_bytes(expected_payload)
    assert result.artifact.payload == expected_payload
    assert result.artifact.schema_version == SCHEMA_VERSION
    assert result.artifact.canonical_bytes() == expected_bytes
    assert result.artifact.artifact_hash == hashlib.sha256(expected_bytes).hexdigest()
    assert result.receipt.outcome["artifact_hash"] == result.artifact.artifact_hash


def test_scheduled_instant_is_identical_in_artifact_receipt_and_outbox(
    actor,
    announcement,
):
    now = datetime.fromisoformat("2026-09-09T09:00:00-03:00")
    publish_at = datetime.fromisoformat("2026-09-09T10:15:00-03:00")

    result = _approve(
        actor=actor,
        announcement=announcement,
        key="idem-canonical-instant-0001",
        platforms=["instagram"],
        publish_mode=PUBLISH_SCHEDULED,
        publish_at=publish_at,
        publish_timezone="America/Sao_Paulo",
        now=now,
    )

    assert result.artifact.payload["schedule"] == {
        "effective_at": publish_at.isoformat(),
        "publish_at": publish_at.isoformat(),
        "publish_mode": "scheduled",
        "timezone": "America/Sao_Paulo",
    }
    assert result.receipt.outcome["publish_at"] == publish_at.isoformat()
    assert result.receipt.outcome["publish_timezone"] == "America/Sao_Paulo"
    assert [row.available_at for row in result.outbox] == [publish_at]


def test_schedule_at_expiry_is_rejected_before_any_delivery_graph(actor, announcement):
    now = datetime.fromisoformat("2026-09-09T09:00:00-03:00")
    announcement.expires_at = now + timedelta(hours=1)
    announcement.save(update_fields=["expires_at"])

    with pytest.raises(MarketingCommandRejected) as caught:
        _approve(
            actor=actor,
            announcement=announcement,
            key="idem-expiry-boundary-0001",
            platforms=["instagram"],
            publish_mode=PUBLISH_SCHEDULED,
            publish_at=announcement.expires_at,
            publish_timezone="America/Sao_Paulo",
            now=now,
        )

    assert caught.value.code == "scheduled_after_expiry"
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_whatsapp_now_is_blocked_during_quiet_hours_before_audience_work(
    actor,
    announcement,
):
    now = datetime.fromisoformat("2026-09-09T21:00:00-03:00")

    with pytest.raises(MarketingCommandRejected) as caught:
        _approve(
            actor=actor,
            announcement=announcement,
            key="idem-quiet-hours-000001",
            platforms=["whatsapp"],
            now=now,
        )

    assert caught.value.code == "quiet_hours_active"
    receipt = MarketingCommandReceipt.objects.get(ref=caught.value.receipt_ref)
    assert receipt.outcome["next_allowed_at"] == "2026-09-10T08:00:00-03:00"
    assert receipt.outcome["publish_timezone"] == "America/Sao_Paulo"
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_social_publish_now_is_not_blocked_by_direct_message_quiet_hours(
    actor,
    announcement,
):
    now = datetime.fromisoformat("2026-09-09T21:00:00-03:00")

    result = _approve(
        actor=actor,
        announcement=announcement,
        key="idem-social-quiet-hours-01",
        platforms=["instagram"],
        publish_timezone="America/Sao_Paulo",
        now=now,
    )

    assert result.receipt.state == MarketingCommandReceipt.State.COMPLETED
    assert result.outbox[0].available_at == now


def test_input_mutation_after_approval_cannot_change_sealed_artifact(actor, announcement):
    content = {"body": "Original", "hashtags": ["original"]}
    result = _approve(actor=actor, announcement=announcement, content=content)

    content["body"] = "Alterado fora"
    content["hashtags"].append("tarde")
    result.artifact.refresh_from_db()

    assert result.artifact.payload["content"] == {
        "body": "Original",
        "hashtags": ["original"],
    }


def test_untrusted_media_is_rejected_before_artifact_and_outbox(actor, announcement):
    with pytest.raises(MarketingContractError) as caught:
        _approve(
            actor=actor,
            announcement=announcement,
            key="idem-approval-private-media",
            content={
                "body": "Original",
                "image_url": "https://169.254.169.254/latest/meta-data",
                "link": "https://example.test/produto/CRO-001",
            },
        )

    assert caught.value.code == "marketing_media_private_host"
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_same_key_replays_same_artifact_snapshot_audit_and_outbox(actor, announcement):
    first = _approve(actor=actor, announcement=announcement)
    second = _approve(actor=actor, announcement=announcement)

    assert second.replayed is True
    assert second.receipt.pk == first.receipt.pk
    assert second.artifact.pk == first.artifact.pk
    assert second.snapshot.pk == first.snapshot.pk
    assert [row.pk for row in second.outbox] == [row.pk for row in first.outbox]
    assert MarketingContentArtifact.objects.count() == 1
    assert MarketingAuditEvent.objects.count() == 1
    assert MarketingOutbox.objects.count() == 2


def test_crash_before_audit_rolls_back_entire_approval_graph(actor, announcement):
    with patch.object(
        MarketingAuditEvent.objects,
        "create",
        side_effect=RuntimeError("injected-before-audit"),
    ):
        with pytest.raises(RuntimeError, match="injected-before-audit"):
            _approve(actor=actor, announcement=announcement)

    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1
    assert MarketingCommandReceipt.objects.count() == 0
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingAuditEvent.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0
    assert announcement.audience_snapshots.count() == 0


def test_scheduled_approval_uses_one_absolute_instant_for_announcement_audit_and_outbox(actor, announcement):
    publish_at = timezone.now() + timedelta(hours=3)

    result = _approve(
        actor=actor,
        announcement=announcement,
        key="idem-approval-00000002",
        publish_mode=PUBLISH_SCHEDULED,
        publish_at=publish_at,
    )

    announcement.refresh_from_db()
    audit = MarketingAuditEvent.objects.get(command=result.receipt)
    assert announcement.status == AnnouncementStatus.APPROVED
    assert announcement.publish_at == publish_at
    assert audit.facts["publish_at"] == publish_at.isoformat()
    assert {entry.available_at for entry in result.outbox} == {publish_at}


@pytest.mark.parametrize(
    ("mode", "publish_at", "code"),
    [
        (PUBLISH_NOW, timezone.now() + timedelta(hours=1), "publish_now_has_schedule"),
        (PUBLISH_SCHEDULED, None, "scheduled_publish_at_required"),
        (PUBLISH_SCHEDULED, timezone.now() - timedelta(hours=1), "scheduled_publish_at_past"),
    ],
)
def test_publish_mode_has_no_implicit_boolean_or_ambiguous_instant(actor, announcement, mode, publish_at, code):
    with pytest.raises(MarketingContractError) as caught:
        _approve(
            actor=actor,
            announcement=announcement,
            key=f"idem-approval-mode-{code}",
            publish_mode=mode,
            publish_at=publish_at,
        )

    assert caught.value.code == code
    assert MarketingCommandReceipt.objects.count() == 0


def test_whatsapp_below_minimum_is_rejected_before_any_effect_shaped_row(actor, announcement):
    with pytest.raises(MarketingCommandRejected) as caught:
        _approve(
            actor=actor,
            announcement=announcement,
            key="idem-approval-00000003",
            platforms=["whatsapp"],
        )

    announcement.refresh_from_db()
    assert caught.value.code == "audience_below_minimum"
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert announcement.version == 1
    receipt = MarketingCommandReceipt.objects.get(ref=caught.value.receipt_ref)
    assert receipt.state == MarketingCommandReceipt.State.REJECTED
    assert receipt.outcome == {
        "code": "audience_below_minimum",
        "eligible_count": 0,
        "minimum_count": 10,
    }
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_whatsapp_at_approved_minimum_seals_exact_members_flow_and_one_wave(actor, announcement, monkeypatch):
    refs = []
    for number in range(10):
        customer = Customer.objects.create(
            ref=f"MKT-APPROVAL-{number}",
            first_name=f"Pessoa {number}",
            phone=f"+554399910{number:04d}",
        )
        ConsentService.grant_consent(customer.ref, "whatsapp", source="approval-test")
        refs.append(customer.ref)
    template = AnnouncementTemplate.objects.create(name="WhatsApp", body="Novidade")
    rule = Campaign.objects.create(
        name="Público mínimo",
        trigger="manual",
        template=template,
        platforms=["whatsapp"],
        audience_rules={"customer_refs": refs},
    )
    announcement.rule = rule
    announcement.template = template
    announcement.save(update_fields=["rule", "template"])
    NotificationTemplate.objects.create(
        event="announcement_published",
        subject="x",
        body="y",
        whatsapp_flow_ns="content_approval_flow",
        version=4,
    )
    from shopman.shop.services.manychat_flows import FlowCatalog

    checked_at = timezone.now()
    monkeypatch.setattr(
        "shopman.shop.services.manychat_flows.flow_catalog",
        lambda **kwargs: FlowCatalog(
            flows=(("content_approval_flow", "Campanha geral"),),
            state="fresh",
            checked_at=checked_at,
            facts_as_of=checked_at,
            fresh_until=checked_at + timedelta(minutes=5),
            catalog_hash="a" * 64,
        ),
    )

    with pytest.raises(MarketingCommandRejected) as blocked:
        _approve(
            actor=actor,
            announcement=announcement,
            key="idem-approval-unverified-flow",
            platforms=["whatsapp"],
        )
    assert blocked.value.code == "manychat_custom_fields_unverified"
    assert MarketingContentArtifact.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0

    monkeypatch.setattr(
        "shopman.shop.services.manychat_marketing_safety.require_safe_delivery",
        lambda: None,
    )

    result = _approve(
        actor=actor,
        announcement=announcement,
        key="idem-approval-00000004",
        platforms=["whatsapp"],
    )

    assert result.snapshot.members.count() == 10
    assert result.snapshot.summary["total"] == 10
    assert [(entry.platform, entry.wave_key) for entry in result.outbox] == [("whatsapp", "all")]
    resolved = result.artifact.payload["resolved_artifacts"]["whatsapp"]
    assert resolved["flow_ref"] == "content_approval_flow"
    assert resolved["flow_version"] == 4
    assert resolved["flow_catalog_hash"] == "a" * 64
    assert Directive.objects.count() == 0


def test_sealed_artifact_and_audit_refuse_instance_and_bulk_rewrites(actor, announcement):
    result = _approve(actor=actor, announcement=announcement)
    audit = MarketingAuditEvent.objects.get(command=result.receipt)
    result.artifact.payload = {"body": "tampered"}

    with pytest.raises(ValidationError, match="imutáveis"):
        result.artifact.save()
    with pytest.raises(ValidationError, match="imutáveis"):
        MarketingContentArtifact.objects.filter(pk=result.artifact.pk).update(artifact_hash="0" * 64)
    with pytest.raises(ValidationError, match="imutáveis"):
        audit.save()
    with pytest.raises(ValidationError, match="não podem ser apagados"):
        MarketingAuditEvent.objects.filter(pk=audit.pk).delete()


def test_artifact_model_refuses_a_forged_hash(announcement):
    with pytest.raises(ValidationError, match="não confere"):
        MarketingContentArtifact.objects.create(
            announcement=announcement,
            version=2,
            payload={"schema_version": 1, "content": {"body": "válido"}},
            artifact_hash="0" * 64,
            retention_until=timezone.now() + timedelta(days=365 * 5),
        )


@pytest.mark.django_db(transaction=True)
def test_approval_schema_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0026_marketing_command_receipt")]
    after = [("shop", "0027_marketing_approval_outbox")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    tables_before = set(connection.introspection.table_names())
    assert "shop_marketingcontentartifact" not in tables_before
    assert "shop_marketingauditevent" not in tables_before
    assert "shop_marketingoutbox" not in tables_before

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    tables_after = set(connection.introspection.table_names())
    assert {
        "shop_marketingcontentartifact",
        "shop_marketingauditevent",
        "shop_marketingoutbox",
    } <= tables_after

    # Migration tests must not leak an old schema into whichever test pytest
    # schedules next.
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
