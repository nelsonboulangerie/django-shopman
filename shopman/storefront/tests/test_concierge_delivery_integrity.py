"""C02/C03/C07: consumo, certeza e contenção sem fornecedor real."""
# ruff: noqa: F811

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, OutboundAttempt
from shopman.shop.tests.ai_support import configure_ai
from shopman.storefront.concierge import intents, service
from shopman.storefront.concierge.contracts import HandoffOutcome, SendOutcome, WindowEvidence
from shopman.storefront.concierge.turn_outcome import TurnOutcome, current_customer_text
from shopman.storefront.tests.support.concierge_transport_v3 import (
    adapter_class,
    connection,
    event,
    reset_adapter,
)
from shopman.storefront.tests.support.concierge_turn import stub_turn
from shopman.storefront.tests.test_concierge_engine import (
    surface,  # noqa: F401
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings, monkeypatch):
    configure_ai("test-only")
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "human_return_enabled": True,
        "output_retry_enabled": True,
        "window_messages": 40,
        "connections": {
            "manychat-wa": connection(
                provider="manychat",
                account="test-account",
                channel="whatsapp",
                subjects=["wa-subject"],
            )
        },
    }
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)


def inbound(text="Quero pão", event_id="event-1"):
    result = service.receive_inbound(event(account="test-account", subject="wa-subject", text=text, event_id=event_id))
    assert result.queued
    binding = ConversationBinding.objects.get(conversation_id=result.conversation_id)
    return result, binding, ConversationMessage.objects.get(pk=result.message_id)


def test_late_input_revokes_stale_answer_and_replays_the_whole_context(monkeypatch):
    first, binding, first_message = inbound()
    late = []

    def respond(**kwargs):
        late.append(inbound("Na verdade, três", "event-2")[2])
        return TurnOutcome(reply_text="Sacola consultada.")

    stub_turn(monkeypatch, respond)
    result = service.run_turn(first.conversation_id, binding.pk)
    assert result.fallback == "revoked"
    assert result.processed_message_ids == []
    assert result.pending_more
    assert [message.pk for message in service.unanswered_inbound(binding.conversation, binding)] == [
        first_message.pk,
        late[0].pk,
    ]
    assert not ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY).exists()

    stub_turn(
        monkeypatch,
        lambda **kwargs: TurnOutcome(reply_text="Entendi a correção para três."),
    )
    replay = service.run_turn(first.conversation_id, binding.pk)
    assert replay.processed_message_ids == [first_message.pk, late[0].pk]
    assert [message.text for message in ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY)] == [
        "Entendi a correção para três."
    ]


def test_prepared_attempt_exists_before_remote_effect_and_unknown_is_not_retried(monkeypatch):
    result, binding, _ = inbound()
    effects = []
    stub_turn(
        monkeypatch,
        lambda **kwargs: TurnOutcome(reply_text="Resposta factual"),
    )

    def remote(subject, text):
        row = ConversationMessage.objects.get(kind=ConversationMessage.Kind.REPLY)
        attempt = row.outbound_attempts.get()
        assert row.transport_state == attempt.state == "executing"
        effects.append(row.pk)
        raise TimeoutError("effect applied but response lost")

    adapter_class().send_outcomes["manychat-wa"] = [remote]
    service.run_turn(result.conversation_id, binding.pk)
    row = ConversationMessage.objects.get(kind=ConversationMessage.Kind.REPLY)
    assert row.transport_state == "unknown"
    assert list(row.outbound_attempts.values_list("attempt_no", "state")) == [(1, "unknown")]
    service.recover_pending()
    service.run_turn(result.conversation_id, binding.pk)
    assert effects == [row.pk]


