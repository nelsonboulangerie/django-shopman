# ruff: noqa: F811  (as fixtures do motor entram por import, como nos vizinhos)
"""Regras da casa (OBS0310-M, ``concierge/house_rules.py``): a tabela e cada regra provada.

Três camadas de prova:

1. **A tabela**: 14 regras, cada uma com quando, o que exige, o efeito e quem executa;
   toda regra de entrada e de saída tem exemplos que disparam e que não podem disparar.
2. **Cada regra pelos próprios exemplos** (parametrizado a partir da tabela: regra nova
   sem exemplo reprova aqui).
3. **O turno inteiro**: a resposta montada pelo sistema também passa pela tabela; o que
   ela segura não sai, a conversa vai para a equipe e o aviso de handoff é verdade.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import house_rules, service
from shopman.storefront.concierge.house_rules import (
    CART,
    ENTRY,
    HANDOFF,
    HOUSE,
    MODEL,
    ORDER,
    OUTPUT,
    RULES,
    RULES_BY_ID,
    SEND,
    TEAM_NOTIFIED,
    Effect,
    ReplyContext,
)
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    CONCIERGE_SETTINGS,
    ScriptedClient,
    _binding,
    _receive,
    _turn,
    alpha_menu,
    conversation,
    customer,
    outbox,
    surface,
)

# ── 1. A tabela ───────────────────────────────────────────────────────


def test_the_table_has_the_fourteen_rules_of_v2_in_order():
    assert [rule.id for rule in RULES] == [f"R{n}" for n in range(1, 15)]


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.id)
def test_every_rule_is_declared_in_full(rule):
    assert rule.title and rule.when and rule.demands and rule.enforced_by
    assert rule.stages and set(rule.stages) <= {ENTRY, OUTPUT, SEND}
    assert rule.on_violation and set(rule.on_violation) <= {HOUSE, MODEL}
    if OUTPUT in rule.stages:
        assert rule.output_check and rule.must_flag and rule.must_pass, "regra de saída sem verificador ou exemplos"
        assert rule.examples_origin in {HOUSE, MODEL}
    if ENTRY in rule.stages and rule.id not in {"R3", "R8"} or rule.entry_check:
        assert rule.entry_check and rule.entry_flag and rule.entry_pass, "regra de entrada sem detector ou exemplos"
    if rule.repair:
        assert rule.effect_for(HOUSE) == Effect.REPAIR
    for text in (*rule.must_pass, rule.title, rule.when, rule.demands):
        assert "—" not in text and "–" not in text  # a tabela segue a própria R12


def _cases(kind):
    for rule in RULES:
        for text in getattr(rule, kind):
            yield pytest.param(rule, text, id=f"{rule.id}:{text[:40]}")


# ── 2. Cada regra pelos próprios exemplos ─────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("rule", "text"), list(_cases("must_flag")))
def test_output_rule_flags_its_examples(rule, text):
    assert rule.output_check(text, ReplyContext(origin=rule.examples_origin)), text


@pytest.mark.django_db
@pytest.mark.parametrize(("rule", "text"), list(_cases("must_pass")))
def test_output_rule_lets_its_counterexamples_pass(rule, text):
    assert rule.output_check(text, ReplyContext(origin=rule.examples_origin)) == [], text


@pytest.mark.parametrize(("rule", "text"), list(_cases("entry_flag")))
def test_entry_rule_catches_its_examples(rule, text):
    assert rule.entry_check(text), text


@pytest.mark.parametrize(("rule", "text"), list(_cases("entry_pass")))
def test_entry_rule_lets_its_counterexamples_pass(rule, text):
    assert not rule.entry_check(text), text


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("O croissant está esgotado.", "O croissant está indisponível."),
        ("Os pães de queijo acabaram.", "Os pães de queijo estão indisponíveis."),
        ("Esgotados hoje: brioche.", "Indisponíveis hoje: brioche."),
        ("Obrigado pela preferência!", "Obrigada pela preferência!"),
        ("Nosso concierge está fora do ar.", "Nossa concierge está fora do ar."),
        ("Croissant — R$ 13,00", "Croissant: R$ 13,00"),
        ("Pedido ORD-1 — Em preparo.", "Pedido ORD-1, Em preparo."),
        ("Total: **R$ 68,00**", "Total: R$ 68,00"),
        ("Pronto! 🎉", "Pronto!"),
        ("Até logo! 💛", "Até logo! 💛"),
    ],
)
def test_repair_rules_fix_the_word_and_let_the_reply_go(before, after):
    reviewed = house_rules.review([before])
    assert reviewed.texts == [after]
    assert reviewed.held == []


def test_r1_and_r5_hold_model_text_and_trust_house_text():
    """A resposta montada pelo código traz o preço da ficha; o modelo nunca digita preço."""
    text = "Croissant: R$ 13,00. Total: R$ 26,00."
    assert house_rules.review([text], ReplyContext(origin=HOUSE)).held == []
    held = {v.rule for v in house_rules.review([text], ReplyContext(origin=MODEL)).held}
    assert {"R1", "R5"} <= held


def test_r6_promise_goes_out_only_with_its_receipt():
    """A frase do teste do dono (04/09): "vou avisar a equipe" sem ninguém avisado."""
    promise = "Vou avisar nossa equipe sobre o problema no link do cartão."
    assert [v.rule for v in house_rules.review([promise]).held] == ["R6"]
    assert house_rules.review([promise], ReplyContext(receipts=frozenset({TEAM_NOTIFIED}))).held == []

    assert house_rules.review(["Já separei 2 croissants."]).held
    assert not house_rules.review(["Já separei 2 croissants."], ReplyContext(receipts=frozenset({CART}))).held
    assert not house_rules.review(["Pedido ORD-7 registrado. Total: R$ 52,00."], ReplyContext(receipts=frozenset({ORDER}))).held
    # Aviso de alerta não é entrega da conversa: "a equipe continua" pede o handoff.
    takeover = "A equipe continua o atendimento por aqui."
    assert house_rules.review([takeover], ReplyContext(receipts=frozenset({TEAM_NOTIFIED}))).held
    assert not house_rules.review([takeover], ReplyContext(receipts=frozenset({HANDOFF}))).held


def test_receipts_come_from_what_the_executors_did():
    from shopman.storefront.concierge.agent import AgentOutcome

    outcome = AgentOutcome(
        reply_text="",
        tool_events=[
            {"name": "set_item", "ok": True},
            {"name": "place_order", "ok": False},
            {"name": "notify_when_available", "ok": True},
        ],
    )
    assert house_rules.receipts_for(outcome) == {CART, house_rules.NOTIFY}
    assert house_rules.receipts_for(AgentOutcome(reply_text="", order_ref="ORD-1")) == {ORDER}
    assert house_rules.receipts_for(None, team_notified=True) == {TEAM_NOTIFIED}


@pytest.mark.django_db
def test_r13_lets_the_house_contact_out():
    from shopman.shop.models import Shop

    shop = Shop.load() or Shop.objects.create(name="Casa")
    shop.phone, shop.email = "554333231997", "contato@casa.com.br"
    shop.save()
    contacts = house_rules.house_contacts()
    text = "Fale com a casa pelo (43) 3323-1997 ou contato@casa.com.br."
    assert house_rules.check(text, ReplyContext(house_contacts=contacts)) == [] or all(
        v.rule != "R13" for v in house_rules.check(text, ReplyContext(house_contacts=contacts))
    )
    assert any(v.rule == "R13" for v in house_rules.check("Ligue (43) 99876-5432.", ReplyContext(house_contacts=contacts)))


def test_locked_blocks_stay_out_of_form_and_personal_data():
    pix = "00020126580014BR.GOV.BCB.PIX0136" + "52998224725" + "5204000053039865802BR6304ABCD"
    assert house_rules.check(pix) == []
    assert house_rules.check("Continue no site: https://loja.exemplo/s/12345678901") == []


def test_r14_send_refuses_without_the_24h_window_evidence():
    """R14 é executada pelo transporte: sem evidência da janela, o envio é recusado."""
    from shopman.storefront.concierge import transport

    assert RULES_BY_ID["R14"].stages == (SEND,)
    adapter = transport.ManyChatWhatsAppAdapter.__new__(transport.ManyChatWhatsAppAdapter)
    adapter._window_config = lambda: {}
    refused = adapter.authorize_response(None, timezone.now(), purpose="reply")
    assert refused.allowed is False


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("Faz um desconto pra mim?", "R7"),
        ("Você é um robô? Faz um desconto?", "R7"),
        ("vc é robô?", "R8"),
        ("tem croissant?", ""),
    ],
)
def test_fixed_reply_for_entry_rules(text, rule):
    got, reply = house_rules.fixed_reply_for(text, shop_name="Casa", copy=lambda key: f"[{key}] {{shop_name}}")
    assert got == rule
    assert bool(reply) == bool(rule)


# ── 3. O turno inteiro ────────────────────────────────────────────────


@pytest.mark.django_db
def test_r8_identity_question_gets_the_fixed_reply_without_model(conversation, alpha_menu):
    outcome, client = _turn(conversation, "Você é um robô?", "identity-1")
    assert client.requests == []
    assert outcome.reply_text.startswith("Sou a assistente virtual da")
    assert outcome.layer == "house_rule"


@pytest.mark.django_db
def test_r7_discount_request_gets_the_fixed_reply_without_model(conversation, alpha_menu, monkeypatch):
    # Teto do desconto da Concierge desligado (0): sobra a frase fixa. Com teto, o
    # desconto até ele é do sistema (``test_concierge_discount.py``).
    from shopman.storefront.concierge import discount

    monkeypatch.setattr(discount, "max_percent", lambda channel_ref: discount.Decimal(0))
    outcome, client = _turn(conversation, "Consegue fazer um preço melhor nos 10 croissants?", "nego-1")
    assert client.requests == []
    assert "não consigo negociar" in outcome.reply_text
    assert house_rules.check(outcome.reply_text) == []


@pytest.mark.django_db
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_house_reply_with_a_promise_nobody_keeps_is_held_and_goes_to_the_team(conversation, outbox, monkeypatch):
    """A copy do teto diário prometia "a equipe segue com você" sem chamar ninguém.

    A resposta montada pelo sistema passa pela tabela: R6 segura, a conversa vai para a
    equipe e o cliente recebe o aviso de handoff, que agora é verdade.
    """
    copies = {
        "CONCIERGE_TURN_LIMIT": "Chegamos ao limite. A equipe segue com você por aqui.",
        "CONCIERGE_HANDOFF_ACK": "Solicitei atendimento humano. A equipe continuará por aqui.",
    }
    monkeypatch.setattr(service, "copy_message", lambda key: copies.get(key, f"[{key}]"))
    conversation.turns_today = 80
    conversation.turns_day = timezone.localdate()
    conversation.save()
    _receive(conversation, "tem pão?", "limit-1")

    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())

    assert result.handoff
    assert outbox.sent == [copies["CONCIERGE_HANDOFF_ACK"]]
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert conversation.handoff_reason.startswith("Regra da casa: R6")
    ack = ConversationMessage.objects.get(conversation=conversation, kind="reply")
    assert ack.envelope["house_rules"]["replaced"]["held"] == ["R6"]
    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.filter(type="concierge_handoff", message__startswith="Regra da casa").exists()


@pytest.mark.django_db
@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS, AI_ASSIST_API_KEY="sk-teste")
def test_house_reply_is_repaired_before_it_goes_out(conversation, outbox, monkeypatch):
    """Copy editada no Admin com travessão e "obrigado" sai consertada, e o envelope conta."""
    monkeypatch.setattr(
        service,
        "copy_message",
        lambda key: "Obrigado — ainda não ouço áudios." if key == "CONCIERGE_MEDIA_UNSUPPORTED" else f"[{key}]",
    )
    _receive(conversation, "https://lookaside.fbsbx.com/x/audio.ogg", "media-1", message_type="audio")

    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())

    assert result.fallback == "media"
    assert outbox.sent == ["Obrigada, ainda não ouço áudios."]
    reply = ConversationMessage.objects.get(conversation=conversation, kind="reply")
    assert reply.envelope["house_rules"]["repaired"] == ["R10", "R12"]
    assert reply.envelope["house_rules"]["version"] == house_rules.VERSION


@pytest.mark.django_db
def test_default_house_copy_obeys_the_rules():
    """As frases da casa que o turno manda sem recibo não prometem nada (R6) e têm a voz da casa."""
    resolve = service.copy_message

    keys = (
        "CONCIERGE_MEDIA_UNSUPPORTED",
        "CONCIERGE_TURN_LIMIT",
        "CONCIERGE_NO_PHONE",
        "CONCIERGE_SMALL_TALK_OFFER",
        "CONCIERGE_SMALL_TALK_THANKS",
        "CONCIERGE_SMALL_TALK_FAREWELL",
        "CONCIERGE_PRICE_NEGOTIATION",
        "CONCIERGE_IDENTITY",
    )
    for key in keys:
        text = resolve(key)
        assert house_rules.review([text]).held == [], key
        assert house_rules.review([text]).texts == [text], key
    # A de indisponível vai com o alerta criado (recibo de equipe avisada).
    unavailable = resolve("CONCIERGE_UNAVAILABLE")
    assert house_rules.review([unavailable], ReplyContext(receipts=frozenset({TEAM_NOTIFIED}))).held == []
    ack = resolve("CONCIERGE_HANDOFF_ACK")
    assert house_rules.review([ack], ReplyContext(receipts=frozenset({HANDOFF}))).held == []


def test_review_keeps_alignment_with_empty_replies():
    reviewed = house_rules.review(["", "Croissant — R$ 13,00"])
    assert reviewed.texts == ["", "Croissant: R$ 13,00"]


def test_reason_line_names_the_rule():
    reviewed = house_rules.review(["Já separei para você."])
    assert reviewed.reason_line() == "Regra da casa: R6 nunca prometer ação sem recibo"
    assert timedelta  # (import usado nos casos de janela)
