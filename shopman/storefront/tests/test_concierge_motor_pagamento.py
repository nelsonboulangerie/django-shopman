"""A forma de pagamento pelo motor, do lado da Nice (cartão 5 do pedido pelo motor, 23/11/2026).

O motor pergunta a forma quando o canal tem mais de uma e a sacola nenhuma (``requirements``), lê a
resposta (``choose_payment {method}``) e grava pelo sítio (``set_payment``). O que estes testes seguram:

- o fato do canal diz o que falta e as opções, sem dinheiro (D-003), só da sacola do sujeito;
- o sítio grava a forma na sacola e sobe a revisão (o "sim" de antes cai, N07); recusa dinheiro e
  forma que o canal não oferece;
- o leitor da Nice devolve ``choose_payment`` com ``method``;
- a pergunta é a MESMA de hoje, e o feito diz "Combinado: Pix.".
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from conversational_commerce.contracts import Known
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import PortError
from shopman.orderman.models import Session

from shopman.shop.conversational.commerce_read import ShopmanCommerceRead
from shopman.shop.models import Channel, Conversation
from shopman.storefront.concierge.effect_site import ConciergeEffectSite
from shopman.storefront.concierge.ports import ConversationOwnership, new_cart_ref
from shopman.storefront.concierge.tools import ToolContext

pytestmark = pytest.mark.django_db

CHANNEL = "whatsapp"
CTX = SimpleNamespace(tenant="t", environment="test", subject="conversation:1")


@pytest.fixture
def channel():
    return Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={"payment": {"method": ["pix", "card", "cash"]}})


@pytest.fixture
def conversation(channel):
    return Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)


def _read_port():
    return ShopmanCommerceRead(channel_ref=CHANNEL, ownership=ConversationOwnership())


def _ctx():
    from conversational_commerce.ports import TrustedContext

    return TrustedContext(tenant="t", environment="test", subject="conversation:1")


# ── o fato do canal ──────────────────────────────────────────────────────────────────────


def test_without_a_choice_the_payment_is_missing_with_the_channel_options_and_no_cash(conversation):
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    fact = _read_port().requirements(_ctx(), "sess-1")
    assert isinstance(fact, Known)
    assert {k: list(v) for k, v in fact.value.items()} == {"missing": ["payment_method"], "payment_method": ["pix", "card"]}


def test_a_chosen_method_is_no_longer_missing(conversation):
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL, data={"payment": {"method": "card"}})
    assert list(_read_port().requirements(_ctx(), "sess-1").value["missing"]) == []


def test_a_single_method_channel_never_asks(db):
    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={"payment": {"method": ["pix", "cash"]}})
    Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    assert list(_read_port().requirements(_ctx(), "sess-1").value["missing"]) == []


def test_the_new_cart_of_the_conversation_has_requirements_too(channel):
    """ "2 croissants, pago no pix" no primeiro pedido: a forma confere antes de a sacola nascer."""
    Conversation.objects.create(pk=1, channel_ref=CHANNEL)
    fact = _read_port().requirements(_ctx(), new_cart_ref(1))
    assert list(fact.value["payment_method"]) == ["pix", "card"]


def test_another_subject_cart_is_forbidden(conversation):
    Session.objects.create(session_key="sess-2", channel_ref=CHANNEL)
    with pytest.raises(PortError):
        _read_port().requirements(_ctx(), "sess-2")


# ── o sítio ──────────────────────────────────────────────────────────────────────────────


def _command(method, target="sess-1"):
    return SimpleNamespace(action="set_payment", targets=(target,), parameters={"method": method})


def test_the_site_writes_the_method_and_moves_the_cart_revision(conversation):
    session = Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    before = session.rev
    site = ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))
    done = site.apply(CTX, _command("pix"))
    session.refresh_from_db()
    assert done.applied and dict(done.domain_refs) == {"effect": "sess-1", "cart": "sess-1", "method": "pix"}
    assert session.data["payment"] == {"method": "pix"}
    assert session.rev > before  # o "sim" aos termos de antes não vale mais (a guarda confere a versão)


@pytest.mark.parametrize("method", ["cash", "boleto", ""])
def test_the_site_refuses_cash_and_what_the_channel_does_not_offer(conversation, method):
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    site = ConciergeEffectSite(ToolContext(conversation=conversation, channel_ref=CHANNEL))
    done = site.apply(CTX, _command(method))
    assert (done.applied, done.refusal) == (False, ErrorCode.INVALID_CONTENT.value)
    assert not (Session.objects.get(session_key="sess-1").data or {}).get("payment")


def test_set_payment_is_a_cart_action_that_may_land_on_the_new_cart():
    from shopman.storefront.concierge import effect_site

    assert "set_payment" in effect_site.ACTIONS
    assert "set_payment" in effect_site.NEW_CART_ACTIONS


# ── o leitor ─────────────────────────────────────────────────────────────────────────────


def test_the_reader_returns_choose_payment_with_the_method(conversation):
    from conversational_commerce.engine.acts import ACTS

    from shopman.storefront.tests.test_concierge_model_reader import FakeAI, _fields, _read

    ai = FakeAI(raw=json.dumps({"acts": [{"act": "choose_payment", "span": "no pix", "product": "", "qty": 0,
                                          "change": "", "day": "", "mode": "", "time": "", "payment": "pix"}]}))
    understanding, _ = _read("pode ser no pix", ai, allowed=ACTS)
    assert _fields(understanding) == [("choose_payment", {"method": "pix"})]
    assert "payment" in json.dumps(ai.requests[0]["output_config"])


def test_a_payment_outside_the_vocabulary_is_dropped():
    from shopman.storefront.concierge.model_reader import parse

    readings = parse(json.dumps({"acts": [{"act": "choose_payment", "payment": "bitcoin"}]}), "bitcoin",
                     ("choose_payment",))
    assert readings[0].payment == ""


# ── as frases ────────────────────────────────────────────────────────────────────────────


def _say(template_id: str, **values) -> str:
    from shopman.storefront.concierge import turn_framework

    template = turn_framework.nice_templates()[template_id]
    formatters = turn_framework.nice_formatters()
    text = template.text
    for slot, value in values.items():
        text = text.replace("{" + slot + "}", formatters[slot](value))
    return text


def test_the_question_is_today_question_with_the_channel_options(db):
    from shopman.storefront.concierge.service import copy_message

    today = copy_message("CONCIERGE_CLOSE_ASK_PAYMENT").strip()
    said = _say("present_terms.needs_payment_method", payment_method=["pix", "card"])
    assert said == today.replace("{options}", "Pix ou Cartão (link seguro)")
    assert said == "Como você prefere pagar? Pix ou Cartão (link seguro)"


def test_the_choice_says_combinado(db):
    assert _say("set_payment.done", method="pix") == "Combinado: Pix."
    assert _say("set_payment.done", method="card") == "Combinado: Cartão (link seguro)."


def test_a_method_the_house_does_not_know_never_leaks():
    from shopman.storefront.concierge.turn_framework import method_text

    with pytest.raises(ValueError):
        method_text("boleto")


def test_the_profile_turns_set_payment_on_with_the_order(db):
    from shopman.storefront.concierge import profile, turn_framework

    assert "set_payment" in profile.ORDER_MOVES
    assert profile.LEVEL_OF_MOVE["set_payment"] == "A2"
    assert turn_framework.CLASS_OF_MOVE["set_payment"] == "order"


def test_cash_is_said_with_today_no_cash_phrase_and_the_options(db):
    """ "Pago em dinheiro": a frase de hoje do fechamento (``CONCIERGE_CLOSE_NO_CASH``), nunca a limitação genérica."""
    from shopman.storefront.concierge.service import copy_message

    today = copy_message("CONCIERGE_CLOSE_NO_CASH").strip()
    said = _say("set_payment.not_offered", payment_method=["pix", "card"])
    assert said == today.replace("{options}", "Pix ou Cartão (link seguro)")


# ── a régua única ─────────────────────────────────────────────────────────────────────────


def test_what_is_missing_and_the_single_method_shown_follow_one_ruler(db):
    """Canal com pix e dinheiro: a conversa oferece só pix. Nada falta, e os termos mostram pix (antes, as condições
    contavam o dinheiro, viam duas formas e não mostravam nenhuma, enquanto o requirements dizia que nada faltava)."""
    from shopman.shop.conversational.commerce_read import _fulfillment_conditions

    Channel.objects.create(ref=CHANNEL, name="WhatsApp", config={"payment": {"method": ["pix", "cash"]}})
    Conversation.objects.create(pk=1, session_key="sess-1", channel_ref=CHANNEL)
    Session.objects.create(session_key="sess-1", channel_ref=CHANNEL)
    assert list(_read_port().requirements(_ctx(), "sess-1").value["missing"]) == []
    assert {"code": "payment_method", "value": "pix"} in _fulfillment_conditions({}, CHANNEL)


def test_a_source_that_fails_is_unknown_never_an_empty_list(conversation, monkeypatch):
    from conversational_commerce.contracts import Unknown

    from shopman.shop.conversational import commerce_read

    monkeypatch.setattr(commerce_read, "conversation_payment_methods", lambda ref: 1 / 0)
    assert isinstance(_read_port().requirements(_ctx(), "sess-1"), Unknown)
