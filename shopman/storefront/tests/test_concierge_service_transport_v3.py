"""Regressões do núcleo v3: conversa lógica e transportes explícitos."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive

from shopman.shop.models import (
    Conversation,
    ConversationBinding,
    ConversationMessage,
    OutboundAttempt,
)
from shopman.storefront.concierge import agent, service, transport
from shopman.storefront.concierge.contracts import HandoffOutcome, SendOutcome, WindowEvidence
from shopman.storefront.concierge.handler import ConciergeTurnHandler
from shopman.storefront.tests.support.concierge_transport_v3 import (
    adapter_class as _adapter_class,
)
from shopman.storefront.tests.support.concierge_transport_v3 import connection as _connection
from shopman.storefront.tests.support.concierge_transport_v3 import event as _event
from shopman.storefront.tests.support.concierge_transport_v3 import reset_adapter

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def concierge_v3(settings, monkeypatch):
    settings.AI_ASSIST_API_KEY = "test-only"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "human_return_enabled": True,
        "output_retry_enabled": True,
        "connections": {
            "manychat-wa": _connection(
                provider="manychat",
                account="manychat-account",
                channel="whatsapp",
                subjects=["wa-subject"],
            ),
            "tiktok-primary": _connection(
                provider="future-provider",
                account="tiktok-business",
                channel="tiktok",
                subjects=["tiktok-subject"],
            ),
        },
    }
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)


def _intake(event=None):
    result = service.receive_inbound(event or _event())
    assert result.queued, result
    binding = ConversationBinding.objects.get(conversation_id=result.conversation_id)
    return result, binding


def test_verified_ingress_persists_binding_v3_and_dedupes_within_scope():
    first, binding = _intake()
    duplicate = service.receive_inbound(_event())

    message = ConversationMessage.objects.get(pk=first.message_id)
    assert duplicate.reason == "duplicate"
    assert duplicate.message_id == first.message_id
    assert message.binding == binding
    assert message.envelope["version"] == 3
    assert message.envelope["input_assurance"] == "provider_event"
    assert message.external_id.startswith("e:")

    directive = Directive.objects.get(topic=service.TURN_TOPIC)
    assert directive.payload == {
        "conversation_id": first.conversation_id,
        "binding_id": binding.pk,
        "contract_version": 3,
    }


def test_subject_outside_connection_policy_leaves_no_persistence():
    result = service.receive_inbound(_event(subject="not-in-cohort"))
    assert result.reason == "not_allowed"
    assert not result.queued
    assert not Conversation.objects.exists()
    assert not ConversationBinding.objects.exists()


def test_string_allowlist_does_not_become_a_character_allowlist(settings):
    settings.SHOPMAN_CONCIERGE["connections"]["manychat-wa"]["options"][
        "allowed_subjects"
    ] = "wa-subject"
    result = service.receive_inbound(_event(subject="w"))
    assert result.reason == "not_allowed"
    assert not Conversation.objects.exists()


def test_tiktok_shaped_connection_uses_same_core_and_causal_binding(monkeypatch):
    result, binding = _intake(
        _event(
            key="tiktok-primary",
            provider="future-provider",
            account="tiktok-business",
            channel="tiktok",
            subject="tiktok-subject",
        )
    )
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Resposta no mesmo canal."),
    )

    turn = service.run_turn(result.conversation_id, binding.pk)

    reply = ConversationMessage.objects.get(kind=ConversationMessage.Kind.REPLY)
    attempt = reply.outbound_attempts.get()
    assert turn.processed_message_ids == [result.message_id]
    assert reply.binding == binding
    assert reply.envelope["connection_key"] == "tiktok-primary"
    assert (attempt.binding, attempt.attempt_no, attempt.state) == (binding, 1, "accepted")
    assert _adapter_class().sent == [("tiktok-primary", "tiktok-subject", "Resposta no mesmo canal.")]


def test_unverified_event_is_first_class_at_least_once_and_forces_read_only(monkeypatch):
    first, binding = _intake(_event(event_id="synthetic", assurance="unverified"))
    second = service.receive_inbound(_event(event_id="synthetic", assurance="unverified"))
    model = Mock(side_effect=AssertionError("read-only input reached the model"))
    monkeypatch.setattr(agent, "run_agent", model)

    turn = service.run_turn(first.conversation_id, binding.pk)

    inputs = list(ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND).order_by("pk"))
    assert second.reason == "queued"
    assert len(inputs) == 2
    assert all(message.external_id == "" for message in inputs)
    assert all(message.envelope["input_assurance"] == "at_least_once" for message in inputs)
    assert turn.fallback == "limited_assurance"
    assert turn.processed_message_ids == [message.pk for message in inputs]
    assert OutboundAttempt.objects.get().state == "accepted"
    model.assert_not_called()


def test_response_limits_and_window_evidence_fail_closed_without_losing_text():
    result, binding = _intake()
    conversation = binding.conversation
    inbound = ConversationMessage.objects.get(pk=result.message_id)
    oversized = "Pix: " + "a" * 4100

    row = service._send_reply(
        conversation,
        binding,
        oversized,
        window_evidence=inbound.envelope["window_evidence"],
    )
    assert row.text == oversized
    assert row.transport_state == "not_applied"
    assert row.envelope["code"] == "essential_block_too_large"
    assert _adapter_class().sent == []

    expired = WindowEvidence(
        policy="test-window-v1",
        source="authenticated-test-event",
        observed_at=timezone.now() - timedelta(hours=25),
        valid_until=timezone.now() - timedelta(hours=1),
        assurance="provider_window",
    )
    row = service._send_reply(
        conversation,
        binding,
        "Resposta preservada",
        window_evidence=expired.as_dict(),
    )
    assert row.transport_state == "not_applied"
    assert row.envelope["code"] == "window_closed"
    assert _adapter_class().sent == []


def test_persisted_binding_rejects_connection_scope_change_and_identity_claim(settings):
    result, binding = _intake()
    conversation = binding.conversation
    inbound = ConversationMessage.objects.get(pk=result.message_id)
    settings.SHOPMAN_CONCIERGE["connections"]["manychat-wa"] = {
        **settings.SHOPMAN_CONCIERGE["connections"]["manychat-wa"],
        "account": "swapped-account",
    }

    assert transport.identity_for(binding, {"whatsapp_phone": "+5543999999999"}) is None
    row = service._send_reply(
        conversation,
        binding,
        "Não pode cruzar conta",
        window_evidence=inbound.envelope["window_evidence"],
    )
    assert row.transport_state == "not_applied"
    assert row.envelope["code"] == "contained"
    assert _adapter_class().identified == []
    assert _adapter_class().sent == []


def test_same_subject_in_another_account_starts_separate_logical_conversation(settings):
    first, _ = _intake()
    settings.SHOPMAN_CONCIERGE["connections"]["manychat-secondary"] = _connection(
        provider="manychat",
        account="second-account",
        channel="whatsapp",
        subjects=["wa-subject"],
    )
    second = service.receive_inbound(_event(key="manychat-secondary", account="second-account", event_id="event-2"))
    assert second.queued
    assert first.conversation_id != second.conversation_id
    assert Conversation.objects.filter(pk__in=[first.conversation_id, second.conversation_id]).count() == 2


def test_semantic_blocks_preserve_all_characters_and_do_not_cut_lines():
    _, binding = _intake()
    text = "\n".join(f"Item {index}: " + "a" * 600 for index in range(12))
    blocks = transport.semantic_blocks(binding, text)
    assert len(blocks) > 1
    assert "".join(blocks) == text
    assert all(len(block) <= 4000 for block in blocks)
    for line in text.splitlines():
        assert sum(line in block for block in blocks) == 1


def test_late_input_revokes_the_turn_that_was_already_running(monkeypatch):
    first, binding = _intake()
    late = []

    def respond(**kwargs):
        late.append(service.receive_inbound(_event(event_id="event-2", text="Na verdade, três")))
        return agent.AgentOutcome(reply_text="Sacola consultada.")

    monkeypatch.setattr(agent, "run_agent", respond)
    turn = service.run_turn(first.conversation_id, binding.pk)

    assert turn.fallback == "revoked"
    assert turn.processed_message_ids == []
    assert turn.pending_more
    assert [message.pk for message in service.unanswered_inbound(binding.conversation, binding)] == [
        first.message_id,
        late[0].message_id,
    ]
    assert not ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY).exists()


def test_new_input_after_prepare_blocks_the_remote_send():
    first, binding = _intake()
    claimed, claimed_binding, inbound = service._claim(first.conversation_id, binding.pk)
    reply = service._prepare_reply(
        claimed,
        claimed_binding,
        "Resposta que ficou velha",
        window_evidence=inbound[0].envelope["window_evidence"],
    )
    service.receive_inbound(_event(event_id="event-2", text="Na verdade, três"))

    service._dispatch_reply(claimed, reply)

    reply.refresh_from_db()
    assert reply.transport_state == "not_applied"
    assert reply.envelope["code"] == "stale_turn"
    assert _adapter_class().sent == []


def test_message_type_drives_media_handling_instead_of_url_shape(monkeypatch):
    first, binding = _intake(_event(text="https://cdn.example/menu.jpg"))
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Link entendido como texto."),
    )
    text_turn = service.run_turn(first.conversation_id, binding.pk)
    assert text_turn.fallback == ""
    assert text_turn.replies == ["Link entendido como texto."]

    media = service.receive_inbound(
        _event(event_id="event-2", text="opaque-provider-reference", message_type="image")
    )
    monkeypatch.setattr(service, "copy_message", lambda key: f"[{key}]")
    media_turn = service.run_turn(media.conversation_id, binding.pk)
    assert media_turn.fallback == "media"
    assert media_turn.replies == ["[CONCIERGE_MEDIA_UNSUPPORTED]"]


def test_kill_switch_during_model_revokes_output_and_preserves_input(monkeypatch, settings):
    result, binding = _intake()

    def respond(**kwargs):
        settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "enabled": False}
        return agent.AgentOutcome(reply_text="Não pode sair")

    monkeypatch.setattr(agent, "run_agent", respond)
    turn = service.run_turn(result.conversation_id, binding.pk)
    inbound = ConversationMessage.objects.get(pk=result.message_id)
    assert turn.fallback == "revoked"
    assert inbound.consumed_by is None
    assert not ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY).exists()
    assert _adapter_class().sent == []


def test_non_v3_input_is_never_claimed_or_replayed(monkeypatch):
    _, binding = _intake()
    ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND).delete()
    stale = ConversationMessage.objects.create(
        conversation=binding.conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="sim",
        content=[{"type": "text", "text": "sim"}],
        envelope={"version": 2},
    )
    monkeypatch.setattr(agent, "run_agent", lambda **kwargs: pytest.fail("v2 input replayed"))
    turn = service.run_turn(binding.conversation_id, binding.pk)
    stale.refresh_from_db()
    assert turn.processed_message_ids == []
    assert stale.consumed_by is None


def test_claimed_batch_survives_small_history_window_and_caps_at_twenty(monkeypatch, settings):
    first, binding = _intake(_event(event_id="event-0", text="item 0"))
    for index in range(1, 30):
        service.receive_inbound(_event(event_id=f"event-{index}", text=f"item {index}"))
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "window_messages": 2}
    captured = []

    def respond(**kwargs):
        captured.extend(
            block["text"]
            for message in kwargs["history"]
            for block in message["content"]
            if block.get("type") == "text"
        )
        return agent.AgentOutcome(reply_text="Entradas preservadas")

    monkeypatch.setattr(agent, "run_agent", respond)
    turn = service.run_turn(first.conversation_id, binding.pk)
    expected = list(
        ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND)
        .order_by("pk")
        .values_list("pk", flat=True)[:20]
    )
    assert turn.processed_message_ids == expected
    assert captured == [f"item {index}" for index in range(20)]
    assert turn.pending_more


def test_turn_counter_resets_on_new_local_day_without_losing_input(monkeypatch):
    result, binding = _intake()
    conversation = binding.conversation
    conversation.turns_day = timezone.localdate() - timedelta(days=1)
    conversation.turns_today = 80
    conversation.save(update_fields=["turns_day", "turns_today"])
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Escolhas preservadas"),
    )
    turn = service.run_turn(result.conversation_id, binding.pk)
    conversation.refresh_from_db()
    assert conversation.turns_day == timezone.localdate()
    assert conversation.turns_today == 1
    assert turn.processed_message_ids == [result.message_id]
    assert not turn.fallback


def test_not_applied_retry_appends_attempt_and_unknown_is_never_retried(monkeypatch):
    result, binding = _intake()
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Resposta factual."),
    )
    _adapter_class().send_outcomes["manychat-wa"] = [
        SendOutcome("not_applied", "provider_rejected"),
        SendOutcome("accepted", "accepted", "receipt-retry"),
    ]

    service.run_turn(result.conversation_id, binding.pk)
    reply = ConversationMessage.objects.get(kind=ConversationMessage.Kind.REPLY)
    assert service.retry_not_applied(result.conversation_id, reply.pk)
    assert list(reply.outbound_attempts.values_list("attempt_no", "state", "code")) == [
        (1, "not_applied", "provider_rejected"),
        (2, "accepted", "accepted"),
    ]

    other_result, other_binding = _intake(_event(event_id="event-2", text="Outra"))
    _adapter_class().send_outcomes["manychat-wa"] = [SendOutcome("unknown", "acceptance_unconfirmed")]
    service.run_turn(other_result.conversation_id, other_binding.pk)
    unknown = (
        ConversationMessage.objects.filter(
            conversation_id=other_result.conversation_id,
            kind=ConversationMessage.Kind.REPLY,
        )
        .order_by("-pk")
        .first()
    )
    assert unknown is not None
    assert not service.retry_not_applied(other_result.conversation_id, unknown.pk)
    assert list(unknown.outbound_attempts.values_list("attempt_no", "state")) == [(1, "unknown")]


def test_delivery_receipts_are_monotonic_and_scoped_to_binding(monkeypatch):
    result, binding = _intake()
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text="Acompanhe por aqui."),
    )
    _adapter_class().send_outcomes["manychat-wa"] = [SendOutcome("accepted", "accepted", "provider-receipt-1")]
    service.run_turn(result.conversation_id, binding.pk)

    assert service.apply_delivery_receipt(binding, "provider-receipt-1", "delivered")
    assert service.apply_delivery_receipt(binding, "provider-receipt-1", "read")
    assert not service.apply_delivery_receipt(binding, "provider-receipt-1", "delivered")
    attempt = OutboundAttempt.objects.get(provider_receipt_ref="provider-receipt-1")
    attempt.message.refresh_from_db()
    assert attempt.state == attempt.message.transport_state == "read"

    alien_conversation = Conversation.objects.create(channel_ref="web")
    alien = ConversationBinding.objects.create(
        conversation=alien_conversation,
        provider="future-provider",
        account="tiktok-business",
        transport_channel="tiktok",
        subject="alien-subject",
        connection_key="tiktok-primary",
        status=ConversationBinding.Status.ACTIVE,
    )
    assert not service.apply_delivery_receipt(alien, "provider-receipt-1", "read")


def test_handoff_keeps_logical_ownership_when_any_active_binding_is_unknown():
    result, whatsapp = _intake(_event(text="Quero falar com alguém"))
    conversation = whatsapp.conversation
    tiktok = ConversationBinding.objects.create(
        conversation=conversation,
        provider="future-provider",
        account="tiktok-business",
        transport_channel="tiktok",
        subject="tiktok-subject",
        connection_key="tiktok-primary",
        status=ConversationBinding.Status.ACTIVE,
    )
    _adapter_class().handoff_outcomes[("tiktok-primary", True)] = HandoffOutcome("unknown", "acceptance_unconfirmed")

    turn = service.run_turn(result.conversation_id, whatsapp.pk)

    conversation.refresh_from_db()
    whatsapp.refresh_from_db()
    tiktok.refresh_from_db()
    assert turn.handoff
    assert conversation.state == Conversation.State.HANDOFF
    assert whatsapp.handoff_sync_state == "accepted"
    assert tiktok.handoff_sync_state == "unknown"
    assert set(_adapter_class().handoffs) == {
        ("manychat-wa", "wa-subject", True),
        ("tiktok-primary", "tiktok-subject", True),
    }

    _adapter_class().handoff_outcomes[("tiktok-primary", False)] = HandoffOutcome("unknown", "acceptance_unconfirmed")
    assert not service.return_to_concierge(conversation)
    conversation.refresh_from_db()
    whatsapp.refresh_from_db()
    tiktok.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert whatsapp.handoff_sync_state == "accepted"
    assert tiktok.handoff_sync_state == "unknown"
    assert set(_adapter_class().handoffs[-3:]) == {
        ("manychat-wa", "wa-subject", False),
        ("tiktok-primary", "tiktok-subject", False),
        ("manychat-wa", "wa-subject", True),
    }


def test_handler_requires_v3_binding_and_forwards_both_ids(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service,
        "run_turn",
        lambda conversation_id, binding_id: (
            calls.append((conversation_id, binding_id)) or service.TurnResult(conversation_id)
        ),
    )
    message = SimpleNamespace(payload={"contract_version": 3, "conversation_id": 41, "binding_id": 73})
    ConciergeTurnHandler().handle(message=message, ctx={})
    assert calls == [(41, 73)]

    for payload in (
        {"contract_version": 2, "conversation_id": 41, "binding_id": 73},
        {"contract_version": 3, "conversation_id": 41},
    ):
        with pytest.raises(DirectiveTerminalError):
            ConciergeTurnHandler().handle(message=SimpleNamespace(payload=payload), ctx={})
