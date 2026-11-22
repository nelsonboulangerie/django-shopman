# ruff: noqa: F401, F811
"""Reclamação não cala a conversa (ensaio do dono no WhatsApp, 21/11/2026).

"mas eu ainda queria adicionar itens... porque já fechou o pedido??? não posso acrescentar mais
coisas no meu pedido?" virou reclamação, a equipe foi chamada e a Concierge calou para tudo. O
dono: "garanta sempre a questão de atribuição da conversa". A reclamação vai à equipe pelo "vou
verificar" (cartão no sino, com prazo) e a Concierge segue; quem assume a conversa é uma pessoa,
pelo "Assumir". Handoff automático fica para pessoa pedida, alergia, cancelamento fora do
autoatendimento e encomenda especial.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import Conversation
from shopman.storefront.tests.test_concierge_engine import conversation, customer, outbox, surface
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn, menu

pytestmark = pytest.mark.django_db

COMPLAINT = "porque já fechou o pedido??? não posso acrescentar mais coisas no meu pedido?"


def test_a_complaint_alone_goes_to_the_team_by_card_and_the_concierge_keeps_talking(conversation, outbox, menu):
    reply = _turn(conversation, COMPLAINT, [_act("complaint", COMPLAINT)])

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE  # ninguém silenciou a conversa
    assert reply.startswith("Sinto muito por isso. Já levei à equipe e sigo com você por aqui."), reply
    assert (conversation.flags.get("verification") or {}).get("alert_pk"), conversation.flags  # o cartão abriu


def test_with_an_open_cart_the_complaint_reply_shows_it(conversation, outbox, menu):
    _turn(conversation, "quero 2 croissant", [_act("order", "quero 2 croissant", "croissant", 2)])

    reply = _turn(conversation, COMPLAINT, [_act("complaint", COMPLAINT)])

    assert "Sua sacola de agora:" in reply and "2 × " in reply, reply
    assert _cart(conversation) == {"CROISSANT": 2}


def test_asking_for_a_person_still_hands_off(conversation, outbox, menu):
    text = "isso está errado, quero falar com uma pessoa"
    _turn(conversation, text, [_act("complaint", "isso está errado"), _act("human", "quero falar com uma pessoa")])

    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
