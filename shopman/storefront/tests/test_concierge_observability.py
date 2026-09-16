"""Correlation is local IDs; general telemetry never carries transport secrets."""

import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding
from shopman.storefront.concierge import service, transport
from shopman.storefront.concierge.contracts import InboundEvent, TransportScope, WindowEvidence

pytestmark = pytest.mark.django_db


def _config(subject):
    return {
        "enabled": True,
        "contract_version": 3,
        "connections": {
            "synthetic": {
                "active": True,
                "provider": "opaque-test",
                "account": "synthetic",
                "channel": "text-only-test",
                "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
                "options": {"allowed_subjects": [subject], "identity_link_enabled": True},
            }
        },
    }


def _event(subject, text, event_id):
    now = timezone.now()
    return InboundEvent(
        scope=TransportScope("opaque-test", "synthetic", "text-only-test", subject, "synthetic"),
        text=text,
        message_type="text",
        received_at=now,
        event_id=event_id,
        event_identity_assurance="verified",
        payload_hash="opaque-payload-hash",
        window_evidence=WindowEvidence(
            "opaque-test-v1", "opaque-event", now, now + timedelta(minutes=30), "provider_window"
        ),
    )


def test_ingress_telemetry_correlates_internal_ids_without_payload(settings, caplog, monkeypatch):
    subject = "private-subject-canary"
    secret_text = "private-address-canary"
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = _config(subject)
    operational_logger = logging.getLogger("shopman.operational")
    monkeypatch.setattr(operational_logger, "handlers", [*operational_logger.handlers, caplog.handler])
    with caplog.at_level(logging.INFO):
        result = service.receive_inbound(_event(subject, secret_text, "private-event-canary"))
    record = next(r for r in caplog.records if getattr(r, "event", "") == "concierge.stage")
    assert record.conversation_id == result.conversation_id
    assert record.message_id == result.message_id
    assert record.duration_ms >= 0
    assert record.outcome == "queued"
    assert all(secret not in str(record.__dict__) for secret in (subject, secret_text, "private-event-canary"))


def test_rejection_and_identity_failure_do_not_log_subject_or_provider_echo(settings, monkeypatch, caplog):
    subject = "private-subject-canary"
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    monkeypatch.setattr(service.logger, "handlers", [*service.logger.handlers, caplog.handler])
    settings.SHOPMAN_CONCIERGE = {**_config(subject), "enabled": False}
    with caplog.at_level(logging.INFO):
        service.receive_inbound(_event(subject, "private-address", "private-event"))
        settings.SHOPMAN_CONCIERGE = _config("someone-else")
        service.receive_inbound(_event(subject, "private-address", "private-event"))
        settings.SHOPMAN_CONCIERGE = _config(subject)
        conversation = Conversation.objects.create()
        binding = ConversationBinding.objects.create(
            conversation=conversation,
            provider="opaque-test",
            account="synthetic",
            transport_channel="text-only-test",
            subject=subject,
            connection_key="synthetic",
            status="active",
        )
        def fail(*args):
            raise RuntimeError("private-provider-key-canary")
        monkeypatch.setattr(transport, "identity_for", fail)
        service.identify(conversation, binding)
    assert "concierge.identify failed" in caplog.text
    assert "concierge.not_allowed" in caplog.text
    assert subject not in caplog.text
    assert "private-address" not in caplog.text
    assert "private-provider-key-canary" not in caplog.text
