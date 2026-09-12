"""C02/C03/C07: PostgreSQL independente; provider apenas fake sintético."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event

import pytest
from django.db import connection as database_connection
from django.db import connections
from django.utils import timezone
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import agent, service
from shopman.storefront.concierge.contracts import WindowEvidence
from shopman.storefront.tests.support.concierge_transport_v3 import (
    adapter_class,
    connection,
    event,
    reset_adapter,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def isolated_runtime(settings, monkeypatch):
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "connections": {
            "runtime": connection(
                provider="synthetic",
                account="test-account",
                channel="text",
                subjects=["synthetic-subject"],
            )
        },
    }
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)


@pytest.fixture
def conversation():
    logical = Conversation.objects.create(
        customer_ref="synthetic-customer",
        channel_ref="web",
        last_inbound_at=timezone.now(),
    )
    ConversationBinding.objects.create(
        conversation=logical,
        provider="synthetic",
        account="test-account",
        transport_channel="text",
        subject="synthetic-subject",
        connection_key="runtime",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER,
        activated_at=timezone.now(),
    )
    return logical


def binding_for(conversation):
    return ConversationBinding.objects.get(conversation=conversation)


def inbound(conversation, text="Quero pão", event_id=None):
    binding = binding_for(conversation)
    now = timezone.now()
    return Message.objects.create(
        conversation=conversation,
        binding=binding,
        role=Message.Role.USER,
        kind=Message.Kind.INBOUND,
        text=text,
        content=[{"type": "text", "text": text}],
        external_id=event_id or "",
        envelope={
            "version": 3,
            "event_id": event_id or "",
            "input_assurance": "provider_event",
            "window_evidence": WindowEvidence(
                policy="test-window-v1",
                source="runtime-test",
                observed_at=now,
                valid_until=now + timedelta(hours=24),
                assurance="provider_window",
            ).as_dict(),
        },
    )


def normalized_event(text="Olá", event_id="durable-event"):
    return event(
        key="runtime",
        provider="synthetic",
        account="test-account",
        channel="text",
        subject="synthetic-subject",
        text=text,
        event_id=event_id,
    )


def threaded(function):
    def call():
        try:
            return function()
        finally:
            connections.close_all()

    return call


def pg():
    if database_connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL independent row locks")


def test_two_workers_claim_exactly_one_turn(conversation):
    pg()
    binding = binding_for(conversation)
    message = inbound(conversation)
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=10)
        return service._claim(conversation.pk, binding.pk)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(threaded(claim)) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(len(messages) for _, _, messages in results) == [0, 1]
    assert [item.pk for _, _, messages in results for item in messages] == [message.pk]
    conversation.refresh_from_db()
    assert conversation.turn_fence == 1


def test_expired_lease_new_claim_revokes_old_worker(conversation):
    pg()
    binding = binding_for(conversation)
    message = inbound(conversation)
    old, _, _ = service._claim(conversation.pk, binding.pk)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=timezone.now() - timedelta(seconds=1))
    with ThreadPoolExecutor(max_workers=1) as pool:
        current, _, messages = pool.submit(threaded(lambda: service._claim(conversation.pk, binding.pk))).result(
            timeout=20
        )
    assert current.turn_fence == old.turn_fence + 1
    assert [item.pk for item in messages] == [message.pk]
    with pytest.raises(service.TurnRevoked):
        service.assert_turn_authority(old)
    service.assert_turn_authority(current, for_mutation=False)


def test_handoff_during_model_has_no_bot_reply_or_consumption(conversation, monkeypatch):
    pg()
    binding = binding_for(conversation)
    message = inbound(conversation)
    started, release = Event(), Event()

    def model(**kwargs):
        started.set()
        assert release.wait(timeout=10)
        return agent.AgentOutcome(reply_text="Resposta obsoleta")

    monkeypatch.setattr(agent, "run_agent", model)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(threaded(lambda: service.run_turn(conversation.pk, binding.pk)))
        assert started.wait(timeout=10)
        try:
            service.mark_handoff(conversation, binding, "Atendimento solicitado")
        finally:
            release.set()
        result = pending.result(timeout=20)
    message.refresh_from_db()
    conversation.refresh_from_db()
    assert result.fallback == "revoked"
    assert conversation.state == Conversation.State.HANDOFF
    assert message.consumed_by is None
    assert not conversation.messages.filter(kind=Message.Kind.REPLY).exists()


def test_new_input_during_model_stays_pending_and_invalidates_mutation(conversation, monkeypatch):
    pg()
    binding = binding_for(conversation)
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
        pending = pool.submit(threaded(lambda: service.run_turn(conversation.pk, binding.pk)))
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
    assert [message.pk for message in service.unanswered_inbound(conversation, binding)] == [late.pk]


def test_provider_effect_timeout_is_unknown_and_same_block_is_not_retried(conversation):
    binding = binding_for(conversation)
    evidence = normalized_event().window_evidence.as_dict()
    adapter_class().send_outcomes["runtime"] = [TimeoutError("synthetic lost response")]
    message = service._prepare_reply(
        conversation,
        binding,
        "Pedido registrado; consulte o pagamento.",
        window_evidence=evidence,
    )
    service._dispatch_reply(conversation, message)
    service._dispatch_reply(conversation, message)
    message.refresh_from_db()
    assert len(adapter_class().sent) == 1
    assert message.transport_state == "unknown"
    assert list(message.outbound_attempts.values_list("attempt_no", "state")) == [(1, "unknown")]


def test_burst_after_five_loops_defers_same_directive_then_finishes(conversation, monkeypatch):
    binding = binding_for(conversation)
    inbound(conversation)
    calls = []

    def model(**kwargs):
        calls.append(1)
        if len(calls) <= 6:
            inbound(conversation, f"Correção {len(calls)}")
        return agent.AgentOutcome(reply_text="Contexto preservado")

    monkeypatch.setattr(agent, "run_agent", model)
    directive = Directive.objects.create(
        topic=service.TURN_TOPIC,
        payload={
            "conversation_id": conversation.pk,
            "binding_id": binding.pk,
            "contract_version": 3,
        },
        available_at=timezone.now() + timedelta(hours=1),
    )
    _process_directive(directive)
    directive.refresh_from_db()
    assert len(calls) == 5
    assert directive.status == "queued"
    assert directive.attempts == 0
    assert service.unanswered_inbound(conversation, binding)
    _process_directive(directive)
    directive.refresh_from_db()
    assert len(calls) == 7
    assert directive.status == "done"
    assert not service.unanswered_inbound(conversation, binding)
    assert conversation.messages.filter(kind=Message.Kind.INBOUND, consumed_by__isnull=False).count() == 7
    assert Directive.objects.filter(topic=service.TURN_TOPIC).count() == 1


def test_window_expired_while_queued_prevents_provider_call(conversation):
    binding = binding_for(conversation)
    now = timezone.now()
    expired = WindowEvidence(
        policy="test-window-v1",
        source="runtime-test",
        observed_at=now - timedelta(hours=25),
        valid_until=now - timedelta(hours=1),
        assurance="provider_window",
    )
    message = service._prepare_reply(
        conversation,
        binding,
        "Resposta preparada",
        window_evidence=expired.as_dict(),
    )
    service._dispatch_reply(conversation, message)
    message.refresh_from_db()
    assert adapter_class().sent == []
    assert message.transport_state == "not_applied"
    assert message.envelope["code"] == "window_closed"


def test_non_v3_messages_are_not_replayed_as_new_intents(conversation):
    binding = binding_for(conversation)
    Message.objects.create(
        conversation=conversation,
        binding=binding,
        role=Message.Role.USER,
        kind=Message.Kind.INBOUND,
        text="sim",
        envelope={"version": 2},
    )
    _, _, claimed = service._claim(conversation.pk, binding.pk)
    assert claimed == []


def test_removed_cohort_member_cannot_run_accepted_work(conversation, settings, monkeypatch):
    binding = binding_for(conversation)
    inbound(conversation)
    settings.SHOPMAN_CONCIERGE["connections"]["runtime"]["options"]["allowed_subjects"] = []
    calls = []
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: calls.append(1) or agent.AgentOutcome(reply_text="Não deveria executar"),
    )
    result = service.run_turn(conversation.pk, binding.pk)
    assert calls == []
    assert result.processed_message_ids == []
    assert len(service.unanswered_inbound(conversation, binding)) == 1


@pytest.mark.parametrize("after_queue", [False, True])
def test_d02_intake_and_queue_failure_roll_back_together_and_retry_repairs(conversation, monkeypatch, after_queue):
    binding = binding_for(conversation)
    original = service._enqueue_turn

    def fail(current, current_binding):
        if after_queue:
            original(current, current_binding)
        raise RuntimeError("synthetic queue boundary failure")

    with monkeypatch.context() as patch:
        patch.setattr(service, "_enqueue_turn", fail)
        with pytest.raises(RuntimeError, match="synthetic queue"):
            service.receive_inbound(normalized_event())
    assert not Message.objects.filter(conversation=conversation).exists()
    assert not Directive.objects.filter(topic=service.TURN_TOPIC).exists()
    accepted = service.receive_inbound(normalized_event())
    assert accepted.queued
    assert Message.objects.filter(conversation=conversation, kind=Message.Kind.INBOUND).count() == 1
    Directive.objects.filter(topic=service.TURN_TOPIC).delete()
    replay = service.receive_inbound(normalized_event())
    assert replay.message_id == accepted.message_id and replay.queued
    assert Message.objects.filter(conversation=conversation, kind=Message.Kind.INBOUND).count() == 1
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1
    assert ConversationBinding.objects.get(pk=binding.pk).status == ConversationBinding.Status.ACTIVE


def test_d02_two_postgres_deliveries_accept_one_event_and_one_work(conversation):
    pg()
    barrier = Barrier(2)

    def deliver():
        barrier.wait(timeout=10)
        return service.receive_inbound(normalized_event(event_id="same-durable-event"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(threaded(deliver)) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert len({result.message_id for result in results}) == 1
    assert Message.objects.filter(conversation=conversation, kind=Message.Kind.INBOUND).count() == 1
    assert Directive.objects.filter(topic=service.TURN_TOPIC, status="queued").count() == 1
