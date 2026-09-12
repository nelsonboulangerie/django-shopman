"""A janela WhatsApp autoriza resposta de leitura sem autoridade comercial."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.urls import reverse
from shopman.orderman.models import Order, Session

from shopman.shop.models import Conversation, ConversationBinding, OutboundAttempt
from shopman.storefront.concierge import service, tools, transport, webhook
from shopman.storefront.concierge.contracts import HandoffOutcome, SendOutcome
from shopman.storefront.tests.test_concierge_engine import surface as surface_fixture

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 9, 12, 15, tzinfo=UTC)
KEY = "existing-test-key"
CONNECTION_KEY = "manychat-whatsapp-window"
SUBJECT = "123"
WINDOW = {
    "policy": "manychat-whatsapp-customer-care-24h-v1",
    "source": "manychat_whatsapp_last_interaction",
    "field": "provider_timestamp",
    "timezone": "America/Sao_Paulo",
    "authentication": "api_key",
    "duration_seconds": 86400,
    "purposes": ["reply", "handoff_ack"],
}
CONFIG = {
    "contract_version": 3,
    "enabled": True,
    "channel_ref": "web",
    "connections": {
        CONNECTION_KEY: {
            "active": True,
            "provider": "manychat",
            "account": "window-account",
            "channel": "whatsapp",
            "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
            "options": {
                "authentication": {"scheme": "api_key", "keys": [KEY]},
                "allowed_subjects": [SUBJECT],
                "pilot_prefixes": ["#c"],
                "response_window": WINDOW,
                "stable_event_identity_verified": False,
                "handoff_field": "concierge_handoff",
            },
        }
    },
}


@pytest.fixture(autouse=True)
def configured(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONFIG
    settings.AI_ASSIST_API_KEY = "fake"
    monkeypatch.setattr(service.timezone, "now", lambda: NOW)
    monkeypatch.setattr(webhook.timezone, "now", lambda: NOW)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def catalog():
    return surface_fixture.__wrapped__()


@pytest.fixture
def gateway(monkeypatch):
    sent: list[str] = []

    def send(binding, text):
        sent.append(text)
        return SendOutcome("accepted", "accepted", f"window-send-{len(sent)}")

    monkeypatch.setattr(transport, "send_for", send)
    return sent


def post(client, at, **extra):
    body = {
        "subscriber_id": SUBJECT,
        "text": "#c cardápio",
        "provider_timestamp": at,
        **extra,
    }
    return client.post(
        reverse("concierge:connection-events", args=[CONNECTION_KEY]),
        json.dumps(body),
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
    )


def local(at):
    return at.astimezone(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None).isoformat(sep=" ")


def binding_for(conversation):
    return ConversationBinding.objects.get(conversation=conversation)


def evidence_for(conversation):
    return [
        message.envelope.get("window_evidence")
        for message in conversation.messages.filter(kind="inbound").order_by("pk")
        if message.envelope.get("window_evidence")
    ]


def set_window_config(settings, **changes):
    connection = CONFIG["connections"][CONNECTION_KEY]
    settings.SHOPMAN_CONCIERGE = {
        **CONFIG,
        "connections": {
            CONNECTION_KEY: {
                **connection,
                "options": {
                    **connection["options"],
                    "response_window": {**WINDOW, **changes},
                },
            }
        },
    }


def test_live_field_opens_read_reply_without_identity_or_purchase(client, catalog, gateway):
    assert post(client, "2026-09-12 11:29:01.391392").json() == {
        "status": "queued",
        "queued": True,
    }
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    receipt = conversation.messages.get()
    evidence = receipt.envelope["window_evidence"]
    assert evidence["observed_at"] == "2026-09-12T14:29:01.391392+00:00"
    assert receipt.envelope["input_assurance"] == "at_least_once"
    assert receipt.external_id == receipt.envelope["event_id"] == ""
    assert receipt.envelope["occurred_at"] == ""
    assert conversation.last_inbound_at == NOW
    assert transport.response_authorization(binding, evidence, NOW).allowed

    result = service.run_turn(conversation.pk, binding.pk)

    assert result.fallback == "limited_assurance"
    assert gateway and "Pão Francês" in "\n".join(gateway)
    assert OutboundAttempt.objects.get().state == "accepted"
    reloaded = Conversation.objects.get(pk=conversation.pk)
    assert not tools.set_item(tools.ToolContext(reloaded, "web"), "PAO-FRANCES", 2)["ok"]
    assert not Session.objects.exists() and not Order.objects.exists()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not a date",
        "2026-09-12",
        "2026-02-31 11:29:01",
        "2026-09-11 11:29:01.391392",
        "2026-09-12 12:00:00.000001",
        "2026-09-11 12:00:00",
    ],
)
def test_invalid_future_or_expired_field_cannot_open_window(client, gateway, value):
    assert post(client, value).json()["queued"]
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    assert evidence_for(conversation) == []
    assert not transport.response_authorization(binding, None, NOW).allowed

    service.run_turn(conversation.pk, binding.pk)

    assert not gateway
    attempt = OutboundAttempt.objects.get()
    assert attempt.state == "not_applied" and attempt.code == "window_evidence_missing"


def test_queue_expiry_and_replay_do_not_renew_window(client, gateway, monkeypatch):
    original = NOW - timedelta(hours=23, minutes=59)
    post(client, local(original))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    [evidence] = evidence_for(conversation)
    assert transport.response_authorization(binding, evidence, NOW).allowed

    later = NOW + timedelta(minutes=1)
    monkeypatch.setattr(service.timezone, "now", lambda: later)
    monkeypatch.setattr(webhook.timezone, "now", lambda: later)
    post(client, local(original))
    assert not transport.response_authorization(binding, evidence, later).allowed

    service.run_turn(conversation.pk, binding.pk)

    assert not gateway
    assert conversation.messages.filter(kind="inbound").count() == 2
    assert OutboundAttempt.objects.get().state == "not_applied"


def test_out_of_order_does_not_shorten_existing_window(client):
    post(client, local(NOW - timedelta(minutes=10)))
    post(client, local(NOW - timedelta(hours=23)))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    inbound = list(conversation.messages.filter(kind="inbound").order_by("pk"))

    evidence = service._best_window_evidence(binding, inbound)

    assert evidence["observed_at"] == (NOW - timedelta(minutes=10)).isoformat()
    assert transport.response_authorization(
        binding, evidence, NOW + timedelta(hours=2)
    ).allowed


def test_handoff_ack_uses_best_consumed_window_evidence(client, gateway, monkeypatch):
    post(client, local(NOW - timedelta(minutes=10)))
    post(client, local(NOW - timedelta(hours=23)))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    inbound = list(conversation.messages.filter(kind="inbound").order_by("pk"))
    monkeypatch.setattr(
        transport,
        "handoff_for",
        lambda *_args, **_kwargs: HandoffOutcome("accepted", "accepted"),
    )
    monkeypatch.setattr(service, "copy_message", lambda _key: "Equipe avisada.")

    assert service.mark_handoff(
        conversation,
        binding,
        "pedido do cliente",
        consumed_ids=[message.pk for message in inbound],
    )

    reply = conversation.messages.get(kind="reply")
    assert reply.envelope["window_evidence"]["observed_at"] == (
        NOW - timedelta(minutes=10)
    ).isoformat()
    assert gateway == ["Equipe avisada."]


def test_revocation_after_prepare_contains_send(client, settings, gateway):
    post(client, local(NOW))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    claimed, claimed_binding, inbound = service._claim(conversation.pk, binding.pk)
    prepared = service._prepare_reply(
        claimed,
        claimed_binding,
        "Cardápio",
        window_evidence=inbound[0].envelope["window_evidence"],
    )
    set_window_config(settings, timezone="")

    service._dispatch_reply(claimed, prepared)

    prepared.refresh_from_db()
    assert prepared.transport_state == "not_applied"
    assert prepared.envelope["code"] == "window_policy_unconfigured"
    assert OutboundAttempt.objects.get(message=prepared).state == "not_applied"
    assert not gateway


@pytest.mark.parametrize("zone", ["", "Invalid/Zone"])
def test_no_implicit_timezone_or_historical_backfill(client, settings, zone):
    set_window_config(settings, timezone=zone)
    post(client, local(NOW))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    assert evidence_for(conversation) == []
    assert not transport.response_authorization(binding, None, NOW).allowed

    set_window_config(settings, timezone="America/Sao_Paulo")

    assert evidence_for(conversation) == []
    assert not transport.response_authorization(binding, None, NOW).allowed


@pytest.mark.parametrize(
    "changed",
    [
        {"authentication": ""},
        {"account_id": "other"},
        {"provider": "other"},
        {"transport_channel": "instagram"},
    ],
)
def test_field_requires_authenticated_account_and_whatsapp(settings, changed):
    connection = transport.connection_for_key(CONNECTION_KEY)
    adapter = transport.adapter_for_connection(connection)
    envelope = {
        "authentication": "api_key",
        "account_id": "window-account",
        "provider": "manychat",
        "transport_channel": "whatsapp",
        "provider_timestamp": local(NOW),
        **changed,
    }
    assert adapter.window_evidence(envelope, NOW) is None


@pytest.mark.parametrize("stamp", ["2026-09-12T15:00:00Z", "2026-09-12T12:00:00-03:00"])
def test_explicit_offset_is_not_applied_twice(client, stamp):
    post(client, stamp)
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    [evidence] = evidence_for(conversation)
    assert evidence["observed_at"] == NOW.isoformat()
    assert transport.response_authorization(binding, evidence, NOW).allowed


def test_connection_gate_revocation_revokes_window_source(client, settings):
    post(client, local(NOW))
    conversation = Conversation.objects.get()
    binding = binding_for(conversation)
    [evidence] = evidence_for(conversation)
    assert transport.response_authorization(binding, evidence, NOW).allowed
    connection = CONFIG["connections"][CONNECTION_KEY]
    settings.SHOPMAN_CONCIERGE = {
        **CONFIG,
        "connections": {CONNECTION_KEY: {**connection, "active": False}},
    }
    assert not transport.response_authorization(binding, evidence, NOW).allowed
