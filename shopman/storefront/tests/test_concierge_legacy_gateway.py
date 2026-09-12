"""C01: compatibilidade legada explícita, leitura/humano sem identidade inventada."""

import json
from unittest.mock import Mock

import pytest
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order, Session

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service, tools, transport

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gateway(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 2,
        "account_id": "legacy-test-account",
        "api_key": "existing-test-key",
        "allowed_subscribers": ["123"],
        "legacy_read_handoff_enabled": True,
        "channel_ref": "web",
    }
    settings.AI_ASSIST_API_KEY = "fake"
    model = Mock(side_effect=AssertionError("legacy input reached model"))
    identify = Mock(side_effect=AssertionError("legacy input promoted identity"))
    monkeypatch.setattr(agent, "run_agent", model)
    monkeypatch.setattr(service, "identify", identify)
    monkeypatch.setattr(service, "_alert", lambda *args: None)
    sent = []
    monkeypatch.setattr(
        transport, "send_text", lambda subject, text: sent.append(text) or transport.SendOutcome("accepted")
    )
    monkeypatch.setattr(transport, "set_handoff", lambda *args: True)
    yield sent
    model.assert_not_called()
    identify.assert_not_called()


def post(client, text="#c oi", event_id=None):
    body = {"subscriber_id": "123", "text": text, "first_name": "Cliente", "last_name": "Teste"}
    if event_id is not None:
        body["event_id"] = event_id
    return client.post(
        reverse("concierge:manychat-conversation"),
        json.dumps(body),
        content_type="application/json",
        HTTP_X_API_KEY="existing-test-key",
    )


@pytest.fixture
def catalog():
    from shopman.storefront.tests.test_concierge_engine import surface

    return surface.__wrapped__()


def test_legacy_receipts_are_distinct_without_fabricated_event_identity(client):
    for _ in range(2):
        response = post(client)
        assert response.status_code == 200
        assert response.json() == {"status": "legacy_read_only", "queued": True}
    receipts = list(Message.objects.order_by("pk"))
    assert len(receipts) == 2 and receipts[0].pk != receipts[1].pk
    assert all(m.external_id == "" and m.envelope.get("event_id") == "" for m in receipts)
    assert all(m.envelope["input_assurance"] == "legacy_unverified" for m in receipts)
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1
    assert not Session.objects.exists() and not Order.objects.exists()


def test_flag_off_preserves_missing_event_containment(client, settings):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "legacy_read_handoff_enabled": False}
    response = post(client)
    assert response.json() == {"status": "event_id_required", "queued": False}
    assert not Conversation.objects.exists() and not Message.objects.exists()
    assert not Directive.objects.exists()


@pytest.mark.parametrize("menu_text", ["#c cardápio", "#menu NB-SYNTHETIC"])
def test_menu_uses_real_canonical_catalog_without_model_or_identity(client, catalog, gateway, monkeypatch, menu_text):
    from shopman.doorman.services.access_link import AccessLinkService

    forbidden = Mock(side_effect=AssertionError("menu consumed or created access token"))
    for method in ("create_token", "exchange", "send_access_link", "create_and_send"):
        monkeypatch.setattr(AccessLinkService, method, forbidden)
    monkeypatch.setattr(tools, "send_web_link", forbidden)
    assert post(client, menu_text).json()["queued"]
    conversation = Conversation.objects.get()
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada, fixture sintética
    result = service.run_turn(conversation.pk)
    receipt = conversation.messages.get(kind="inbound")
    receipt.refresh_from_db()
    assert receipt.consumed_by is not None
    assert receipt.text == ("cardápio" if menu_text == "#c cardápio" else menu_text)
    forbidden.assert_not_called()
    assert result.processed_message_ids == [receipt.pk]
    assert gateway and "R$ 0,90" in "\n".join(gateway)
    assert "Pão Francês" in "\n".join(gateway)
    assert not Session.objects.exists() and not Order.objects.exists()
    conversation.refresh_from_db()
    assert conversation.consecutive_failures == 0
    assert conversation.phone == conversation.customer_ref == ""
    assert conversation.quote == {}


