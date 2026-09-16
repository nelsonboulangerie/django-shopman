"""C08: o mesmo núcleo funciona com bindings de canais diferentes."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, OutboundAttempt
from shopman.storefront.concierge import agent, service, transport
from shopman.storefront.concierge.contracts import WindowEvidence
from shopman.storefront.tests.support.concierge_transport_v3 import (
    ADAPTER_PATH,
    adapter_class,
    connection,
    event,
    reset_adapter,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["whatsapp", "tiktok"])
def channel(request, settings, monkeypatch):
    is_tiktok = request.param == "tiktok"
    key = "tiktok-primary" if is_tiktok else "manychat-wa"
    provider = "future-provider" if is_tiktok else "manychat"
    account = "tiktok-business" if is_tiktok else "manychat-account"
    subject = "subject:cliente-α" if is_tiktok else "123456"
    settings.AI_ASSIST_API_KEY = "test-only"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "connections": {
            key: connection(
                provider=provider,
                account=account,
                channel=request.param,
                subjects=[subject],
            )
        },
    }
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)
    return SimpleNamespace(
        key=key,
        provider=provider,
        account=account,
        transport_channel=request.param,
        subject=subject,
    )


def intake(channel, text="Olá", event_id="event-1"):
    normalized = event(
        key=channel.key,
        provider=channel.provider,
        account=channel.account,
        channel=channel.transport_channel,
        subject=channel.subject,
        text=text,
        event_id=event_id,
    )
    result = service.receive_inbound(normalized)
    assert result.queued
    binding = ConversationBinding.objects.get(conversation_id=result.conversation_id)
    return binding.conversation, binding, result.message_id


def test_core_turn_preserves_causal_inbound_and_acceptance_evidence(channel, monkeypatch):
    conversation, binding, inbound_id = intake(channel)
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Como posso ajudar?"),
    )
    result = service.run_turn(conversation.pk, binding.pk)
    inbound = ConversationMessage.objects.get(pk=inbound_id)
    reply = conversation.messages.get(kind=ConversationMessage.Kind.REPLY)
    attempt = OutboundAttempt.objects.get(message=reply)
    assert result.processed_message_ids == [inbound.pk]
    inbound.refresh_from_db()
    assert inbound.consumed_by is not None
    assert reply.binding == binding
    assert reply.transport_state == attempt.state == "accepted"
    assert adapter_class().sent == [(channel.key, channel.subject, "Como posso ajudar?")]
    conversation.refresh_from_db()
    assert conversation.phone == conversation.customer_ref == ""


def test_essential_block_is_never_truncated(channel):
    conversation, binding, inbound_id = intake(channel)
    evidence = ConversationMessage.objects.get(pk=inbound_id).envelope["window_evidence"]
    text = "Pix: " + "a" * 4100
    result = service._send_reply(conversation, binding, text, window_evidence=evidence)
    assert result.text == text
    assert result.transport_state == "not_applied"
    assert result.envelope["code"] == "essential_block_too_large"
    assert adapter_class().sent == []


def test_expired_channel_window_blocks_worker_output(channel):
    conversation, binding, _ = intake(channel)
    now = timezone.now()
    expired = WindowEvidence(
        policy="test-window-v1",
        source="authenticated-test-event",
        observed_at=now,
        valid_until=now,
        assurance="provider_window",
    )
    result = service._send_reply(
        conversation,
        binding,
        "Resposta",
        window_evidence=expired.as_dict(),
    )
    assert result.transport_state == "not_applied"
    assert result.envelope["code"] == "window_closed"
    assert adapter_class().sent == []


def test_scope_change_blocks_persisted_reference_and_identity(channel, settings):
    conversation, binding, inbound_id = intake(channel)
    connection = settings.SHOPMAN_CONCIERGE["connections"][channel.key]
    settings.SHOPMAN_CONCIERGE["connections"][channel.key] = {
        **connection,
        "account": "another-account",
        "options": {**connection["options"], "identity_link_enabled": True},
    }
    assert transport.identity_for(binding, {"whatsapp_phone": "+550000000000"}) is None
    evidence = ConversationMessage.objects.get(pk=inbound_id).envelope["window_evidence"]
    result = service._send_reply(
        conversation,
        binding,
        "Resposta de outra conta",
        window_evidence=evidence,
    )
    assert result.transport_state == "not_applied"
    assert adapter_class().identified == []
    assert adapter_class().sent == []


def test_same_subject_in_another_account_has_separate_context(channel, settings):
    first, _, _ = intake(channel)
    second_key = f"{channel.key}-secondary"
    second_account = f"{channel.account}-secondary"
    settings.SHOPMAN_CONCIERGE["connections"][second_key] = connection(
        provider=channel.provider,
        account=second_account,
        channel=channel.transport_channel,
        subjects=[channel.subject],
    )
    result = service.receive_inbound(
        event(
            key=second_key,
            provider=channel.provider,
            account=second_account,
            channel=channel.transport_channel,
            subject=channel.subject,
            event_id="event-2",
        )
    )
    second = Conversation.objects.get(pk=result.conversation_id)
    assert first.pk != second.pk
    assert first.messages.count() == second.messages.count() == 1
    assert first.customer_ref == second.customer_ref == ""


def test_human_escape_skips_model_and_acks_on_causal_binding(channel, monkeypatch):
    conversation, binding, _ = intake(channel, text="Quero falar com alguém")
    model = Mock(side_effect=AssertionError("human escape used model"))
    monkeypatch.setattr(agent, "run_agent", model)
    result = service.run_turn(conversation.pk, binding.pk)
    conversation.refresh_from_db()
    ack = conversation.messages.get(kind=ConversationMessage.Kind.REPLY)
    assert result.handoff and conversation.state == Conversation.State.HANDOFF
    assert ack.binding == binding
    assert ack.envelope["purpose"] == "handoff_ack"
    assert ack.transport_state == "accepted"
    assert adapter_class().sent == [(channel.key, channel.subject, service.copy_message("CONCIERGE_HANDOFF_ACK"))]
    model.assert_not_called()


def test_identity_gate_is_closed_even_when_profile_claims_phone(channel, settings):
    _, binding, _ = intake(channel)
    connection = settings.SHOPMAN_CONCIERGE["connections"][channel.key]
    connection["options"]["identity_link_enabled"] = False
    assert transport.identity_for(binding, {"whatsapp_phone": "+5543999999999"}) is None
    assert adapter_class().identified == []


def test_semantic_blocks_preserve_every_character_and_whole_lines(channel):
    _, binding, _ = intake(channel)
    text = "\n".join(f"Item {index}: " + "a" * 600 for index in range(12))
    blocks = transport.semantic_blocks(binding, text)
    assert len(blocks) > 1
    assert "".join(blocks) == text
    assert all(len(block) <= 4000 for block in blocks)
    for line in text.splitlines():
        assert sum(line in block for block in blocks) == 1


def test_semantic_blocks_never_cut_oversized_pix_line(channel):
    _, binding, _ = intake(channel)
    pix = "PIX" + "a" * 4500
    blocks = transport.semantic_blocks(binding, "Pedido registrado\n" + pix)
    assert blocks == ["Pedido registrado\n", pix]
    assert transport.send_for(binding, blocks[-1]).code == "essential_block_too_large"
    assert adapter_class().sent == []


def test_registry_requires_exact_binding_scope(channel):
    _, binding, _ = intake(channel)
    assert transport.adapter_for(binding) is not None
    binding.account = "payload-selected-account"
    assert transport.adapter_for(binding) is None


def test_test_adapter_path_is_explicit_and_not_a_provider_branch(channel, settings):
    assert settings.SHOPMAN_CONCIERGE["connections"][channel.key]["adapter_path"] == ADAPTER_PATH
