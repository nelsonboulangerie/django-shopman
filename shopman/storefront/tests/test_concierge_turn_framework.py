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


def _said(*acts):
    return SimpleNamespace(acts=tuple(SimpleNamespace(act=act) for act in acts))


@pytest.mark.parametrize(("acts", "moves", "template", "reason"), [
    # "oi" respondido com "Nós que agradecemos" é falso: o cumprimento é o de hoje.
    (("greet",), ["acknowledge"], "acknowledge.thanks", "today_answers:acknowledge.thanks"),
    (("greet", "change_quantity"), ["acknowledge", "change_cart"], "acknowledge.thanks",
     "today_answers:acknowledge.thanks"),
    # "Quer que eu chame alguém da equipe?": o "sim" não chama ninguém pelo motor.
    (("change_quantity",), ["inform_limitation"], "inform_limitation.offer_team",
     "today_answers:inform_limitation.offer_team"),
    # "Não entendi bem" a "quanto deu?", "vou pagar" e à pergunta da casa, que o caminho de hoje responde.
    (("choose_payment",), ["ask_clarification"], "ask_clarification.more", "today_answers:ask_clarification.more"),
    (("unknown",), ["ask_clarification"], "ask_clarification.more", "today_answers:ask_clarification.more"),
    # O agradecimento ao agradecimento, e o "sim" (que a sombra julga sem a pergunta do turno vivo), seguem.
    (("thank",), ["acknowledge"], "acknowledge.thanks", ""),
    (("affirm",), ["acknowledge"], "acknowledge.thanks", ""),
])
def test_an_approved_phrase_that_would_be_false_in_this_turn_goes_to_today_path(acts, moves, template, reason):
    """Calibragem do básico (23/11): a frase aprovada que, NESTE turno, mente ou não ajuda, cede ao caminho de hoje."""
    reply = SimpleNamespace(text="x", template_ids=(template,) + (("change_cart.done",) if len(moves) > 1 else ()))
    result = SimpleNamespace(chosen_moves=moves, reply=reply, understanding=_said(*acts))
    approved = frozenset({template, "change_cart.done"})
    verdict = turn_framework.judge(result, enabled=frozenset({"inform", "order"}), approved=approved)
    assert verdict.reason == reason and verdict.eligible is (not reason)


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
    "set_payment.not_offered": "Pelo WhatsApp não recebemos em dinheiro. Como você prefere pagar? {payment_method}",
    "set_delivery_address.ask_mode": "Você vai retirar aqui na loja ou prefere entrega?",
    # Os degraus de baixo dos efeitos (#3412), aprovados em 23/11.
    "change_cart.done_receipt": "{done}, a sacola foi atualizada.",
    "change_cart.done_total": "{done}, a sacola foi atualizada. Total: {total}.",  # #3488, coordenação 24/11
    "set_fulfillment.updated": "{noted}, atualizei o recebimento.",
    "commit_order.done_order": "Pedido {order} registrado. Acompanhar: {track}",
    # O endereço do cadastro (#3421): a MESMA oferta de hoje (``address.saved_offer``), e a pergunta de hoje.
    "present_terms.needs_delivery_address_saved": "Entregamos no endereço do seu cadastro, {delivery_address_saved}?",
    "present_terms.needs_delivery_address_saved_many": ("Entregamos no endereço do seu cadastro, "
                                                        "{delivery_address_saved}? Se preferir outro endereço "
                                                        "cadastrado, é só dizer qual."),
    # O quando (#3482): as perguntas de hoje do fechamento, letra por letra; o horário com as opções do dia.
    "present_terms.needs_fulfillment_date": "Para quando é o pedido? Hoje, amanhã ou outro dia (dia/mês)?",
    "present_terms.needs_fulfillment_type": "Você vai retirar aqui na loja ou prefere entrega?",
    "present_terms.needs_delivery_time_slot": "Qual horário de retirada fica melhor? {delivery_time_slot}",
    # O "outro" à oferta (#3454): a MESMA lista de hoje (``address.saved_listing``).
    "present_terms.needs_delivery_address_saved_options": ("Seus endereços cadastrados: "
                                                           "{delivery_address_saved_options}. Em qual entregamos?"),
    "present_terms.needs_delivery_address_saved_declined": ("Qual é o endereço da entrega? Pode enviar a "
                                                            "localização pelo WhatsApp ou escrever rua, número, "
                                                            "bairro e CEP."),
    # As esperas (#3328), aprovadas em 23/11.
    "effect.pending": "Ainda estou concluindo isso. Te confirmo por aqui até {deadline}.",
    "wait.overdue": "Desculpe a demora. Até {deadline}, {owner} te responde por aqui.",
    "wait.overdue_no_deadline": ("Desculpe a demora. Ainda estou esperando {owner} e te aviso por aqui "
                                 "assim que tiver a resposta."),
    # Aprovada pelo dono em 23/11 (#3408): a limitação que o efeito recusado no ar faz dizer.
    "inform_limitation.offer_team": "Isso eu não consigo fazer por aqui. Quer que eu chame alguém da equipe?",
}
REFUSED = ("ask_clarification.which", "inform.price", "cover_readings.prices")


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