def test_purchase_text_only_guides_without_mutation(client, gateway):
    post(client, "#c quero dois pães e confirmo a compra")
    conversation = Conversation.objects.get()
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada
    service.run_turn(conversation.pk)
    assert gateway
    assert not Session.objects.exists() and not Order.objects.exists()
    assert not conversation.messages.exclude(envelope__quote_token="").filter(envelope__has_key="quote_token").exists()


def test_direct_mutation_cannot_use_legacy_claim(client, catalog):
    post(client, "#c quero dois pães")
    conversation, inbound = service._claim(Conversation.objects.get().pk)
    assert inbound
    result = tools.set_item(tools.ToolContext(conversation, "web"), "PAO-FRANCES", 2)
    assert not result["ok"]
    assert not Session.objects.exists() and not Order.objects.exists()


def test_human_escape_preserves_context_and_contains_bot(client, gateway):
    post(client, "#c quero falar com alguém")
    conversation = Conversation.objects.get()
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada, fixture sintética
    result = service.run_turn(conversation.pk)
    conversation.refresh_from_db()
    assert result.handoff and conversation.state == Conversation.State.HANDOFF
    assert conversation.messages.get(kind="inbound").consumed_by is not None
    assert gateway == [service.copy_message("CONCIERGE_HANDOFF_ACK")]
    assert not Session.objects.exists() and not Order.objects.exists()


def test_legacy_and_verified_batch_remains_read_only(client, gateway):
    post(client, "#c quero dois pães")
    post(client, "confirmo", event_id="real-stable-event")
    conversation = Conversation.objects.get()
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada, fixture sintética
    result = service.run_turn(conversation.pk)
    assert len(result.processed_message_ids) == 2
    assert gateway
    assert not Session.objects.exists() and not Order.objects.exists()
    conversation.refresh_from_db()
    assert conversation.quote == {}


def test_legacy_confirmation_never_becomes_authorization_in_later_turn(client):
    post(client, "#c quero dois pães")
    conversation = Conversation.objects.get()
    service.run_turn(conversation.pk)
    offered = Message.objects.create(
        conversation=conversation,
        kind="reply",
        role="assistant",
        text="Revisão",
        transport_state="accepted",
        envelope={"version": 2, "quote_token": "review-token"},
    )
    post(client, "confirmo")
    service.run_turn(conversation.pk)
    legacy = conversation.messages.filter(kind="inbound", pk__gt=offered.pk).get()
    assert legacy.consumed_by is not None
    assert tools._confirmation(tools.ToolContext(conversation, "web"), "review-token") is None
    post(client, "confirmo", event_id="later-stable-event")
    assert tools._confirmation(tools.ToolContext(conversation, "web"), "review-token") is None
    assert not Order.objects.exists()


def test_revoking_legacy_capability_after_intake_blocks_processing(client, settings, gateway):
    post(client, "#c quero dois pães")
    conversation = Conversation.objects.get()
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "legacy_read_handoff_enabled": False}
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada
    service.run_turn(conversation.pk)
    assert gateway == []
    assert conversation.messages.get(kind="inbound").consumed_by is None
    assert not Session.objects.exists() and not Order.objects.exists()


def test_gate_revoked_between_prepare_and_dispatch_prevents_send(client, settings, gateway):
    post(client, "#c quero dois pães")
    conversation, inbound = service._claim(Conversation.objects.get().pk)
    assert inbound and conversation._legacy_read_only
    prepared = service._prepare_reply(conversation, "Orientação de leitura")
    assert prepared.envelope["legacy_read_only"]
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "legacy_read_handoff_enabled": False}
    service._dispatch_reply(conversation, prepared)
    prepared.refresh_from_db()
    assert prepared.transport_state == "not_applied"
    assert prepared.envelope["code"] == "contained"
    assert gateway == []


