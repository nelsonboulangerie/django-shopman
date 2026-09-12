"""C02/C03/C07: PostgreSQL independente; provider apenas fake sintético."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service, transport

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def isolated_runtime(settings, monkeypatch):
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = {"enabled": True, "contract_version": 2, "allowed_subscribers": ["synthetic-subject"], "account_id": "test-account"}
    monkeypatch.setattr(transport, "set_handoff", lambda *args: True)
    monkeypatch.setattr(transport, "send_text", lambda *args: transport.SendOutcome("accepted"))


@pytest.fixture
def conversation():
    return Conversation.objects.create(subscriber_id="synthetic-subject", account="test-account", customer_ref="synthetic-customer", last_inbound_at=timezone.now())


def inbound(conversation, text="Quero pão"):
    return Message.objects.create(conversation=conversation, role="user", kind="inbound", text=text, content=[{"type": "text", "text": text}], envelope={"version": 2, "event_id": "synthetic-event"})


def threaded(fn):
    def call():
        try:
            return fn()
        finally:
            connections.close_all()
    return call


def pg():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL independent row locks")


def test_two_workers_claim_exactly_one_turn(conversation):
    pg()
    message = inbound(conversation)
    barrier = Barrier(2)
    def claim():
        barrier.wait(timeout=10)
        return service._claim(conversation.pk)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(threaded(claim)) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(len(messages) for _, messages in results) == [0, 1]
    assert [m.pk for _, messages in results for m in messages] == [message.pk]
    conversation.refresh_from_db()
    assert conversation.turn_fence == 1


def test_expired_lease_new_claim_revokes_old_worker(conversation):
    pg()
    message = inbound(conversation)
    old, _ = service._claim(conversation.pk)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=timezone.now()-timedelta(seconds=1))
    with ThreadPoolExecutor(max_workers=1) as pool:
        current, messages = pool.submit(threaded(lambda: service._claim(conversation.pk))).result(timeout=20)
    assert current.turn_fence == old.turn_fence + 1
    assert [m.pk for m in messages] == [message.pk]
    with pytest.raises(service.TurnRevoked):
        service.assert_turn_authority(old)
    service.assert_turn_authority(current)


def test_handoff_during_model_has_no_bot_reply_or_consumption(conversation, monkeypatch):
    pg()
    message = inbound(conversation)
    started, release = Event(), Event()
    def model(**kwargs):
        started.set()
        assert release.wait(timeout=10)
        return agent.AgentOutcome(reply_text="Resposta obsoleta")
    monkeypatch.setattr(agent, "run_agent", model)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(threaded(lambda: service.run_turn(conversation.pk)))
        assert started.wait(timeout=10)
        try:
            # Se o modelo segurasse lock, esta operação não conseguiria terminar.
            service.mark_handoff(conversation, "Atendimento solicitado")
        finally:
            release.set()
        result = pending.result(timeout=20)
    message.refresh_from_db()
    conversation.refresh_from_db()
    assert result.fallback == "revoked"
    assert conversation.state == "handoff"
    assert message.consumed_by is None
    assert not conversation.messages.filter(kind="reply").exists()


def test_new_input_during_model_stays_pending_and_invalidates_mutation(conversation, monkeypatch):
    pg()
    first = inbound(conversation)
    started, release = Event(), Event()
    seen = []
    def model(**kwargs):
        seen.append(kwargs["conversation"])
        started.set()
        assert release.wait(timeout=10)
        return agent.AgentOutcome(reply_text="Resumo factual anterior")
    monkeypatch.setattr(agent, "run_agent", model)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(threaded(lambda: service.run_turn(conversation.pk)))
        assert started.wait(timeout=10)
        try:
            late = inbound(conversation, "Na verdade, três")
            with pytest.raises(service.TurnRevoked, match="new_input"):
                service.assert_turn_authority(seen[0])
        finally:
            release.set()
        result = pending.result(timeout=20)
    assert result.processed_message_ids == [first.pk]
    assert result.pending_more is True
    assert [m.pk for m in service.unanswered_inbound(conversation)] == [late.pk]


def test_provider_effect_timeout_is_unknown_and_same_block_is_not_retried(conversation, monkeypatch):
    effects = []
    def send(*args):
        effects.append(args)
        # O efeito foi observado no fake; resposta perdida não comprova entrega.
        raise TimeoutError("synthetic lost response")
    monkeypatch.setattr(transport, "send_text", send)
    message = service._prepare_reply(conversation, "Pedido registrado; consulte o pagamento.")
    service._dispatch_reply(conversation, message)
    service._dispatch_reply(conversation, message)
    message.refresh_from_db()
    assert len(effects) == 1
    assert message.transport_state == "unknown"
    assert message.delivered is None


def test_burst_after_five_loops_defers_same_directive_then_finishes(conversation, monkeypatch):
    inbound(conversation)
    calls = []
    def model(**kwargs):
        calls.append(1)
        if len(calls) <= 6:
            inbound(conversation, f"Correção {len(calls)}")
        return agent.AgentOutcome(reply_text="Contexto preservado")
    monkeypatch.setattr(agent, "run_agent", model)
    directive = Directive.objects.create(topic=service.TURN_TOPIC, payload={"conversation_id": conversation.pk, "contract_version": 2}, available_at=timezone.now()+timedelta(hours=1))
    _process_directive(directive)
    directive.refresh_from_db()
    assert len(calls) == 5
    assert directive.status == "queued"
    assert directive.attempts == 0
    assert service.unanswered_inbound(conversation)
    _process_directive(directive)
    directive.refresh_from_db()
    assert len(calls) == 7
    assert directive.status == "done"
    assert not service.unanswered_inbound(conversation)
    assert conversation.messages.filter(kind="inbound", consumed_by__isnull=False).count() == 7
    assert Directive.objects.filter(topic=service.TURN_TOPIC).count() == 1


def test_window_expired_while_queued_prevents_provider_call(conversation, monkeypatch):
    sent = []
    monkeypatch.setattr(transport, "send_text", lambda *args: sent.append(args))
    message = service._prepare_reply(conversation, "Resposta preparada")
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now()-timedelta(hours=25))
    service._dispatch_reply(conversation, message)
    message.refresh_from_db()
    assert sent == []
    assert message.transport_state == "not_applied"
    assert message.envelope["code"] == "window_closed"


def test_legacy_messages_are_not_replayed_as_new_intents(conversation):
    Message.objects.create(conversation=conversation, role="user", kind="inbound", text="sim")
    _, claimed = service._claim(conversation.pk)
    assert claimed == []


def test_removed_cohort_member_cannot_run_accepted_work(conversation, settings, monkeypatch):
    inbound(conversation)
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "allowed_subscribers": []}
    calls = []
    monkeypatch.setattr(agent, "run_agent", lambda **kwargs: calls.append(1) or agent.AgentOutcome(reply_text="Não deveria executar"))
    result = service.run_turn(conversation.pk)
    assert calls == []
    assert result.processed_message_ids == []
    assert len(service.unanswered_inbound(conversation)) == 1


@pytest.mark.parametrize("after_queue", [False, True])
def test_d02_intake_and_queue_failure_roll_back_together_and_retry_repairs(conversation, monkeypatch, after_queue):
    original = service._enqueue_turn
    def fail(current):
        if after_queue:
            original(current)
        raise RuntimeError("synthetic queue boundary failure")
    with monkeypatch.context() as patch:
        patch.setattr(service, "_enqueue_turn", fail)
        with pytest.raises(RuntimeError, match="synthetic queue"):
            service.receive_inbound(subscriber_id=conversation.subscriber_id, text="Olá", external_id="durable-event")
    assert not Message.objects.filter(conversation=conversation).exists()
    assert not Directive.objects.filter(topic=service.TURN_TOPIC).exists()
    accepted = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="Olá", external_id="durable-event")
    assert accepted.queued
    assert Message.objects.filter(conversation=conversation, kind="inbound").count() == 1
    Directive.objects.filter(topic=service.TURN_TOPIC).delete()
    replay = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="Olá", external_id="durable-event")
    assert replay.message_id == accepted.message_id and replay.queued
    assert Message.objects.filter(conversation=conversation, kind="inbound").count() == 1
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1


def test_d02_two_postgres_deliveries_accept_one_event_and_one_work(conversation):
    pg()
    barrier = Barrier(2)
    def deliver():
        barrier.wait(timeout=10)
        return service.receive_inbound(subscriber_id=conversation.subscriber_id, text="Olá", external_id="same-durable-event")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(threaded(deliver)) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert len({result.message_id for result in results}) == 1
    assert Message.objects.filter(conversation=conversation, kind="inbound").count() == 1
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1
