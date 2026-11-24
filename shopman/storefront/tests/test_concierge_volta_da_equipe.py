"""OC-13: a volta da equipe à Nice (Etapa III omnicanal, DEV-2026-085).

J8 do plano: a equipe assume pelo Live Chat do ManyChat e, devolvida a conversa, a Nice
retoma relendo o domínio (sacola, pedidos, avisos), não a memória do diálogo. O ManyChat
não entrega ao Shopman o que a equipe escreve (D6), então o que a casa perguntou antes da
equipe não vale mais. Os cenários da matriz do Relatório II:

- **C08** (handoff humano e retorno da Nice: sem diálogo concorrente nem dupla execução): o
  turno que começou antes da equipe não envia depois da volta; um "sim" depois da volta não
  responde à pergunta de cancelamento de antes;
- **N19** (handoff concorrente com a Nice: posse única, comando atrasado revogado): o que o
  cliente escreveu enquanto a equipe atendia não é executado pela Nice na volta.

A volta continua atrás de ``human_return_enabled`` (desligada em produção).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, Session

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage
from shopman.shop.tests.ai_support import configure_ai
from shopman.storefront.concierge import cancellation, dialogue, service
from shopman.storefront.concierge.turn_outcome import TurnOutcome
from shopman.storefront.tests.support.concierge_transport_v3 import (
    adapter_class,
    connection,
    event,
    reset_adapter,
)
from shopman.storefront.tests.support.concierge_turn import stub_turn

pytestmark = pytest.mark.django_db

SUBJECT = "wa-subject"


@pytest.fixture(autouse=True)
def enabled(settings, monkeypatch):
    configure_ai("test-only")
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "channel_ref": "web",
        "human_return_enabled": True,
        "window_messages": 40,
        "connections": {
            "manychat-wa": connection(
                provider="manychat", account="test-account", channel="whatsapp", subjects=[SUBJECT]
            )
        },
    }
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)


def _inbound(text: str, event_id: str):
    return service.receive_inbound(event(account="test-account", subject=SUBJECT, text=text, event_id=event_id))


def _with_team(monkeypatch) -> tuple[Conversation, ConversationBinding]:
    """O cliente pede gente e a Nice passa a conversa à equipe (o turno de verdade, lido por dublê)."""
    first = _inbound("Quero falar com alguém", "event-1")
    binding = ConversationBinding.objects.get(conversation_id=first.conversation_id)
    stub_turn(monkeypatch, lambda **kwargs: TurnOutcome(reply_text="", handoff=True, handoff_reason="pedido do cliente"))
    assert service.run_turn(first.conversation_id, binding.pk).handoff
    conversation = Conversation.objects.get(pk=first.conversation_id)
    assert conversation.state == Conversation.State.HANDOFF
    return conversation, binding


def _return_note(conversation) -> ConversationMessage:
    return conversation.messages.get(kind=ConversationMessage.Kind.NOTE, envelope__kind=service.RETURN_NOTE)


def _turns(conversation) -> int:
    return Directive.objects.filter(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk).count()


def test_n19_o_que_o_cliente_escreveu_para_a_equipe_nao_e_executado_na_volta(monkeypatch):
    conversation, binding = _with_team(monkeypatch)
    # A marca do ManyChat não segurou e a fala chegou ao Shopman com a conversa na equipe:
    # ela foi ao Live Chat, e a equipe a respondeu lá.
    during = _inbound("Pode pôr mais 2 croissants", "event-2")
    assert (during.queued, during.reason) == (False, "handoff")
    Directive.objects.all().delete()
    sent_before = list(adapter_class().sent)

    assert service.return_to_concierge(conversation) is True

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE
    message = ConversationMessage.objects.get(pk=during.message_id)
    assert message.consumed_by == conversation.turn_fence, "consumida pela devolução, não por um turno da Nice"
    assert _return_note(conversation).envelope["revoked_inbound_ids"] == [during.message_id]
    assert _turns(conversation) == 0, "nenhum turno agendado para o comando de antes da volta"
    assert service.unanswered_inbound(conversation, binding) == []
    assert adapter_class().sent == sent_before, "a Nice não responde o que a equipe já respondeu"

    # A fala nova, depois da volta, é da Nice: o turno lê só ela.
    seen = []
    stub_turn(monkeypatch, lambda conversation, **kwargs: seen.append(kwargs) or TurnOutcome(reply_text="Oi! Como posso ajudar?"))
    after = _inbound("Oi, voltei", "event-3")
    assert (after.queued, after.reason) == (True, "queued")
    turn = service.run_turn(conversation.pk, binding.pk)
    assert turn.processed_message_ids == [after.message_id]
    assert adapter_class().sent[-1][2] == "Oi! Como posso ajudar?"


def test_c08_o_turno_de_antes_da_equipe_nao_envia_depois_da_volta(monkeypatch):
    """A equipe assume e devolve enquanto um turno da Nice ainda lia: ele perde a vez e nada sai."""
    first = _inbound("Quanto custa o croissant?", "event-1")
    binding = ConversationBinding.objects.get(conversation_id=first.conversation_id)

    def team_takes_and_returns_while_reading(conversation, **kwargs):
        service.mark_handoff(conversation, binding, "assumida pelo sino", notify_team=False)
        assert service.return_to_concierge(conversation) is True
        return TurnOutcome(reply_text="O croissant custa R$ 12,00.")

    stub_turn(monkeypatch, team_takes_and_returns_while_reading)
    turn = service.run_turn(first.conversation_id, binding.pk)

    assert turn.fallback == "revoked"
    assert all("croissant custa" not in text for _key, _subject, text in adapter_class().sent)
    assert not ConversationMessage.objects.filter(kind=ConversationMessage.Kind.REPLY).exists()
    conversation = Conversation.objects.get(pk=first.conversation_id)
    assert conversation.state == Conversation.State.ACTIVE
    # A pergunta foi da equipe (ela viu no Live Chat): a volta não a reabre para a Nice.
    assert _return_note(conversation).envelope["revoked_inbound_ids"] == [first.message_id]
    assert service.unanswered_inbound(conversation, binding) == []


def test_c08_um_sim_depois_da_volta_nao_cancela_o_pedido(monkeypatch):
    conversation, _binding = _with_team(monkeypatch)
    flags = dict(conversation.flags or {})
    flags[cancellation.PENDING_FLAG] = {
        "order_ref": "OC13-CANCEL", "asked_at": timezone.now().isoformat(), "request": "cancela meu pedido",
    }
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags)
    conversation.refresh_from_db()
    assert cancellation.is_pending_answer(conversation, "sim"), "a pergunta ainda estava no ar"

    assert service.return_to_concierge(conversation) is True

    conversation.refresh_from_db()
    assert cancellation.PENDING_FLAG not in conversation.flags
    assert not cancellation.is_pending_answer(conversation, "sim")


def test_a_volta_rele_o_dominio_e_nao_o_dialogo(monkeypatch):
    conversation, _binding = _with_team(monkeypatch)
    customer_ref = "CUST-OC13"
    Session.objects.create(
        session_key="oc13-cart",
        channel_ref=conversation.channel_ref,
        items=[{"sku": "CROISSANT", "name": "Croissant", "qty": 2, "unit_price_q": 1200}],
    )
    order = Order.objects.create(ref="OC13-1", channel_ref="whatsapp", total_q=2400, data={"customer_ref": customer_ref})
    # O diálogo de antes da equipe: uma lista mostrada e a pergunta "qual deles?" no ar.
    now = timezone.now()
    before = dialogue.next_state(
        {},
        [{"tool": "search_storefront", "items": [{"ref": "CROISSANT", "name": "Croissant"},
                                                 {"ref": "PAIN-CHOC", "name": "Pain au Chocolat"}]}],
        now=now, fence=1, until=now + timedelta(days=1),
    )
    assert before["pending"]["kind"] == dialogue.CHOOSE
    Conversation.objects.filter(pk=conversation.pk).update(
        customer_ref=customer_ref, session_key="oc13-cart", flags={**conversation.flags, dialogue.FLAG_KEY: before},
    )
    # Enquanto a equipe atendia, o aviso de pedido pronto saiu e a notificação o gravou (OC-10).
    ConversationMessage.objects.create(
        conversation=conversation, role=ConversationMessage.Role.ASSISTANT, kind=ConversationMessage.Kind.NOTE,
        text="Seu pedido OC13-1 está pronto para retirada.",
        envelope={"version": 3, "kind": service.ORDER_NOTICE_KIND, "order_ref": order.ref,
                  "template": "order_ready_pickup", "backend": "manychat", "approved_template": False},
    )
    conversation.refresh_from_db()

    assert service.return_to_concierge(conversation) is True

    conversation.refresh_from_db()
    memory = conversation.flags[dialogue.FLAG_KEY]
    assert memory["order"] == {"ref": order.ref, "open": True}, "o pedido aberto, relido do Orderman"
    assert memory["fence"] == conversation.turn_fence
    assert not {"pending", "listed", "focus", "last_change", "parts", "closing"} & set(memory), memory
    # "o segundo" depois da volta não escolhe da lista de antes da equipe.
    facts = dialogue.load_facts(conversation)
    assert dialogue.effective(memory, facts).get("listed") is None
    domain = _return_note(conversation).envelope["domain"]
    assert domain["session_key"] == "oc13-cart"
    assert domain["cart"] == [{"sku": "CROISSANT", "qty": "2.000"}]
    assert domain["open_order"] == {"ref": order.ref, "status": order.status}
    assert [(n["order_ref"], n["template"]) for n in domain["notices"]] == [(order.ref, "order_ready_pickup")]


def test_sem_pedido_aberto_a_memoria_do_dialogo_sai_inteira(monkeypatch):
    conversation, _binding = _with_team(monkeypatch)
    now = timezone.now()
    before = dialogue.next_state({}, [{"tool": "search_storefront", "found": False}], now=now, fence=1,
                                 until=now + timedelta(days=1))
    Conversation.objects.filter(pk=conversation.pk).update(flags={**conversation.flags, dialogue.FLAG_KEY: before})
    conversation.refresh_from_db()

    assert service.return_to_concierge(conversation) is True

    conversation.refresh_from_db()
    assert dialogue.FLAG_KEY not in conversation.flags
    assert _return_note(conversation).envelope["domain"]["open_order"] is None


def test_a_volta_sozinha_do_vou_verificar_responde_a_mensagem_nova(monkeypatch):
    """Ninguém da equipe assumiu (#2836): a fala que trouxe a conversa de volta é da Nice."""
    from shopman.storefront.concierge import verification

    conversation, binding = _with_team(monkeypatch)
    flags = dict(conversation.flags or {})
    flags[verification.FLAG_KEY] = {"v": verification.VERSION, "id": "abc", "status": verification.HANDED_OFF}
    flags["triage"] = {**(flags.get("triage") or {}), "escalated_by": verification.ESCALATED_BY}
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags)
    Directive.objects.all().delete()

    again = _inbound("E aí, conseguiu ver?", "event-2")

    assert (again.queued, again.reason) == (True, "returned")
    conversation.refresh_from_db()
    assert _return_note(conversation).envelope["revoked_inbound_ids"] == []
    assert [m.pk for m in service.unanswered_inbound(conversation, binding)] == [again.message_id]
    assert _turns(conversation) == 1


def test_sem_a_chave_a_conversa_fica_com_a_equipe(monkeypatch, settings):
    conversation, _binding = _with_team(monkeypatch)
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "human_return_enabled": False}

    assert service.return_to_concierge(conversation) is False

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert not conversation.messages.filter(envelope__kind=service.RETURN_NOTE).exists()