def test_pix_second_block_failure_preserves_first(monkeypatch):
    result, binding, _ = inbound()
    stub_turn(
        monkeypatch,
        lambda **kwargs: TurnOutcome(
            reply_text="Pedido registrado; pagamento pendente.",
            extra_replies=["PIX-CANONICAL"],
            # O recibo do pedido (regra da casa R6: "registrado" só com pedido).
            order_ref="ORD-TEST-1",
        ),
    )
    adapter_class().send_outcomes["manychat-wa"] = [
        SendOutcome("accepted", "accepted", "receipt-first"),
        SendOutcome("not_applied", "provider_rejected"),
    ]
    service.run_turn(result.conversation_id, binding.pk)
    replies = list(ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY).order_by("pk"))
    assert [reply.transport_state for reply in replies] == ["accepted", "not_applied"]
    assert [attempt.attempt_no for attempt in OutboundAttempt.objects.order_by("pk")] == [1, 1]
    service.recover_pending()
    assert len(adapter_class().sent) == 2


def test_extra_reply_uses_the_same_semantic_fragmentation(monkeypatch):
    result, binding, _ = inbound()
    extra = "a" * 2500 + "\n" + "b" * 2500
    stub_turn(
        monkeypatch,
        lambda **kwargs: TurnOutcome(reply_text="Resumo", extra_replies=[extra]),
    )

    turn = service.run_turn(result.conversation_id, binding.pk)

    assert len(turn.replies) == 3
    assert "".join(turn.replies[1:]) == extra
    assert all(len(text) <= 4000 for text in turn.replies)


def test_kill_switch_during_model_blocks_output_and_preserves_input(monkeypatch, settings):
    result, binding, message = inbound()

    def respond(**kwargs):
        settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "enabled": False}
        return TurnOutcome(reply_text="Não pode sair")

    stub_turn(monkeypatch, respond)
    assert service.run_turn(result.conversation_id, binding.pk).fallback == "revoked"
    message.refresh_from_db()
    assert message.consumed_by is None
    assert adapter_class().sent == []


def test_human_escape_without_model_preserves_local_human_ownership(monkeypatch):
    result, binding, _ = inbound("Quero falar com alguém")
    monkeypatch.setattr(intents, "read_with_model", lambda *a, **k: pytest.fail("human request used model"))
    adapter_class().handoff_outcomes[("manychat-wa", True)] = HandoffOutcome("unknown", "acceptance_unconfirmed")
    turn = service.run_turn(result.conversation_id, binding.pk)
    binding.conversation.refresh_from_db()
    binding.refresh_from_db()
    assert turn.handoff
    assert binding.conversation.state == Conversation.State.HANDOFF
    assert binding.handoff_sync_state == "unknown"


def test_return_failure_preserves_human_ownership():
    _, binding, _ = inbound()
    conversation = binding.conversation
    conversation.state = Conversation.State.HANDOFF
    conversation.save(update_fields=["state"])
    adapter_class().handoff_outcomes[("manychat-wa", False)] = HandoffOutcome("unknown", "acceptance_unconfirmed")
    assert service.return_to_concierge(conversation) is False
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF


def test_expired_window_keeps_prepared_fact_without_network():
    _, binding, _ = inbound()
    now = timezone.now()
    expired = WindowEvidence(
        policy="test-window-v1",
        source="authenticated-test-event",
        observed_at=now - timedelta(hours=25),
        valid_until=now - timedelta(hours=1),
        assurance="provider_window",
    )
    row = service._send_reply(
        binding.conversation,
        binding,
        "Não cortar Pix",
        window_evidence=expired.as_dict(),
    )
    assert row.text == "Não cortar Pix"
    assert row.transport_state == "not_applied"
    assert row.envelope["code"] == "window_closed"
    assert adapter_class().sent == []


def test_non_v3_input_is_not_replayed(monkeypatch):
    _, binding, original = inbound()
    original.delete()
    stale = ConversationMessage.objects.create(
        conversation=binding.conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="sim",
        content=[{"type": "text", "text": "sim"}],
        envelope={"version": 2},
    )
    stub_turn(monkeypatch, lambda **kwargs: pytest.fail("v2 input replayed"))
    turn = service.run_turn(binding.conversation_id, binding.pk)
    stale.refresh_from_db()
    assert not turn.processed_message_ids
    assert stale.consumed_by is None


