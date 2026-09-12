"""C02/C03/C07: consumo, certeza e contenção sem fornecedor real."""
# ruff: noqa: F811
from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service, transport
from shopman.storefront.tests.test_concierge_engine import conversation, customer, surface  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.SHOPMAN_CONCIERGE = {"enabled": True, "contract_version": 2, "account_id": "test-account", "allowed_subscribers": ["1962036908"]}
    settings.AI_ASSIST_API_KEY = "test-only"


def inbound(conversation, text="Quero pão", event="event-1"):
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())
    return Message.objects.create(conversation=conversation, role="user", kind="inbound", text=text,
                                  external_id=event, envelope={"version": 2, "event_id": event},
                                  content=[{"type": "text", "text": text}])


def test_late_input_survives_answer_and_note(conversation, monkeypatch):
    first = inbound(conversation)
    late = []
    def respond(**kw):
        late.append(inbound(conversation, "Na verdade, três", "event-2"))
        return agent.AgentOutcome(reply_text="Sacola consultada.")
    monkeypatch.setattr(agent, "run_agent", respond)
    monkeypatch.setattr(transport, "send_text", lambda *a: transport.SendOutcome("accepted"))
    result = service.run_turn(conversation.pk)
    Message.objects.create(conversation=conversation, role="assistant", kind="note", text="nota posterior")
    assert result.processed_message_ids == [first.pk]
    assert result.pending_more
    assert [m.pk for m in service.unanswered_inbound(conversation)] == [late[0].pk]


def test_prepared_before_remote_effect_and_unknown_never_retried(conversation, monkeypatch):
    inbound(conversation)
    effects = []
    monkeypatch.setattr(agent, "run_agent", lambda **kw: agent.AgentOutcome(reply_text="Resposta factual"))
    def remote(*args):
        row = conversation.messages.get(kind="reply")
        assert row.transport_state == "executing"
        effects.append(row.pk)
        raise TimeoutError("effect applied but response lost")
    monkeypatch.setattr(transport, "send_text", remote)
    service.run_turn(conversation.pk)
    row = conversation.messages.get(kind="reply")
    assert row.transport_state == "unknown" and row.delivered is None
    service.recover_pending()
    service.run_turn(conversation.pk)
    assert effects == [row.pk]


def test_pix_second_block_failure_preserves_first(conversation, monkeypatch):
    inbound(conversation)
    monkeypatch.setattr(agent, "run_agent", lambda **kw: agent.AgentOutcome(reply_text="Pedido registrado; pagamento pendente.", extra_replies=["PIX-CANONICAL"]))
    seen = []
    def remote(sid, text):
        seen.append(text)
        return transport.SendOutcome("accepted" if len(seen) == 1 else "not_applied", "provider_rejected")
    monkeypatch.setattr(transport, "send_text", remote)
    service.run_turn(conversation.pk)
    assert list(conversation.messages.filter(kind="reply").values_list("transport_state", flat=True)) == ["accepted", "not_applied"]
    service.recover_pending()
    assert len(seen) == 2


def test_kill_switch_during_model_blocks_output(conversation, monkeypatch, settings):
    first = inbound(conversation)
    def respond(**kw):
        settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "enabled": False}
        return agent.AgentOutcome(reply_text="Não pode sair")
    monkeypatch.setattr(agent, "run_agent", respond)
    monkeypatch.setattr(transport, "send_text", lambda *a: pytest.fail("output after switch off"))
    assert service.run_turn(conversation.pk).fallback == "revoked"
    first.refresh_from_db()
    assert first.consumed_by is None


def test_human_escape_without_model(conversation, monkeypatch):
    inbound(conversation, "Quero falar com alguém")
    monkeypatch.setattr(agent, "run_agent", lambda **kw: pytest.fail("human request needs no model"))
    monkeypatch.setattr(transport, "set_handoff", lambda *a: False)
    result = service.run_turn(conversation.pk)
    conversation.refresh_from_db()
    assert result.handoff and conversation.state == "handoff"
    assert conversation.handoff_sync_state == "unknown"


