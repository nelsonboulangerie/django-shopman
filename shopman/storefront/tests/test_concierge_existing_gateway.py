"""Compatibilidade do portão #c existente com ingresso v2, sem rede/credenciais reais."""

import json
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.urls import reverse
from shopman.orderman.models import Directive, Order, Session

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def existing_gateway(settings, monkeypatch):
    # Representa o fallback de configuração já existente, sem ler token real.
    settings.DOORMAN_ACCESS_LINK_API_KEY = "existing-shared-test-only-key"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 2,
        "account_id": "synthetic-existing-account",
        "api_key": settings.DOORMAN_ACCESS_LINK_API_KEY,
        "allowed_subscribers": ["test-subject"],
    }
    settings.AI_ASSIST_API_KEY = "fake"
    forbidden = Mock(side_effect=AssertionError("external enrichment on ACK"))
    monkeypatch.setattr(service, "identify", forbidden)
    cache.clear()
    yield
    forbidden.assert_not_called()
    cache.clear()


def post(client, settings, event_id=None):
    payload = {"subscriber_id": "test-subject", "text": "#c quero dois pães"}
    if event_id is not None:
        payload["event_id"] = event_id
    return client.post(
        reverse("concierge:manychat-conversation"),
        json.dumps(payload),
        content_type="application/json",
        HTTP_X_API_KEY=settings.DOORMAN_ACCESS_LINK_API_KEY,
    )


def test_existing_keyword_endpoint_and_shared_key_accept_minimal_event(client, settings):
    response = post(client, settings, "provider-event-1")
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "queued": True}
    message = ConversationMessage.objects.get()
    assert message.text == "quero dois pães"
    assert message.envelope["event_id"] == "provider-event-1"
    assert message.envelope.get("profile") == {}
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1
    assert not Order.objects.exists() and not Session.objects.exists()


def test_existing_gateway_replay_keeps_one_event_and_one_work_item(client, settings):
    assert post(client, settings, "provider-event-1").json()["status"] == "queued"
    replay = post(client, settings, "provider-event-1")
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate"
    assert ConversationMessage.objects.count() == Conversation.objects.count() == 1
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1


def test_identical_text_in_two_provider_events_is_two_messages(client, settings):
    assert post(client, settings, "provider-event-1").json()["queued"]
    assert post(client, settings, "provider-event-2").json()["queued"]
    assert ConversationMessage.objects.count() == 2
    assert {m.envelope["event_id"] for m in ConversationMessage.objects.all()} == {
        "provider-event-1",
        "provider-event-2",
    }
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1


def test_legacy_payload_without_event_id_has_no_automatic_effect(client, settings):
    response = post(client, settings)
    assert response.status_code == 200
    assert response.json() == {"status": "event_id_required", "queued": False}
    assert not Conversation.objects.exists()
    assert not ConversationMessage.objects.exists()
    assert not Directive.objects.exists()
    assert not Session.objects.exists() and not Order.objects.exists()
