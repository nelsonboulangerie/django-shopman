"""As portas da Nice para o framework: canal, leitor local e posse da conversa (N4).

O que estes testes seguram:

- ``capabilities()`` do canal reflete a conexão: identidade do evento não verificada no
  alpha (``stable_event_identity_verified=false``), e o evento sai ``provider_claimed``;
- ``normalize`` nunca promove identidade (o telefone é ``transported``) e leva o texto só por
  referência (``message:<pk>``);
- o leitor local passa a checagem de forma do framework: sem modelo, custo ``Unavailable``,
  dado pessoal recusado, todo ato dentro da lista fechada;
- a posse: a sacola, o cliente e os pedidos são os da conversa do contexto confiável.
"""

from __future__ import annotations

import dataclasses

import pytest
from conversational_commerce.contracts import sha256_hash
from conversational_commerce.engine.acts import ACTS
from conversational_commerce.ports import InterpretRequest, ModelRequest, PortError, TrustedContext
from conversational_commerce.ports.channel import PreparedMessage
from conversational_commerce.testing.conformance.harness import HarnessEnv, check_capabilities, run_checks
from conversational_commerce.testing.fakes.clock import FakeClock

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage
from shopman.storefront.concierge.contracts import TransportConnection
from shopman.storefront.concierge.ports import (
    ConversationOwnership,
    LocalReader,
    NiceChannel,
    resolve_text,
    subject_of,
)
from shopman.storefront.concierge.transport import ManyChatWhatsAppAdapter

CTX = TrustedContext(tenant="nelson-boulangerie", environment="shadow", subject="conversation:1")
NOW = "2026-11-19T12:00:00.000000Z"


def channel(**options) -> NiceChannel:
    connection = TransportConnection(key="manychat-whatsapp-primary", provider="manychat", account="acc-1",
                                     channel="whatsapp", adapter_path="x", options=options)
    return NiceChannel(ManyChatWhatsAppAdapter(connection=connection))


def envelope(**extra):
    return {"version": 3, "connection_key": "manychat-whatsapp-primary", "provider": "manychat",
            "account_id": "acc-1", "transport_channel": "whatsapp", "subject": "5543999990000",
            "event_id": "mc-123", "event_identity_assurance": "unverified",
            "occurred_at": "2026-11-19T11:59:00+00:00", "message_type": "text", **extra}


def test_channel_capabilities_reflect_the_connection():
    alpha = channel(stable_event_identity_verified=False).capabilities()
    assert alpha.guarantees["stable_event_identity_verified"] is False
    assert alpha.guarantees["response_window_seconds"] == 24 * 3600 and alpha.guarantees["read_receipts"] is False
    assert set(alpha.unsupported) == {"request_handoff"}  # enviar e ler a entrega: o motor fala (22/11)
    assert channel(stable_event_identity_verified=True).capabilities().guarantees[
        "stable_event_identity_verified"] is True
    check_capabilities("channel", channel(), HarnessEnv(ctx=CTX, clock=FakeClock()))


def test_normalize_never_promotes_identity_and_carries_text_by_reference():
    event = channel(stable_event_identity_verified=False).normalize(CTX, envelope(message_ref=42), NOW)
    assert (event.tenant, event.environment) == (CTX.tenant, CTX.environment)
    assert event.event_identity.assurance == "provider_claimed" and event.event_identity.id == "mc-123"
    assert [e.assurance for e in event.identity_evidence] == ["transported"]
    assert event.content_ref == "message:42" and event.occurred_at == "2026-11-19T11:59:00.000000Z"
    verified = channel(stable_event_identity_verified=True).normalize(
        CTX, envelope(event_identity_assurance="verified"), NOW)
    assert verified.event_identity.assurance == "verified"
    anonymous = channel().normalize(CTX, envelope(event_id=""), NOW)
    assert anonymous.event_identity.assurance == "none" and anonymous.event_identity.id is None


@pytest.mark.django_db
def test_the_local_reader_passes_the_framework_shape_check():
    assert run_checks("model", LocalReader(), HarnessEnv(ctx=CTX, clock=FakeClock())) == []


@pytest.mark.parametrize(("text", "act"), [
    ("qual o horário de vocês?", "ask_hours"),
    ("quero falar com um atendente", "request_human"),
    ("meu pedido veio errado, quero reclamar", "complain"),
])
@pytest.mark.django_db
def test_the_local_reader_maps_into_the_closed_list(text, act):
    request = InterpretRequest(request=ModelRequest(purpose="interpret", data_class="redacted",
                                                    budget={"max_calls": 0, "max_spend": {
                                                        "amount_minor": 0, "currency": "BRL"}}),
                               event_id="evt-1", content_ref=f"text:{text}", allowed_acts=ACTS)
    understanding, consumption = LocalReader().interpret(CTX, request)
    names = [a.act for a in understanding.acts]
    assert act in names and set(names) <= set(ACTS)
    assert consumption.calls == 0 and consumption.cost.status == "unavailable"


