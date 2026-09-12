"""Correlation is local IDs; general telemetry never carries transport secrets."""
import logging

import pytest

from shopman.shop.models import Conversation
from shopman.storefront.concierge import service, transport

pytestmark = pytest.mark.django_db


def test_ingress_telemetry_correlates_internal_ids_without_payload(settings, caplog, monkeypatch):
    subject = "private-subject-canary"
    secret_text = "private-address-canary"
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True, "contract_version": 2, "account_id": "synthetic",
        "allowed_subscribers": [subject],
    }
    operational_logger = logging.getLogger("shopman.operational")
    monkeypatch.setattr(operational_logger, "handlers", [*operational_logger.handlers, caplog.handler])
    with caplog.at_level(logging.INFO):
        result = service.receive_inbound(subscriber_id=subject, text=secret_text, external_id="private-event-canary")
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
    settings.SHOPMAN_CONCIERGE = {"enabled": False, "contract_version": 2}
    with caplog.at_level(logging.INFO):
        service.receive_inbound(subscriber_id=subject, text="private-address", external_id="private-event")
        settings.SHOPMAN_CONCIERGE = {"enabled": True, "contract_version": 2, "allowed_subscribers": []}
        service.receive_inbound(subscriber_id=subject, text="private-address", external_id="private-event")
        conversation = Conversation.objects.create(subscriber_id=subject)
        def fail(*args):
            raise RuntimeError("private-provider-key-canary")
        monkeypatch.setattr(transport, "identity_for", fail)
        service.identify(conversation)
    assert "concierge.identify failed" in caplog.text
    assert "concierge.not_allowed" in caplog.text
    assert subject not in caplog.text
    assert "private-address" not in caplog.text
    assert "private-provider-key-canary" not in caplog.text
