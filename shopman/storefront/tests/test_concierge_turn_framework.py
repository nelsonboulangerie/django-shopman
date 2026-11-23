"""O turno da Nice pelo motor do framework, atrás da chave e por classe (N9a, #3199).

A decisão de 22/11/2026: o motor fala, mas só onde a casa tem a frase de hoje; o resto segue o
caminho de hoje, nunca uma frase genérica. A chave é da loja, por classe, e nasce desligada.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.models import ConversationalEpisode, ConversationBinding, ConversationMessage, Shop
from shopman.storefront.concierge import turn_framework
from shopman.storefront.concierge.contracts import TransportConnection
from shopman.storefront.concierge.ports import NiceChannel
from shopman.storefront.concierge.service import copy_message
from shopman.storefront.concierge.transport import ManyChatWhatsAppAdapter

pytestmark = pytest.mark.django_db


def _channel():
    connection = TransportConnection(key="manychat-whatsapp-primary", provider="manychat", account="acc-1",
                                     channel="whatsapp", adapter_path="x", options={})
    return NiceChannel(ManyChatWhatsAppAdapter(connection=connection))


@pytest.fixture
def shop(db):
    from shopman.shop.models import Channel

    # O canal de venda do WhatsApp materializado, como no descritor da instância.
    Channel.objects.create(ref="whatsapp", name="WhatsApp", config={
        "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
        "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
        "notifications": {"backend": "manychat"},
    })
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def sent(monkeypatch):
    """O envio de verdade é o ``_dispatch_reply``; aqui ele só marca aceito e anota."""
    out = []

    def dispatch(conv, message):
        if message.transport_state == "prepared":
            message.transport_state = "accepted"
            message.save(update_fields=["transport_state"])
            out.append(message.text)
        return message

    monkeypatch.setattr("shopman.storefront.concierge.service._dispatch_reply", dispatch)
    return out


def _inbound(text):
    from shopman.shop.models import Conversation

    conversation = Conversation.objects.create(phone="+5543999990000", channel_ref="whatsapp")
    binding = ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="acc-1", transport_channel="whatsapp",
        subject="5543999990000", connection_key="manychat-whatsapp-primary",
        status=ConversationBinding.Status.ACTIVE, identity_assurance="transport_subject")
    message = ConversationMessage.objects.create(
        conversation=conversation, binding=binding, role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND, text=text,
        envelope={"version": 3, "connection_key": "manychat-whatsapp-primary", "provider": "manychat",
                  "account_id": "acc-1", "transport_channel": "whatsapp", "subject": "5543999990000",
                  "event_id": f"mc-{text[:8]}", "event_identity_assurance": "unverified",
                  "occurred_at": "2026-11-22T11:59:00+00:00", "message_type": "text"})
    return conversation, message


def _switch(shop, **classes):
    for name, on in classes.items():
        setattr(shop, turn_framework.SWITCH_FIELD[name], on)
    shop.save()


def test_with_every_class_off_nothing_runs_and_nothing_is_written(shop, sent):
    conversation, message = _inbound("obrigada!")
    assert turn_framework.run(conversation, message, channel=_channel()) is None
    assert not ConversationalEpisode.objects.exists() and sent == []


def test_a_thank_you_goes_through_the_engine_in_the_nice_phrase(shop, sent):
    _switch(shop, inform=True)
    conversation, message = _inbound("obrigada!")
    result = turn_framework.run(conversation, message, channel=_channel())
    assert result is not None and result.chosen_moves == ["acknowledge"]
    assert result.reply.template_ids == ("acknowledge.thanks",)
    assert sent == [copy_message("CONCIERGE_SMALL_TALK_THANKS").strip()]  # a frase de hoje, pelo envio de hoje


def test_a_question_without_a_nice_phrase_stays_on_today_path(shop, sent):
    _switch(shop, inform=True)
    conversation, message = _inbound("qual o horário de vocês?")
    assert turn_framework.run(conversation, message, channel=_channel()) is None
    assert sent == []  # nenhuma frase genérica do pacote sai


def test_a_class_switched_off_stays_on_today_path(shop, sent):
    _switch(shop, handoff=True)
    conversation, message = _inbound("obrigada!")
    assert turn_framework.run(conversation, message, channel=_channel()) is None
    assert sent == []


def test_a_failure_never_breaks_the_turn(shop, sent, monkeypatch):
    _switch(shop, inform=True)
    conversation, message = _inbound("obrigada!")
    monkeypatch.setattr(turn_framework, "build_engine", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert turn_framework.run(conversation, message, channel=_channel()) is None


def test_the_judge_needs_a_switched_on_class_and_a_nice_template_for_every_part():
    reply = SimpleNamespace(text="Oi", template_ids=("acknowledge.thanks", "inform.hours"))
    result = SimpleNamespace(chosen_moves=["acknowledge", "inform"], reply=reply)
    approved = frozenset({"acknowledge.thanks"})
    assert turn_framework.judge(result, enabled=frozenset({"handoff"}), approved=approved).reason.startswith("class_off")
    assert turn_framework.judge(result, enabled=frozenset({"inform"}), approved=approved).reason == (
        "no_nice_template:inform.hours")
    ok = SimpleNamespace(chosen_moves=["acknowledge"], reply=SimpleNamespace(text="Oi", template_ids=("acknowledge.thanks",)))
    assert turn_framework.judge(ok, enabled=frozenset({"inform"}), approved=approved).eligible


APPROVED = {  # prévia frase a frase de 22/11/2026: "sim" do dono (#3298)
    "ask_clarification.more": "Desculpe, não entendi bem. Pode me dizer o que você gostaria?",
    "effect.failed": ("Não consegui concluir esta ação. Suas escolhas foram preservadas. "
                      "Se quiser, chamo alguém da equipe."),
    "handoff.routed": ("Solicitei atendimento a {owner} e preservei suas escolhas. "
                       "Se ninguém assumir até {deadline}, te aviso por aqui."),
    "handoff.routed_no_deadline": ("Solicitei atendimento a {owner} e preservei suas escolhas. "
                                   "A equipe continuará por aqui conforme a disponibilidade."),
    "handoff.not_accepted": ("Solicitei atendimento humano e preservei suas escolhas. Enquanto ninguém "
                             "assume, sigo com você por aqui e te dou notícia até {deadline}."),
    # Aprovadas pelo dono em 23/11, no cartão do motor. O "total mudou" substitui o "não" de 22/11
    # (a frase de antes pedia o código).
    "present_terms.changed": "O total mudou; agora é {total}. Confira antes de confirmar.",
    "commit_order.done": "Pedido {order} registrado. Total: {total}.\nAcompanhar: {track}",
    "change_cart.done": ("{done}, sua sacola ficou assim:\n{items}\nTotal: {total}\nQuer mais alguma coisa? "
                         "Quando terminar, é só escrever “pode fechar”."),
    "present_terms.confirm": "{items}\nTotal: {total}\n{fulfillment}{conditions}\nPosso registrar?",
    "acknowledge.terms_declined": ("Tudo bem, fica sem pedido por agora. Os itens continuam na sacola, "
                                   "se mudar de ideia."),
    # Cartão 5 (pagamento), aprovadas pelo dono em 23/11: a pergunta de hoje e o "Combinado".
    "set_payment.done": "Combinado: {method}.",
    "present_terms.needs_payment_method": "Como você prefere pagar? {payment_method}",
    # Cartão 2 (entrega): as perguntas de hoje e o "Combinado" aprovado em 23/11.
    "set_delivery_address.done": "Combinado: entrega na {address}.",
    "present_terms.needs_delivery_address": ("Qual é o endereço da entrega? Pode enviar a localização pelo "
                                             "WhatsApp ou escrever rua, número, bairro e CEP."),
    "present_terms.needs_delivery_address_details": "Para a entrega, me diga {delivery_address_details}.",
    "set_delivery_address.not_delivered": ("Esse endereço está fora da nossa área de entrega. Qual é o endereço da "
                                           "entrega? Pode enviar a localização pelo WhatsApp ou escrever rua, "
                                           "número, bairro e CEP."),
    "set_delivery_address.not_located": ("Não consegui localizar esse endereço para calcular a entrega. Confira a "
                                         "rua, o número e o bairro, ou envie sua localização pelo WhatsApp."),
    "present_terms.needs_delivery_complement": ("Tem complemento (apartamento, bloco, fundos)? Se não tiver, "
                                                "é só dizer \"sem complemento\"."),
}
REFUSED = ("ask_clarification.which", "inform.price", "cover_readings.prices", "inform_limitation.offer_team")


def test_the_nice_templates_are_the_approved_phrases_and_a_broken_copy_drops_out(shop, monkeypatch):
    found = turn_framework.nice_templates()
    assert set(found) == {"acknowledge.got_it", "acknowledge.thanks", *APPROVED, *turn_framework.FULFILLMENT_TEMPLATES}
    assert found["acknowledge.thanks"].text == copy_message("CONCIERGE_SMALL_TALK_THANKS").strip()
    for template_id, text in APPROVED.items():
        assert found[template_id].text == text, template_id  # a frase aprovada, letra por letra
    assert not set(REFUSED) & set(found)  # o "não" do dono: a classe fica com a frase de hoje
    monkeypatch.setattr("shopman.storefront.concierge.service.copy_message",
                        lambda key: "Fechamos às 19h." if key == "CONCIERGE_SMALL_TALK_THANKS" else "Combinado.")
    assert "acknowledge.thanks" not in turn_framework.nice_templates()  # dígito no texto fixo: fora


def test_who_answers_and_until_when_are_said_in_portuguese(settings):
    from datetime import UTC, datetime, timedelta

    from django.utils import timezone

    assert turn_framework.owner_text("operator_on_duty") == "alguém da equipe"  # nunca o nome do papel
    now = timezone.localtime()
    tomorrow = (now + timedelta(days=1)).replace(hour=7, minute=10, second=0, microsecond=0)
    assert turn_framework.deadline_text(tomorrow.isoformat()) == "amanhã às 7h10"
    today = now.replace(hour=15, minute=0, second=0, microsecond=0)
    assert turn_framework.deadline_text(today.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")) == "hoje às 15h"
    later = datetime(2030, 3, 4, 9, 0, tzinfo=timezone.get_current_timezone())
    assert turn_framework.deadline_text(later.isoformat()) == "04/03 às 9h"


def test_the_tick_does_nothing_with_the_classes_off(shop, sent):
    assert turn_framework.tick(channel=_channel())["skipped"] == "classes_off"
    assert sent == []


def test_the_tick_stays_silent_while_the_deadline_notice_has_no_nice_phrase(shop, sent):
    _switch(shop, inform=True, handoff=True)
    counts = turn_framework.tick(channel=_channel())
    # Todo molde de espera (``effect.pending`` também é ``wait``) precisa da frase da Nice antes.
    assert counts["skipped"].startswith("no_nice_template:") and "wait.overdue" in counts["skipped"]
    assert counts["notices"] == 0
    assert sent == []  # aviso em frase genérica do pacote nunca sai


def test_the_engine_tick_command_runs_in_the_worker(shop):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("concierge_engine_tick", stdout=out)
    assert '"skipped": "classes_off"' in out.getvalue()


# ── os moldes do pedido com a frase de hoje (passo 4 do pedido pelo motor) ────────────────


def test_the_order_templates_are_today_phrases(shop):
    from datetime import timedelta

    from django.utils import timezone

    from shopman.storefront.concierge import order_closing
    found = turn_framework.nice_templates()
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    formatters = turn_framework.nice_formatters()

    def say(template_id, **values):
        text = found[template_id].text
        for slot, value in values.items():
            text = text.replace("{" + slot + "}", formatters[slot](value))
        return text

    today_with_window = order_closing.noted({"day": tomorrow, "kind": "pickup", "slot": "A partir das 15h"},
                                            copy=copy_message)
    today_without = order_closing.noted({"day": tomorrow, "kind": "delivery", "slot": ""}, copy=copy_message)
    assert say("set_fulfillment.done", mode="pickup", date=tomorrow, window="slot-15") == today_with_window \
        == "Combinado: retirada amanhã, a partir das 15h."
    assert say("set_fulfillment.done_day", mode="delivery", date=tomorrow) == today_without \
        == "Combinado: entrega amanhã."
    assert say("set_fulfillment.done_date", date=tomorrow) == "Combinado: para amanhã."
    assert say("set_fulfillment.done_mode", mode="delivery") == "Combinado: entrega."
    # A hora sem janela da grade: derivada das aprovadas (coordenação, 23/11).
    assert say("set_fulfillment.done_time", mode="pickup", date=tomorrow, time="16:00") == \
        "Combinado: retirada amanhã às 16h."
    assert turn_framework.time_text("16:30") == "16h30"
    # O que não tem frase de hoje fica fora: o turno segue o caminho de hoje (a hora sem janela, o resumo,
    # o "total mudou" com o total, a sacola e o pedido registrado esperam a palavra do dono).
    for missing in ("set_fulfillment.updated",):
        assert missing not in found, missing


def test_a_window_the_house_grid_does_not_know_never_leaks(shop):
    assert turn_framework.window_text("manha") == "horário a confirmar"
