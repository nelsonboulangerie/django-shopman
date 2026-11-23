"""Várias linhas num turno são uma mudança só: um comando, atômico, com um recibo (spec 08 §5, [DECIDIDO]).

"2 itens A e 1 item B" não vira dois efeitos (o segundo seria recusado por ``one_effect_per_turn``):
a primeira necessidade de mudança leva o comando com todas as linhas, e as outras são levadas por ela.
"""

from __future__ import annotations

from conversational_commerce.testing.journeys import j4
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _step(*acts, mid="lines-1"):
    return JourneyStep(message=j4.message(mid, "two lines"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=())


A3 = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}}
B1 = {"act": "change_quantity", "fields": {"item": "ITEM-B", "quantity": "1"}}


def test_two_lines_are_one_command_with_one_receipt_and_one_reply():
    step = _step(A3, B1)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert len(result.commands) == 1 and len(result.receipts) == 1
    assert [dict(line) for line in result.commands[0].parameters["lines"]] == [
        {"item": "ITEM-A", "quantity": "3"}, {"item": "ITEM-B", "quantity": "1"}]
    assert world.state.carts["cart-1"] == {"ITEM-A": "3", "ITEM-B": "1"}
    assert world.commerce_execute.effects == 1
    assert result.chosen_moves == ["change_cart", "change_cart"]  # as duas necessidades, atendidas
    assert result.reply.template_ids == ("change_cart.done",)  # uma resposta só, com a sacola inteira
    assert "one_effect_per_turn" not in str(result.fallbacks)


def test_a_relative_line_makes_the_whole_change_ineligible():
    step = _step(A3, {"act": "change_quantity", "fields": {"item": "ITEM-B", "quantity": "1", "relative": True}})
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert result.commands == () and world.commerce_execute.effects == 0  # tudo ou nada


def test_the_same_turn_twice_applies_once():
    step = _step(A3, B1)
    turn_engine, world = engine(steps=(step,))
    turn_engine.turn(CTX, step.message)
    again = turn_engine.turn(CTX, step.message)
    assert again.outcome == "duplicate" and world.commerce_execute.effects == 1


def test_a_different_effect_in_the_same_turn_is_still_refused():
    """A regra continua para efeitos diferentes: um comando por turno (a intenção é gravada antes, N13)."""
    fulfillment = {"act": "choose_fulfillment", "fields": {"mode": "delivery"}}
    step = _step(A3, fulfillment)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert len(result.commands) == 1 and result.commands[0].action == "change_cart"
    assert "cart-1" not in world.state.fulfillment