def test_model_cannot_invent_critical_facts(surface):  # noqa: ARG001
    from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act

    result, binding, _ = inbound("Quanto custa o pão? e entrega amanhã?")
    # A leitura só separa partes: o que ela "diz" não vira resposta; quem responde é o executor.
    reader = ReaderClient([
        _act("product_question", "O pão custa R$ 999,99. Sem glúten. https://evil.test", "pão"),
        _act("hours_delivery", "entregue amanhã"),
    ])
    service.run_turn(result.conversation_id, binding.pk, intents_client=reader)
    assert len(adapter_class().sent) == 1
    sent = adapter_class().sent[0][2]
    assert "999" not in sent and "evil" not in sent and "glúten" not in sent


def test_the_turn_reads_every_claimed_input(monkeypatch, settings):
    result, binding, _ = inbound("item 0", "event-0")
    for index in range(1, 30):
        inbound(f"item {index}", f"event-{index}")
    captured = []

    def respond(**kwargs):
        # O turno lê o que o claim cobriu, inteiro: é o texto que as partes recebem.
        captured.extend(current_customer_text(kwargs["conversation"]).split("\n"))
        return TurnOutcome(reply_text="Entradas preservadas")

    stub_turn(monkeypatch, respond)
    turn = service.run_turn(result.conversation_id, binding.pk)
    messages = list(ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND).order_by("pk"))
    assert turn.processed_message_ids == [message.pk for message in messages[:20]]
    assert captured == [f"item {index}" for index in range(20)]
    assert turn.pending_more


def test_kill_switch_during_human_return_never_reactivates_bot(settings):
    _, binding, _ = inbound()
    conversation = binding.conversation
    conversation.state = Conversation.State.HANDOFF
    conversation.save(update_fields=["state"])

    def remote(subject, on):
        settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "enabled": False}
        return HandoffOutcome("accepted", "accepted")

    adapter_class().handoff_outcomes[("manychat-wa", False)] = remote
    assert not service.return_to_concierge(conversation)
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert adapter_class().handoffs[-2:] == [
        ("manychat-wa", "wa-subject", False),
        ("manychat-wa", "wa-subject", True),
    ]


def test_turn_counter_uses_new_local_day_without_losing_input(monkeypatch):
    result, binding, message = inbound()
    conversation = binding.conversation
    today = timezone.localdate()
    conversation.turns_day = today - timedelta(days=1)
    conversation.turns_today = 80
    conversation.save(update_fields=["turns_day", "turns_today"])
    stub_turn(
        monkeypatch,
        lambda **kwargs: TurnOutcome(reply_text="Escolhas preservadas"),
    )
    turn = service.run_turn(result.conversation_id, binding.pk)
    conversation.refresh_from_db()
    assert conversation.turns_day == today and conversation.turns_today == 1
    assert turn.processed_message_ids == [message.pk] and not turn.fallback


def test_a_message_while_with_the_team_never_falls_into_silence(monkeypatch):
    """O fornecedor mandou ao bot uma mensagem de conversa que está com a equipe.

    Medido em 19/11/2026: a marca de atendimento humano do ManyChat voltou a 0 fora daqui,
    a conversa seguia em HANDOFF, e a mensagem do cliente era gravada e mais nada. Agora a
    marca volta a ser ligada (a próxima vai ao Live Chat) e o sino diz que ele escreveu.
    A posse continua da equipe: nada de turno da Concierge.
    """
    result, binding, _ = inbound("Quero falar com alguém")
    Conversation.objects.filter(pk=result.conversation_id).update(state=Conversation.State.HANDOFF)
    alerts = []
    monkeypatch.setattr(service, "_alert", lambda conversation, kind, message: alerts.append((kind, message)))
    reset_adapter()

    again = service.receive_inbound(
        event(account="test-account", subject="wa-subject", text="Oi? Alguém aí?", event_id="event-2")
    )

    assert (again.queued, again.reason) == (False, "handoff")
    assert adapter_class().handoffs == [("manychat-wa", "wa-subject", True)]
    # A fala nova, entre aspas; título e "há N min" saem da projeção.
    assert alerts == [("concierge_handoff", "“Oi? Alguém aí?”")]
    binding.refresh_from_db()
    assert binding.handoff_sync_state == "accepted"
    assert Conversation.objects.get(pk=result.conversation_id).state == Conversation.State.HANDOFF
    assert not adapter_class().sent  # a Concierge não responde

    # A mesma entrada de novo (retry do fornecedor) não liga a marca nem o cartão outra vez.
    service.receive_inbound(event(account="test-account", subject="wa-subject", text="Oi? Alguém aí?", event_id="event-2"))
    assert len(adapter_class().handoffs) == 1 and len(alerts) == 1


