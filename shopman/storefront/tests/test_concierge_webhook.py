"""Fronteira HTTP canônica: rota escolhe connection e adapter normaliza."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from shopman.storefront.concierge import service, webhook
from shopman.storefront.concierge.contracts import InboundEvent

pytestmark = pytest.mark.django_db

KEY = "manychat-test-key"
PREVIOUS_KEY = "manychat-previous-key"
CONNECTION_KEY = "manychat-whatsapp-primary"
NOW = datetime(2026, 9, 12, 15, tzinfo=UTC)
CONFIG = {
    "contract_version": 3,
    "enabled": True,
    "connections": {
        CONNECTION_KEY: {
            "active": True,
            "provider": "manychat",
            "account": "mc-account",
            "channel": "whatsapp",
            "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
            "options": {
                "authentication": {"scheme": "api_key", "keys": [KEY, PREVIOUS_KEY]},
                "pilot_prefixes": ["#concierge", "#c"],
                "response_window": {
                    "policy": "manychat-whatsapp-customer-care-24h-v1",
                    "source": "manychat_whatsapp_last_interaction",
                    "field": "provider_timestamp",
                    "timezone": "America/Sao_Paulo",
                    "authentication": "api_key",
                    "duration_seconds": 86400,
                    "purposes": ["reply", "handoff_ack"],
                },
                "stable_event_identity_verified": False,
                "handoff_field": "concierge_handoff",
            },
        }
    },
}


@pytest.fixture(autouse=True)
def configured(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = deepcopy(CONFIG)
    settings.AI_ASSIST_API_KEY = "fake"
    monkeypatch.setattr(webhook.timezone, "now", lambda: NOW)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def url():
    return reverse("concierge:connection-events", args=[CONNECTION_KEY])


@pytest.fixture
def intake(monkeypatch):
    seen: list[InboundEvent] = []

    def receive(event):
        seen.append(event)
        return SimpleNamespace(reason="queued", queued=True)

    monkeypatch.setattr(service, "receive_inbound", receive)
    return seen


def post(url, body, key=KEY, content_type="application/json"):
    return Client().post(
        url,
        data=json.dumps(body),
        content_type=content_type,
        HTTP_X_API_KEY=key,
    )


def event(**changes):
    return {
        "subscriber_id": "4685528796186498",
        "text": "#c cardápio",
        "first_name": "Pablo",
        "last_name": "Valentini",
        "provider_timestamp": "2026-09-12 11:29:01.391392",
        **changes,
    }


def test_canonical_url_has_only_connection_key(url):
    assert url == "/api/webhooks/concierge/manychat-whatsapp-primary/events/"


@pytest.mark.parametrize("key", [KEY, PREVIOUS_KEY])
def test_adapter_authenticates_rotating_key_and_view_passes_one_event(url, intake, key):
    response = post(url, event(), key)
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "queued": True}
    [normalized] = intake
    assert normalized.scope.connection_key == CONNECTION_KEY
    assert normalized.scope.provider == "manychat"
    assert normalized.scope.account == "mc-account"


def test_bare_pilot_keyword_becomes_a_real_greeting(url, intake):
    response = post(url, event(text="#c"))
    assert response.status_code == 200
    assert intake[0].text == "oi"


def test_adapter_normalizes_manychat_payload_without_inventing_event_identity(url, intake):
    response = post(url, event())
    assert response.status_code == 200
    [normalized] = intake
    assert normalized.scope.channel == "whatsapp"
    assert normalized.scope.subject == "4685528796186498"
    assert normalized.text == "cardápio"
    assert normalized.profile == {"first_name": "Pablo", "last_name": "Valentini"}
    assert normalized.event_id == ""
    assert normalized.event_identity_assurance == "unavailable"
    assert normalized.occurred_at is None
    assert normalized.window_evidence is not None


def test_verified_replay_hash_ignores_profile_and_window_metadata(url, intake, settings):
    settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"][
        "stable_event_identity_verified"
    ] = True
    first = post(url, event(event_id="provider-event-1"))
    second = post(
        url,
        event(
            event_id="provider-event-1",
            first_name="Nome atualizado",
            provider_timestamp="2026-09-12 11:30:01.391392",
        ),
    )
    assert first.status_code == second.status_code == 200
    assert len(intake) == 2
    assert intake[0].payload_hash == intake[1].payload_hash


def test_body_cannot_choose_transport_scope(url, intake):
    response = post(
        url,
        event(provider="meta", account_id="attacker", transport_channel="instagram"),
    )
    assert response.status_code == 200
    [normalized] = intake
    assert (
        normalized.scope.provider,
        normalized.scope.account,
        normalized.scope.channel,
    ) == ("manychat", "mc-account", "whatsapp")


def test_event_id_is_candidate_until_connection_gate_is_verified(url, intake):
    assert post(url, event(event_id="mc-message-1")).status_code == 200
    assert intake[0].event_id == "mc-message-1"
    assert intake[0].event_identity_assurance == "unverified"


def test_old_payload_aliases_are_not_a_second_contract(url, intake):
    body = {
        "manychat_id": "4685528796186498",
        "message": "#c",
        "first_name": "Pablo",
        "last_name": "Valentini",
        "provider_timestamp": "2026-09-12 11:29:01.391392",
    }
    response = post(url, body)
    assert response.status_code == 400
    assert response.json()["field"] == "subscriber_id"
    assert intake == []


def test_payload_hash_and_envelope_keep_window_separate_from_occurrence(url, intake):
    assert post(url, event()).status_code == 200
    envelope = intake[0].as_envelope()
    assert len(envelope["payload_hash"]) == 64
    assert envelope["occurred_at"] == ""
    assert envelope["window_evidence"]["source"] == "manychat_whatsapp_last_interaction"
    assert "provider_timestamp" not in envelope


@pytest.mark.parametrize("key", ["wrong", ""])
def test_wrong_or_missing_key_is_401(url, intake, key):
    response = post(url, event(), key)
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert intake == []


def test_missing_connection_secret_is_503(url, intake, settings):
    connection = CONFIG["connections"][CONNECTION_KEY]
    settings.SHOPMAN_CONCIERGE = {
        **CONFIG,
        "connections": {
            CONNECTION_KEY: {
                **connection,
                "options": {**connection["options"], "authentication": {"scheme": "api_key", "keys": []}},
            }
        },
    }
    assert post(url, event()).status_code == 503
    assert intake == []


def test_unknown_or_inactive_connection_is_404(settings, intake):
    unknown = reverse("concierge:connection-events", args=["unknown"])
    assert post(unknown, event()).status_code == 404
    connection = CONFIG["connections"][CONNECTION_KEY]
    settings.SHOPMAN_CONCIERGE = {
        **CONFIG,
        "connections": {CONNECTION_KEY: {**connection, "active": False}},
    }
    current = reverse("concierge:connection-events", args=[CONNECTION_KEY])
    assert post(current, event()).status_code == 404
    assert intake == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ([], ""),
        ({"text": "oi"}, "subscriber_id"),
        (event(subscriber_id=True), "subscriber_id"),
        (event(text=[]), "text"),
        (event(event_id=[]), "event_id"),
        (event(message_type="location"), "message_type"),
    ],
)
def test_invalid_payload_never_reaches_service(url, intake, body, field):
    response = post(url, body)
    assert response.status_code == 400
    assert response.json().get("field", "") == field
    assert intake == []


def test_content_type_size_depth_and_rate_limits(url, intake, monkeypatch):
    assert post(url, event(), content_type="text/plain").status_code == 415
    assert post(url, event(text="x" * 33000)).status_code == 413
    nested = {}
    for _ in range(10):
        nested = {"x": nested}
    assert post(url, event(extra=nested)).status_code == 400
    monkeypatch.setattr(webhook, "is_ratelimited", lambda **kwargs: True)
    assert post(url, event()).status_code == 429
    assert intake == []


def test_disabled_still_authenticates_before_ack(url, intake, settings):
    settings.SHOPMAN_CONCIERGE = {**CONFIG, "enabled": False}
    assert post(url, event(), key="wrong").status_code == 401
    response = post(url, event())
    assert response.json() == {"status": "disabled", "reason": "switch_off"}
    assert intake == []


def test_no_network_lookup_in_ack(url, intake, monkeypatch):
    from shopman.guestman.adapters.auth import CustomerResolver

    network = Mock(side_effect=AssertionError("network in ACK"))
    monkeypatch.setattr(CustomerResolver, "manychat_last_input_text", network)
    assert post(url, event()).status_code == 200
    network.assert_not_called()


def test_service_failure_is_sanitized(url, monkeypatch):
    monkeypatch.setattr(service, "receive_inbound", lambda event: (_ for _ in ()).throw(RuntimeError("db")))
    response = post(url, event())
    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno"}


def test_get_is_reserved_for_future_contract_and_not_accepted(url):
    assert Client().get(url, HTTP_X_API_KEY=KEY).status_code == 405
