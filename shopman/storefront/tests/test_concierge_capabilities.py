"""C08: o mesmo núcleo funciona com dois adapters sem elevar identidade."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import agent, service, transport
from shopman.storefront.tests.support.concierge_fake import OpaqueAdapter

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["manychat", "opaque-test"])
def channel(request, settings, monkeypatch):
    fake = request.param == "opaque-test"
    subject = "subject:cliente-α" if fake else "123456"
    cfg = {
        "enabled": True,
        "contract_version": 2,
        "account_id": "isolated-account",
        "provider": request.param,
        "transport_channel": "text-only-test" if fake else "whatsapp",
        "allowed_subscribers": [subject],
        "channel_ref": "web",
    }
    if fake:
        cfg["adapter_path"] = "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter"
    settings.SHOPMAN_CONCIERGE = cfg
    settings.AI_ASSIST_API_KEY = "fake"
    sent = []
    OpaqueAdapter.sent = sent
    monkeypatch.setattr(
        transport, "send_text", lambda subject, text: sent.append((subject, text)) or transport.SendOutcome("accepted")
    )
    monkeypatch.setattr(transport, "set_handoff", lambda *args: True)
    monkeypatch.setattr(service, "_alert", lambda *args: None)
    return cfg, subject, sent


def intake(channel, text="Olá", event="event-1"):
    cfg, subject, _ = channel
    result = service.receive_inbound(subscriber_id=subject, text=text, external_id=event)
    assert result.queued
    return Conversation.objects.get(pk=result.conversation_id)


def test_core_turn_preserves_inbound_and_accepted_is_not_delivered(channel, monkeypatch):
    conversation = intake(channel)
    monkeypatch.setattr(agent, "run_agent", lambda **kw: agent.AgentOutcome(reply_text="Como posso ajudar?"))
    result = service.run_turn(conversation.pk)
    inbound = conversation.messages.get(kind=ConversationMessage.Kind.INBOUND)
    reply = conversation.messages.get(kind=ConversationMessage.Kind.REPLY)
    assert result.processed_message_ids == [inbound.pk]
    assert inbound.consumed_by is not None
    assert reply.transport_state == "accepted" and reply.delivered is None
    assert channel[2] == [(channel[1], "Como posso ajudar?")]
    conversation.refresh_from_db()
    assert conversation.phone == conversation.customer_ref == ""


def test_essential_block_is_never_truncated(channel):
    conversation = intake(channel)
    text = "Pix: " + "a" * 4100
    result = service._send_reply(conversation, text)
    assert result.text == text
    assert result.transport_state == "not_applied"
    assert result.envelope["code"] == "essential_block_too_large"
    assert channel[2] == []


def test_expired_channel_window_blocks_worker_output(channel):
    conversation = intake(channel)
    capability = transport.adapter_for(conversation).capabilities
    conversation.last_inbound_at = timezone.now() - capability.response_window - timedelta(seconds=1)
    conversation.save(update_fields=["last_inbound_at"])
    result = service._send_reply(conversation, "Resposta")
    assert result.transport_state == "not_applied"
    assert channel[2] == []


def test_scope_change_blocks_persisted_reference_and_identity(channel, settings, monkeypatch):
    conversation = intake(channel)
    resolver = Mock(side_effect=AssertionError("cross-account identity"))
    monkeypatch.setattr(transport.ManyChatAdapter, "identify", resolver)
    settings.SHOPMAN_CONCIERGE = {**channel[0], "account_id": "another-account", "identity_link_enabled": True}
    assert transport.identity_for(conversation, {"whatsapp_phone": "+550000000000"}) is None
    result = service._send_reply(conversation, "Resposta de outra conta")
    assert result.transport_state == "not_applied"
    resolver.assert_not_called()
    assert channel[2] == []


def test_same_subject_in_another_account_has_separate_context(channel, settings):
    first = intake(channel)
    settings.SHOPMAN_CONCIERGE = {**channel[0], "account_id": "another-account"}
    second = intake(channel)
    assert first.pk != second.pk
    assert first.messages.count() == second.messages.count() == 1
    assert first.customer_ref == second.customer_ref == ""


def test_human_escape_does_not_require_supported_remote_handoff(channel, monkeypatch):
    conversation = intake(channel, text="Quero falar com alguém")
    model = Mock(side_effect=AssertionError("human escape used model"))
    monkeypatch.setattr(agent, "run_agent", model)
    result = service.run_turn(conversation.pk)
    conversation.refresh_from_db()
    assert result.handoff and conversation.state == Conversation.State.HANDOFF
    assert channel[2] == [(channel[1], service.copy_message("CONCIERGE_HANDOFF_ACK"))]
    ack = conversation.messages.get(kind=ConversationMessage.Kind.REPLY)
    assert ack.envelope["purpose"] == "handoff_ack"
    assert ack.transport_state == "accepted"
    model.assert_not_called()
    if channel[0]["provider"] == "opaque-test":
        assert conversation.handoff_sync_state == "unknown"


def test_identity_gate_is_closed_even_when_payload_claims_phone(channel, monkeypatch):
    conversation = intake(channel)
    resolver = Mock(side_effect=AssertionError("identity not authorized"))
    monkeypatch.setattr(transport.ManyChatAdapter, "identify", resolver)
    assert transport.identity_for(conversation, {"whatsapp_phone": "+5543999999999"}) is None
    resolver.assert_not_called()


def test_manychat_identity_does_not_trust_profile_claim(channel, settings, monkeypatch):
    conversation = intake(channel)
    from shopman.guestman.adapters.auth import CustomerResolver

    resolver = Mock(return_value=None)
    monkeypatch.setattr(CustomerResolver, "upsert_manychat_subscriber", resolver)
    settings.SHOPMAN_CONCIERGE = {**channel[0], "identity_link_enabled": True}
    assert transport.identity_for(conversation, {"whatsapp_phone": "+5543999999999"}) is None
    if channel[0]["provider"] == "manychat":
        resolver.assert_called_once_with({"id": channel[1]})
    else:
        resolver.assert_not_called()


def test_unidentified_subject_cannot_consult_purchase_receipt(channel, monkeypatch):
    from shopman.shop.services import remote_mutations
    from shopman.storefront.concierge import tools

    conversation = intake(channel)
    lookup = Mock(side_effect=AssertionError("receipt consulted before identity"))
    monkeypatch.setattr(remote_mutations, "lookup_local_mutation", lookup)
    result = tools.place_order(tools.ToolContext(conversation, "web"), "known-token", "pix")
    assert not result["ok"] and result["error"] == "identity_required"
    lookup.assert_not_called()


def test_account_swapped_reference_cannot_consult_receipt(channel, settings, monkeypatch):
    from shopman.shop.services import remote_mutations
    from shopman.storefront.concierge import tools

    conversation = intake(channel)
    settings.SHOPMAN_CONCIERGE = {**channel[0], "account_id": "other-account"}
    lookup = Mock(side_effect=AssertionError("cross-account receipt consulted"))
    monkeypatch.setattr(remote_mutations, "lookup_local_mutation", lookup)
    result = tools.place_order(tools.ToolContext(conversation, "web"), "known-token", "pix")
    assert not result["ok"] and result["error"] == "authority_unavailable"
    lookup.assert_not_called()


def test_semantic_blocks_preserve_every_character_and_whole_lines(channel):
    conversation = intake(channel)
    text = "\n".join(f"Item {i}: " + "a" * 600 for i in range(12))
    blocks = transport.semantic_blocks(conversation, text)
    assert len(blocks) > 1
    assert "".join(blocks) == text
    assert all(len(block) <= 4000 for block in blocks)
    for line in text.splitlines():
        assert sum(line in block for block in blocks) == 1


def test_semantic_blocks_never_cut_oversized_pix_line(channel):
    conversation = intake(channel)
    pix = "PIX" + "a" * 4500
    blocks = transport.semantic_blocks(conversation, "Pedido registrado\n" + pix)
    assert blocks == ["Pedido registrado\n", pix]
    assert transport.send_for(conversation, blocks[-1]).code == "essential_block_too_large"
    assert channel[2] == []