def _with_team(conversation_id, *, verification_status, escalated_by):
    """A conversa na equipe, como o prazo do "vou verificar" (ou o "Assumir" do sino) a deixa."""
    from shopman.storefront.concierge import verification

    conversation = Conversation.objects.get(pk=conversation_id)
    flags = dict(conversation.flags or {})
    flags[verification.FLAG_KEY] = {"v": verification.VERSION, "id": "abc", "status": verification_status}
    flags["triage"] = {**(flags.get("triage") or {}), "escalated_by": escalated_by}
    Conversation.objects.filter(pk=conversation_id).update(state=Conversation.State.HANDOFF, flags=flags)


def test_after_the_verification_deadline_a_new_message_returns_to_the_concierge(monkeypatch):
    """Dono, 20/11/2026 (#2836, "1"): foi à equipe só pelo prazo do "vou verificar" e o
    cliente escreveu de novo: volta à Concierge, a marca do ManyChat vai a 0 e o turno roda."""
    from shopman.orderman.models import Directive

    from shopman.storefront.concierge import verification

    result, binding, _ = inbound("Quero falar com alguém")
    _with_team(result.conversation_id, verification_status=verification.HANDED_OFF,
               escalated_by=verification.ESCALATED_BY)
    reset_adapter()
    Directive.objects.all().delete()

    again = service.receive_inbound(
        event(account="test-account", subject="wa-subject", text="E aí, conseguiu ver?", event_id="event-2")
    )

    assert (again.queued, again.reason) == (True, "returned")
    conversation = Conversation.objects.get(pk=result.conversation_id)
    assert conversation.state == Conversation.State.ACTIVE
    assert adapter_class().handoffs == [("manychat-wa", "wa-subject", False)]
    assert Directive.objects.filter(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk).exists()
    assert conversation.flags[verification.FLAG_KEY]["status"] == verification.RETURNED


def test_a_conversation_taken_over_from_the_bell_never_returns_by_itself(monkeypatch):
    from shopman.storefront.concierge import verification

    result, _binding, _ = inbound("Quero falar com alguém")
    _with_team(result.conversation_id, verification_status=verification.TAKEN_OVER, escalated_by="")
    reset_adapter()

    again = service.receive_inbound(
        event(account="test-account", subject="wa-subject", text="Oi?", event_id="event-2")
    )

    assert (again.queued, again.reason) == (False, "handoff")
    assert Conversation.objects.get(pk=result.conversation_id).state == Conversation.State.HANDOFF
    assert adapter_class().handoffs == [("manychat-wa", "wa-subject", True)]  # a marca religada, como antes


def test_without_the_return_switch_the_deadline_conversation_stays_with_the_team(settings):
    from shopman.storefront.concierge import verification

    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "human_return_enabled": False}
    result, _binding, _ = inbound("Quero falar com alguém")
    _with_team(result.conversation_id, verification_status=verification.HANDED_OFF,
               escalated_by=verification.ESCALATED_BY)
    reset_adapter()

    again = service.receive_inbound(
        event(account="test-account", subject="wa-subject", text="E aí?", event_id="event-2")
    )

    assert (again.queued, again.reason) == (False, "handoff")
    assert Conversation.objects.get(pk=result.conversation_id).state == Conversation.State.HANDOFF
