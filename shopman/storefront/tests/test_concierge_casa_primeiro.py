# ruff: noqa: F401, F811
"""A casa primeiro, a IA só no que ela não resolve (coordenação, 22/11/2026; DEV-2026-076).

O pedido que a leitura da casa entende por inteiro (itens, quantidade, quando/como, cortesia)
não vai ao leitor de IA: a mesma resposta toda vez, e sem custo. Sobrou palavra que a casa não
entende, ou a fala é sobre pedido já feito: o leitor de IA continua sendo
chamado, e é a leitura dele que vale.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import service
from shopman.storefront.tests.test_concierge_engine import (
    _binding,
    _create_inbound,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import ReaderClient, _act
from shopman.storefront.tests.test_concierge_sacola import _cart, menu

pytestmark = pytest.mark.django_db


def _turn_with(conversation, text, reader):
    message = _create_inbound(conversation, text, f"casa-{Message.objects.count()}")
    envelope = {**message.envelope, "input_assurance": "at_least_once", "event_identity_assurance": "unavailable"}
    envelope.pop("event_id", None)
    Message.objects.filter(pk=message.pk).update(envelope=envelope)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=None)
    service.run_turn(conversation.pk, _binding(conversation).pk, intents_client=reader)


@pytest.mark.parametrize("text", [
    "quero 2 croissants para retirar amanhã às 16h",
    "2 croissant pra amanha, busco 16h",
    "oi! queria 2 croissants e 2 pain au chocolat pra amanhã, por favor",
])
def test_an_order_the_house_understands_whole_does_not_call_the_ai(conversation, outbox, menu, text):
    reader = ReaderClient([_act("order", text, "brioche", 9)])  # se fosse chamado, mandaria errado

    _turn_with(conversation, text, reader)

    assert reader.requests == []
    assert _cart(conversation).get("CROISSANT") == 2


def test_a_follow_up_the_house_understands_does_not_call_the_ai(conversation, outbox, menu):
    _turn_with(conversation, "quero 2 croissants", ReaderClient([]))
    reader = ReaderClient([_act("order", "na verdade 3", "brioche", 9)])

    _turn_with(conversation, "na verdade 3", reader)

    assert reader.requests == [] and _cart(conversation) == {"CROISSANT": 3}


@pytest.mark.parametrize("text", [
    "quero 2 croissant e o de ontem veio queimado",  # palavra que a casa não entende: a queixa
    "as 2 croissants que pedi",  # pedido já feito
])
def test_what_the_house_does_not_understand_whole_still_goes_to_the_ai(conversation, outbox, menu, text):
    reader = ReaderClient([_act("unknown", text)])

    _turn_with(conversation, text, reader)

    assert len(reader.requests) == 1
