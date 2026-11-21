# ruff: noqa: F401, F811
"""Fechar o pedido na conversa (WP-13): do recebimento ao Pix.

Ingresso "pelo menos uma vez" (o do ManyChat), com a autoridade de sacola do WP-11: o
fechamento só sai com o código do orçamento ("confirmo 4821"). O "Pronto quando" do plano,
item por item.
"""

from __future__ import annotations

import re

import pytest
from shopman.orderman.models import Order, Session

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import intents, service
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    CONCIERGE_SETTINGS,
    SKU,
    _binding,
    _create_inbound,
    _geocode_text,
    _listed,
    _saved_address,
    _tomorrow,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act

pytestmark = pytest.mark.django_db

ORDER_TWO = [_act("order", "quero 2 pão francês", "pão francês", 2)]


@pytest.fixture
def shop(surface, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")


def _turn(conversation, text, acts=()):  # noqa: F811
    """Um turno inteiro, pelo ingresso sem identificador de mensagem (o do ManyChat)."""
    message = _create_inbound(conversation, text, f"fechar-{Message.objects.count()}")
    envelope = {**message.envelope, "input_assurance": "at_least_once", "event_identity_assurance": "unavailable"}
    envelope.pop("event_id", None)
    Message.objects.filter(pk=message.pk).update(envelope=envelope)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    before = Message.objects.filter(conversation=conversation, kind="reply").order_by("-pk").values_list("pk", flat=True).first() or 0
    service.run_turn(conversation.pk, _binding(conversation).pk, intents_client=ReaderClient(list(acts)))
    replies = Message.objects.filter(conversation=conversation, kind="reply", pk__gt=before).order_by("pk")
    return [row.text for row in replies]


def _say(conversation, text, acts=()):  # noqa: F811
    return "\n".join(_turn(conversation, text, acts))


def _session(conversation) -> Session:  # noqa: F811
    conversation.refresh_from_db()
    return Session.objects.get(session_key=conversation.session_key)


def _code(reply: str) -> str:
    found = re.search(r"confirmo (\d{4})", reply)
    assert found, reply
    return found.group(1)


def _bag(conversation):  # noqa: F811
    reply = _say(conversation, "quero 2 pão francês", ORDER_TWO)
    assert "2 × “Pão Francês”" in reply, reply


def _pickup_until_summary(conversation):  # noqa: F811
    _bag(conversation)
    assert _say(conversation, "pode fechar") == "Para quando é o pedido? Hoje, amanhã ou outro dia (dia/mês)?"
    assert _say(conversation, "amanhã") == "Você vai retirar aqui na loja ou prefere entrega?"
    slots = _say(conversation, "vou retirar")
    assert slots.startswith("Qual horário de retirada fica melhor?") and "1) A partir das 9h" in slots, slots
    payment = _say(conversation, "às 13h")
    assert payment == "Como você prefere pagar? 1) Pix; 2) Cartão (link seguro)", payment
    data = _session(conversation).data
    assert (data["fulfillment_type"], data["delivery_date"], data["delivery_time_slot"]) == ("pickup", _tomorrow(), "slot-12")
    return _say(conversation, "pix")


def test_pickup_with_the_chosen_time(conversation, outbox, shop):
    summary = _pickup_until_summary(conversation)

    assert "Retirada:" in summary and "A partir das 12h" in summary, summary
    assert _session(conversation).data["payment"] == {"method": "pix"}


def test_the_summary_has_the_system_total_and_the_code_of_wp11(conversation, outbox, shop):
    summary = _pickup_until_summary(conversation)

    conversation.refresh_from_db()
    quote = conversation.quote
    assert "Total: R$ 1,80" in summary, summary
    from shopman.storefront.concierge.tools import quote_code

    assert _code(summary) == quote_code(quote["token"])
    offered = Message.objects.filter(conversation=conversation, kind="reply").order_by("-pk").first()
    assert offered.envelope.get("quote_token") == quote["token"], "o resumo é o orçamento oferecido"


def test_confirming_makes_one_order(conversation, outbox, shop):
    summary = _pickup_until_summary(conversation)
    code = _code(summary)

    placed = _turn(conversation, f"confirmo {code}")
    _turn(conversation, f"confirmo {code}")

    assert Order.objects.count() == 1, "a confirmação repetida não faz outro pedido"
    order = Order.objects.get()
    assert order.channel_ref == CHANNEL, "aparece no Gestor como qualquer pedido do canal"
    assert order.data["payment"]["method"] == "pix"
    assert (order.data["fulfillment_type"], order.data["delivery_time_slot"]) == ("pickup", "slot-12")
    assert placed[0].startswith(f"Pedido {order.ref} registrado. Total: R$ 1,80."), placed


def test_a_plain_yes_asks_for_the_code_and_does_not_close(conversation, outbox, shop):
    summary = _pickup_until_summary(conversation)

    reply = _say(conversation, "sim")

    assert reply == f"Para registrar o pedido, responda: confirmo {_code(summary)}", reply
    assert not Order.objects.exists()


def test_changing_the_subject_keeps_the_bag_and_resumes(conversation, outbox, shop):
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")
    slots = _say(conversation, "vou retirar")
    assert slots.startswith("Qual horário de retirada fica melhor?")

    reply = _say(conversation, "tem croissant?", [_act("product_question", "tem croissant?", "croissant")])

    assert "Croissant" in reply, reply
    assert reply.rstrip().endswith(slots.split("? ", 1)[1]), "a pergunta que estava no ar volta no fim"
    assert {i["sku"]: int(i["qty"]) for i in _session(conversation).items} == {SKU: 2}
    assert _say(conversation, "o 2").startswith("Como você prefere pagar?")
    assert _session(conversation).data["delivery_time_slot"] == "slot-12"


def test_a_time_before_the_first_pickup_is_refused_with_the_true_reason(conversation, outbox, shop):
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")
    _say(conversation, "vou retirar")

    reply = _say(conversation, "às 7h")

    assert reply.startswith("Às 7h ainda não há retirada nesse dia."), reply
    assert "1) A partir das 9h" in reply
    assert not _session(conversation).data.get("delivery_time_slot")


def test_a_time_outside_delivery_is_refused_with_the_true_reason(conversation, outbox, shop, customer, monkeypatch):
    _geocode_text(monkeypatch)
    _saved_address(customer)
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")
    assert _say(conversation, "entrega") == "Entregamos no endereço do seu cadastro, Rua Pará, 120 - Centro?"
    _say(conversation, "sim")

    reply = _say(conversation, "às 7h")

    assert reply.startswith("Às 7h não entregamos nesse dia. As janelas de entrega são: 1) A partir das 9h"), reply
    assert not _session(conversation).data.get("delivery_time_slot")


def test_delivery_with_the_saved_address(conversation, outbox, shop, customer, monkeypatch):
    _geocode_text(monkeypatch)
    saved = _saved_address(customer)
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")

    offer = _say(conversation, "entrega")
    payment = _say(conversation, "sim")

    assert offer == "Entregamos no endereço do seu cadastro, Rua Pará, 120 - Centro?"
    assert payment.startswith("Como você prefere pagar?"), payment
    data = _session(conversation).data
    assert data["fulfillment_type"] == "delivery" and data["saved_address_id"] == saved.pk
    summary = _say(conversation, "pix")
    assert "Entrega:" in summary and "confirmo " in summary, summary


def test_a_new_incomplete_address_asks_only_what_is_missing(conversation, outbox, shop, monkeypatch):
    _geocode_text(monkeypatch, route="Rua das Flores", neighborhood="Centro", city="Londrina", state_code="PR")
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")
    asked = _say(conversation, "entrega")
    assert "localização pelo WhatsApp" in asked, asked

    reply = _say(conversation, "rua das flores, centro")

    assert reply == "Para a entrega, me diga o número (ou S/N) e o CEP.", reply
    assert _session(conversation).data["delivery_address_structured"]["route"] == "Rua das Flores"


def test_cash_is_not_offered(conversation, outbox, shop):
    _bag(conversation)
    _say(conversation, "pode fechar")
    _say(conversation, "amanhã")
    _say(conversation, "vou retirar")
    _say(conversation, "o 1")

    reply = _say(conversation, "em dinheiro")

    assert reply.startswith("Pelo WhatsApp não recebemos em dinheiro."), reply
    assert "Dinheiro" not in reply


@pytest.mark.parametrize("text", ["deixa, não quero mais", "não", "desisto"])
def test_giving_up_at_the_summary_registers_nothing_and_keeps_the_bag(conversation, outbox, shop, text):
    _pickup_until_summary(conversation)

    reply = _say(conversation, text)

    assert reply == "Tudo bem, fica sem pedido por agora. Os itens continuam na sacola, se mudar de ideia.", reply
    assert not Order.objects.exists()
    assert {i["sku"]: int(i["qty"]) for i in _session(conversation).items} == {SKU: 2}
    assert _say(conversation, "confirmo 0000") != "", "o fechamento acabou: a fala segue para as partes"
    assert not Order.objects.exists()

