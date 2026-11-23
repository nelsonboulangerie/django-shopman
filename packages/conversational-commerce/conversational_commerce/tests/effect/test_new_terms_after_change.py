"""Mudar a sacola com o resumo no ar apresenta o resumo novo (v2 4.7, propriedade 2; #3381).

"Pode fechar" → resumo → "na verdade 4": a mudança executa, os termos de antes deixam de valer, e
a decisão refeita (ligada à anterior, N14) apresenta os termos novos. O "sim" seguinte responde ao
documento novo e fecha o pedido com 4, nunca com o de antes nem com um agradecimento.
"""

from __future__ import annotations

from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

FOUR = JourneyStep(message=j4.message("j4-four", "make it four"),
                   understanding={"acts": [{"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "4"}}]},
                   expect_moves=("present_terms",), expect_text=("4 × Item A", "Shall I place the order?"),
                   expect_state="waiting_authorization", advance_seconds=30)
YES = JourneyStep(message=j4.message("j4-yes-again", "yes"), understanding={"acts": [{"act": "affirm"}]},
                  expect_moves=("commit_order",), expect_text=("is placed",), expect_state="active",
                  advance_seconds=30)


def test_a_change_under_the_offer_presents_the_new_terms_and_the_yes_places_them():
    turn_engine, world = engine(steps=(j4.CHANGE, j4.QUOTE, FOUR, YES))
    results = run_journey(turn_engine, CTX, [j4.CHANGE, j4.QUOTE, FOUR, YES])
    assert [r.problems for r in results] == [(), (), (), ()]
    changed = results[2].result
    assert [c.action for c in changed.commands] == ["change_cart"]  # a mudança executou
    assert len(changed.decisions) == 2  # e a decisão foi refeita sobre os termos novos
    assert changed.decisions[1].parent_decision_id == changed.decisions[0].decision_id
    assert world.state.carts["cart-1"] == {"ITEM-A": "4"} and len(world.state.orders) == 1
    order = next(iter(world.state.orders.values()))
    assert order["terms_hash"] == results[3].result.commands[0].terms_hash  # o pedido é o dos termos novos


def test_without_an_offer_a_change_still_answers_with_the_cart():
    turn_engine, _ = engine()
    [changed] = run_journey(turn_engine, CTX, [j4.CHANGE])
    assert changed.result.chosen_moves == ["change_cart"]