def test_legacy_batch_unknown_is_not_retried(client, catalog, monkeypatch):
    for _ in range(3):
        assert post(client, "#menu NB-SYNTHETIC").json()["queued"]
    conversation = Conversation.objects.get()
    attempts = []

    def remote_timeout(subject, text):
        attempts.append(text)
        raise TimeoutError("synthetic possible provider acceptance")

    monkeypatch.setattr(transport, "send_text", remote_timeout)
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada, fixture sintética
    result = service.run_turn(conversation.pk)
    replies = list(conversation.messages.filter(kind="reply").order_by("pk"))
    assert len(result.processed_message_ids) == 3
    assert replies
    assert len(attempts) == 1
    assert replies[0].transport_state == "unknown"
    assert all(message.transport_state == "not_applied" for message in replies[1:])
    assert all(not message.envelope.get("quote_token") for message in replies)
    service.recover_pending()
    service.run_turn(conversation.pk)
    replies[0].refresh_from_db()
    assert replies[0].transport_state == "unknown"
    assert len(attempts) == 1
    assert not service.unanswered_inbound(conversation)
    assert not Order.objects.exists() and not Session.objects.exists()


def test_reloaded_conversation_does_not_lose_legacy_mutation_containment(client, catalog):
    post(client, "#c quero dois pães")
    conversation = Conversation.objects.get()
    for consumed in (False, True):
        if consumed:
            service.run_turn(conversation.pk)
        reloaded = Conversation.objects.get(pk=conversation.pk)
        result = tools.set_item(tools.ToolContext(reloaded, "web"), "PAO-FRANCES", 2)
        assert not result["ok"]
        assert not Session.objects.exists() and not Order.objects.exists()


def test_revocation_parks_legacy_without_requeue_or_blocking_verified_input(client, settings):
    post(client, "#c quero dois pães")
    conversation = Conversation.objects.get()
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "legacy_read_handoff_enabled": False}
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())  # janela previamente verificada, fixture sintética
    result = service.run_turn(conversation.pk)
    assert not result.pending_more
    assert service.recover_pending()["queued"] == 0
    assert conversation.messages.get(kind="inbound").consumed_by is None
    post(client, "consulta nova", event_id="new-verified-input")
    claimed, inbound = service._claim(conversation.pk)
    assert [m.envelope["event_id"] for m in inbound] == ["new-verified-input"]
    assert not claimed._legacy_read_only


def test_legacy_receipt_never_opens_or_renews_transport_window(client, gateway):
    from datetime import timedelta

    post(client, "#menu NB-SYNTHETIC")
    conversation = Conversation.objects.get()
    assert conversation.last_inbound_at is None
    assert not transport.response_allowed(conversation, timezone.now())
    expired = timezone.now() - timedelta(hours=25)
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=expired)
    post(client, "#menu NB-SYNTHETIC")
    conversation.refresh_from_db()
    assert conversation.last_inbound_at == expired
    assert not transport.response_allowed(conversation, timezone.now())
    service.run_turn(conversation.pk)
    assert gateway == []
    assert conversation.messages.filter(kind="reply", transport_state="not_applied", envelope__code="window_closed").exists()


def test_read_only_release_contains_even_verified_event_and_reloaded_tool(client, settings, catalog, gateway):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "read_only": True}
    post(client, "#c quero dois pães", event_id="stable-test-event")
    conversation = Conversation.objects.get()
    result = service.run_turn(conversation.pk)
    assert result.processed_message_ids
    assert gateway
    reloaded = Conversation.objects.get(pk=conversation.pk)
    command = tools.set_item(tools.ToolContext(reloaded, "web"), "PAO-FRANCES", 2)
    assert not command["ok"]
    assert not Session.objects.exists() and not Order.objects.exists()