@pytest.mark.django_db
def test_ownership_is_the_conversation_of_the_trusted_context():
    mine = Conversation.objects.create(session_key="sess-1", customer_ref="cust-1", phone="5543999990000")
    other = Conversation.objects.create(session_key="sess-2", customer_ref="cust-2")
    owns = ConversationOwnership()
    ctx = TrustedContext(tenant="t", environment="shadow", subject=subject_of(mine.pk))
    assert (owns.cart(ctx), owns.customer(ctx)) == ("sess-1", "cust-1")
    stranger = TrustedContext(tenant="t", environment="shadow", subject=subject_of(other.pk))
    assert owns.cart(stranger) == "sess-2"
    for subject in (None, "customer:cust-1", "conversation:x", "conversation:999999"):
        nobody = TrustedContext(tenant="t", environment="shadow", subject=subject)
        assert (owns.cart(nobody), owns.customer(nobody), owns.owns_order(nobody, "ORD-1")) == (None, None, False)


@pytest.mark.django_db
def test_text_is_resolved_on_the_shopman_side_only():
    conversation = Conversation.objects.create()
    message = ConversationMessage.objects.create(conversation=conversation, role="user", kind="note",
                                                 text="tem pão de queijo?")
    assert resolve_text(f"message:{message.pk}") == "tem pão de queijo?"
    assert resolve_text("message:999999") == "" and resolve_text("file:/etc/passwd") == ""


# ── o canal envia pelo mesmo caminho da resposta (#3198, peça 2; decisão de 22/11: o motor fala) ──


BODY_REF = "reply:plan-1"


@pytest.fixture
def live(db, monkeypatch):
    conversation = Conversation.objects.create(pk=1, phone="+5543999990000")
    binding = ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="acc-1", transport_channel="whatsapp",
        subject="5543999990000", connection_key="manychat-whatsapp-primary",
        status=ConversationBinding.Status.ACTIVE, identity_assurance="transport_subject")
    ConversationMessage.objects.create(conversation=conversation, binding=binding, role=ConversationMessage.Role.USER,
                                       kind=ConversationMessage.Kind.INBOUND, text="que horas abre?")
    dispatched = []

    def dispatch(conv, message):
        dispatched.append(message.pk)
        if message.transport_state == "prepared":
            message.transport_state = "accepted"
            message.save(update_fields=["transport_state"])
        return message

    monkeypatch.setattr("shopman.storefront.concierge.service._dispatch_reply", dispatch)
    return conversation, dispatched


def _prepared(text="Abrimos às 7h."):
    return PreparedMessage(decision_id="dec-1", content_hash=sha256_hash({"text": text}), recipient="conversation:1",
                           binding={"channel": "whatsapp", "conversation_ref": "5543999990000"}, body_ref=BODY_REF)


def test_send_goes_through_the_reply_path_and_tells_what_happened(live):
    conversation, dispatched = live
    port = dataclasses.replace(channel(), bodies={BODY_REF: "Abrimos às 7h."})
    exposure = port.send(CTX, _prepared(), "send:dec-1")
    message = conversation.messages.get(kind=ConversationMessage.Kind.REPLY)
    assert message.text == "Abrimos às 7h." and dispatched == [message.pk]
    assert message.envelope["send_key"] == "send:dec-1"  # o mesmo caminho: regras da casa, janela, envio
    assert (exposure.decision_id, exposure.state) == ("dec-1", "accepted")
    assert exposure.content_hash == sha256_hash({"text": message.text})  # o hash do que SAIU


def test_the_same_send_key_never_sends_twice(live):
    conversation, dispatched = live
    port = dataclasses.replace(channel(), bodies={BODY_REF: "Abrimos às 7h."})
    first = port.send(CTX, _prepared(), "send:dec-1")
    again = port.send(CTX, _prepared(), "send:dec-1")
    assert conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).count() == 1
    assert first.id == again.id


def test_without_the_text_nothing_is_sent(live):
    conversation, dispatched = live
    with pytest.raises(PortError) as refused:
        channel().send(CTX, _prepared(), "send:dec-1")
    assert refused.value.code.value == "invalid_content"
    assert not conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).exists() and dispatched == []


def test_delivery_status_reads_the_transport_state_of_the_same_message(live):
    conversation, _ = live
    port = dataclasses.replace(channel(), bodies={BODY_REF: "Abrimos às 7h."})
    sent = port.send(CTX, _prepared(), "send:dec-1")
    conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).update(transport_state="delivered")
    status = port.delivery_status(CTX, sent.id)
    assert (status.decision_id, status.state) == ("dec-1", "delivered")
    with pytest.raises(PortError):
        port.delivery_status(CTX, "exp-msg-999999-accepted")