def test_return_failure_preserves_human_ownership(conversation, monkeypatch, settings):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "human_return_enabled": True}
    conversation.state = "handoff"
    conversation.save(update_fields=["state"])
    monkeypatch.setattr(transport, "set_handoff", lambda *a: False)
    assert service.return_to_concierge(conversation) is False
    conversation.refresh_from_db()
    assert conversation.state == "handoff"


def test_expired_window_keeps_prepared_fact_without_network(conversation, monkeypatch):
    conversation.last_inbound_at = timezone.now()-timedelta(hours=25)
    conversation.save(update_fields=["last_inbound_at"])
    monkeypatch.setattr(transport, "send_text", lambda *a: pytest.fail("expired window"))
    row = service._send_reply(conversation, "Não cortar Pix")
    assert row.transport_state == "not_applied"
    assert row.envelope["code"] == "window_closed"


def test_legacy_input_not_replayed(conversation, monkeypatch):
    Message.objects.create(conversation=conversation, role="user", kind="inbound", text="sim")
    monkeypatch.setattr(agent, "run_agent", lambda **kw: pytest.fail("legacy input replay"))
    assert not service.run_turn(conversation.pk).processed_message_ids


def test_model_cannot_invent_critical_facts(conversation, monkeypatch):
    from shopman.storefront.tests.test_concierge_engine import ScriptedClient, _response, _text
    inbound(conversation, "Quanto custa o pão?")
    sent = []
    monkeypatch.setattr(transport, "send_text", lambda sid, text: sent.append(text) or transport.SendOutcome("accepted"))
    client = ScriptedClient(_response(_text("O pão custa R$ 999,99. Sem glúten; entregue amanhã. https://evil.test"), stop_reason="end_turn"))
    service.run_turn(conversation.pk, client=client)
    assert len(sent) == 1 and "999" not in sent[0] and "evil" not in sent[0] and "glúten" not in sent[0]


def test_history_window_cannot_hide_claimed_input(conversation, monkeypatch, settings):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "window_messages": 2}
    messages = [inbound(conversation, f"item {i}", f"event-{i}") for i in range(30)]
    captured = []
    def respond(**kw):
        captured.extend(block["text"] for msg in kw["history"] for block in msg["content"] if block.get("type") == "text")
        return agent.AgentOutcome(reply_text="Entradas preservadas")
    monkeypatch.setattr(agent, "run_agent", respond)
    monkeypatch.setattr(transport, "send_text", lambda *a: transport.SendOutcome("accepted"))
    result = service.run_turn(conversation.pk)
    assert result.processed_message_ids == [m.pk for m in messages[:20]]
    assert captured == [f"item {i}" for i in range(20)]
    assert result.pending_more


def test_kill_switch_during_human_return_never_reactivates_bot(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "human_return_enabled": True}
    conversation.state = "handoff"
    conversation.save(update_fields=["state"])
    def remote(*args):
        settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "enabled": False}
        return True
    monkeypatch.setattr(transport, "set_handoff", remote)
    assert not service.return_to_concierge(conversation)
    conversation.refresh_from_db()
    assert conversation.state == "handoff" and conversation.handoff_sync_state == "routing_mismatch"


def test_turn_counter_uses_new_local_day_without_losing_input(conversation, monkeypatch):
    today = timezone.localdate()
    conversation.turns_day = today-timedelta(days=1)
    conversation.turns_today = 80
    conversation.save(update_fields=["turns_day", "turns_today"])
    message = inbound(conversation)
    monkeypatch.setattr(agent, "run_agent", lambda **kw: agent.AgentOutcome(reply_text="Escolhas preservadas"))
    monkeypatch.setattr(transport, "send_text", lambda *a: transport.SendOutcome("accepted"))
    result = service.run_turn(conversation.pk)
    conversation.refresh_from_db()
    assert conversation.turns_day == today and conversation.turns_today == 1
    assert result.processed_message_ids == [message.pk] and not result.fallback
