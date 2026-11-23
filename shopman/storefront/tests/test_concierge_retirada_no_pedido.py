# ruff: noqa: F401, F811
"""O dia, a retirada e a hora ditos junto com o pedido (WP-14, cartão 1, ensaio de 22/11/2026).

A conversa real, palavra por palavra: "quero 2 croissants para retirar amanha às 16h" virou
"tirei Croissant" (o "retirar" lido como tirar da sacola), e a segunda tentativa virou "vou
verificar com a equipe" e "Croissant: Indisponível" (o croissant medido para AGORA, não para
amanhã). Aqui o pedido entra, o dia e a retirada ficam anotados, e a sacola mede a fornada da data.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.orderman.models import Order

from shopman.storefront.tests.test_concierge_engine import (
    _tomorrow,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_fechar_pedido import _code, _say, _session, _turn, shop
from shopman.storefront.tests.test_concierge_intents import _act

pytestmark = pytest.mark.django_db

FIRST = "quero 2 croissants para retirar amanha às 16h"
SECOND = "voce nao entendeu... quero 2 croissants para amanha e eu vou ai buscar (retirada) as 16h... entendeu?"


def _order(span):
    return _act("order", span, "croissant", 2)


def _noted_pickup_tomorrow(conversation, reply):
    assert "tirei" not in reply and "vazia" not in reply, reply
    assert "Indisponível" not in reply and "equipe" not in reply, reply
    assert reply.startswith("Combinado: retirada amanhã"), reply
    assert "2 × “Croissant”" in reply, reply
    data = _session(conversation).data
    assert (data["fulfillment_type"], data["delivery_date"]) == ("pickup", _tomorrow()), data


def test_the_first_phrase_of_the_rehearsal_puts_two_and_notes_pickup_tomorrow(conversation, outbox, shop):
    reply = _say(conversation, FIRST, [_order(FIRST)])

    _noted_pickup_tomorrow(conversation, reply)
    assert {item["sku"]: int(item["qty"]) for item in _session(conversation).items} == {"CROISSANT": 2}


def test_the_second_phrase_of_the_rehearsal_is_not_a_question_for_the_team(conversation, outbox, shop):
    # A leitura que a casa recebeu: o pedido e, à parte, "eu vou aí buscar às 16h".
    acts = [_order("quero 2 croissants para amanha"),
            _act("hours_delivery", "eu vou ai buscar (retirada) as 16h... entendeu?", "", 0)]

    reply = _say(conversation, SECOND, acts)

    _noted_pickup_tomorrow(conversation, reply)


@pytest.mark.parametrize("text", [
    "quero 2 croissants, vou buscar amanhã às 16h",
    "quero 2 croissants pra pegar amanhã às 16h",
    "quero 2 croissants, passo aí às 16h amanhã",
    "quero 2 croissants para amanhã, retirada às 16h",
])
def test_the_variants_note_pickup_tomorrow(conversation, outbox, shop, text):
    reply = _say(conversation, text, [_order(text)])

    _noted_pickup_tomorrow(conversation, reply)


def test_for_tomorrow_alone_puts_the_item_and_is_not_a_removal_nor_a_question(conversation, outbox, shop):
    # Sem dizer retirada nem entrega (o canal tem as duas), o dia fica para o fechamento,
    # que pergunta só o que falta. O item entra e nada vira "tirei" nem "vou verificar".
    text = "quero 2 croissants para amanhã"
    reply = _say(conversation, text, [_order(text)])

    assert "2 × “Croissant”" in reply and "tirei" not in reply and "equipe" not in reply, reply
    assert {item["sku"]: int(item["qty"]) for item in _session(conversation).items} == {"CROISSANT": 2}


def test_taking_out_still_takes_out(conversation, outbox, shop):
    _say(conversation, "quero 2 croissants", [_order("quero 2 croissants")])

    reply = _say(conversation, "retira o croissant", [_act("order", "retira o croissant", "croissant")])

    assert "tirei Croissant" in reply, reply
    assert not _session(conversation).items


def test_sold_out_today_but_in_tomorrow_batch_goes_in_for_tomorrow(conversation, outbox, shop):
    from shopman.stockman.models import Position, Quant
    from shopman.stockman.service import Stock

    for ready in Quant.objects.filter(sku="CROISSANT", _quantity__gt=0):
        Stock.issue(ready._quantity, ready, reason="ensaio: vendeu tudo hoje")
    Quant.objects.create(sku="CROISSANT", position=Position.objects.get(ref="loja"),
                         target_date=date.today() + timedelta(days=1), _quantity=Decimal("20"))

    reply = _say(conversation, FIRST, [_order(FIRST)])

    _noted_pickup_tomorrow(conversation, reply)


def test_card_one_end_to_end_the_order_is_registered_for_tomorrow_at_16h(conversation, outbox, shop):
    """O cartão 1 inteiro: a frase dele, o resumo certo, "confirmo" com o código, o pedido registrado."""
    _noted_pickup_tomorrow(conversation, _say(conversation, FIRST, [_order(FIRST)]))
    slot = _session(conversation).data["delivery_time_slot"]
    assert slot, "as 16h ditas na fala escolheram o horário da retirada"

    payment = _say(conversation, "pode fechar")
    # Dia, retirada e horário já ditos: o fechamento pergunta só o que falta.
    assert payment == "Como você prefere pagar? 1) Pix; 2) Cartão (link seguro)", payment
    summary = _say(conversation, "pix")
    from django.utils import formats

    tomorrow = date.today() + timedelta(days=1)
    day = f"{formats.date_format(tomorrow, 'l').lower()}, {formats.date_format(tomorrow, 'd/m')}"
    # As 16h caem na janela da casa que começa às 15h; a data sai por extenso, nunca em ISO.
    assert f"Retirada: {day}, a partir das 15h" in summary and "2 × “Croissant”" in summary, summary
    code = _code(summary)

    placed = _turn(conversation, f"confirmo {code}")

    order = Order.objects.get()
    assert placed[0].startswith(f"Pedido {order.ref} registrado."), placed
    assert (order.data["fulfillment_type"], order.data["delivery_date"], order.data["delivery_time_slot"]) == (
        "pickup", _tomorrow(), slot)
    assert [(item.sku, int(item.qty)) for item in order.items.all()] == [("CROISSANT", 2)]


def test_no_batch_on_the_day_says_so_and_offers_the_next_batch(conversation, outbox, shop):
    from shopman.stockman.models import Position, Quant
    from shopman.stockman.service import Stock

    from shopman.shop.policies.order_date_before_batch import batch_day_phrase

    for ready in Quant.objects.filter(sku="CROISSANT", _quantity__gt=0):
        Stock.issue(ready._quantity, ready, reason="ensaio: vendeu tudo hoje")
    later = date.today() + timedelta(days=3)
    Quant.objects.create(sku="CROISSANT", position=Position.objects.get(ref="loja"), target_date=later,
                         _quantity=Decimal("20"))

    reply = _say(conversation, FIRST, [_order(FIRST)])

    tomorrow = date.today() + timedelta(days=1)
    assert f"Não há fornada de Croissant {batch_day_phrase(tomorrow)}." in reply, reply
    assert f"A próxima sai {batch_day_phrase(later)}." in reply, reply
    assert "Indisponível" not in reply and "tirei" not in reply and "equipe" not in reply, reply
    assert not _session(conversation).items