def test_the_tick_stays_silent_while_a_deadline_notice_has_no_nice_phrase(shop, sent, monkeypatch):
    _switch(shop, inform=True, handoff=True)
    without = {k: v for k, v in turn_framework.NICE_TEMPLATE_COPY.items() if k != "wait.overdue"}
    monkeypatch.setattr(turn_framework, "NICE_TEMPLATE_COPY", without)
    counts = turn_framework.tick(channel=_channel())
    assert counts["skipped"] == "no_nice_template:wait.overdue" and counts["notices"] == 0
    assert sent == []  # aviso em frase genérica do pacote nunca sai


def test_every_wait_phrase_is_the_approved_one_and_the_tick_may_speak(shop):
    """#3328: as frases de espera aprovadas em 23/11, letra por letra, iguais à copy; o tick já pode falar."""
    from shopman.storefront.concierge.service import copy_message

    found = turn_framework.nice_templates()
    for template_id in ("effect.pending", "wait.overdue", "wait.overdue_no_deadline"):
        key = turn_framework.NICE_TEMPLATE_COPY[template_id]
        assert found[template_id].text == APPROVED[template_id] == copy_message(key).strip(), template_id
    assert turn_framework.tick_templates_missing() == ()


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
    # Os degraus de baixo (#3412): o efeito aconteceu, sem o que dizer depois dele. Frases aprovadas em 23/11.
    formatters = turn_framework.nice_formatters()
    assert found["set_fulfillment.updated"].text.replace("{noted}", formatters["noted"]("success")) == \
        "Combinado, atualizei o recebimento."
    assert found["change_cart.done_receipt"].text.replace("{done}", formatters["done"]("success")) == \
        "Pronto, a sacola foi atualizada."
    assert found["commit_order.done_order"].text == "Pedido {order} registrado. Acompanhar: {track}"


def test_a_window_the_house_grid_does_not_know_never_leaks(shop):
    assert turn_framework.window_text("manha") == "horário a confirmar"


def test_the_judge_reads_an_effect_turn_by_its_templates():
    from conversational_commerce.reply.verify import Finding

    def shadow(findings, *, template="set_payment.done", move="set_payment"):
        part = SimpleNamespace(move=move)
        verification = SimpleNamespace(findings=tuple(findings), parts=(part,))
        return SimpleNamespace(chosen_moves=[move], reply=SimpleNamespace(
            text=None, template_ids=(template,), verification=verification))

    outcomes = turn_framework.effect_outcomes("set_payment")
    assert {"set_payment.done", "effect.failed", "effect.pending"} <= outcomes  # o pendente tem frase (#3328)
    approved = frozenset(outcomes)
    gap = [Finding("receipt_not_in_evidence", 0, "method")]
    assert turn_framework.judge(shadow(gap), enabled=frozenset({"order"}), approved=approved).eligible
    # Um desfecho sem frase da Nice: não vai ao ar.
    without_failure = approved - {"effect.failed"}
    assert turn_framework.judge(shadow(gap), enabled=frozenset({"order"}), approved=without_failure).reason == (
        "no_nice_template:effect.failed")
    # Outro achado, que não é o que a sombra não pode ter: segura.
    other = gap + [Finding("number_without_fact", 0)]
    assert turn_framework.judge(shadow(other), enabled=frozenset({"order"}), approved=approved).reason == (
        "held:number_without_fact")


def test_the_turn_reads_ceiling_fits_a_close_with_every_effect():
    """P16 (#3482): o teto do motor conta LEITURAS, não as voltas da IA do caminho de hoje. Com 5, "pra amanhã,
    pode fechar" estourava e os termos não se apresentavam. Cabe: cotação e o que falta, os nomes de uma sacola
    grande, e cotar de novo e reler o que falta depois de cada efeito da sequência."""
    from conversational_commerce.engine.turn import EFFECT_SEQUENCE

    from shopman.storefront.concierge.profile import _max_steps

    assert _max_steps() >= 2 + 8 + 2 * len(EFFECT_SEQUENCE)
