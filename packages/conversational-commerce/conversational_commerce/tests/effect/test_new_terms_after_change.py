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



def test_yes_and_a_change_in_one_turn_present_the_new_terms_once_in_any_order():
    """As duas portas juntas: "sim, e põe quatro" e "põe quatro, sim" mudam a sacola e apresentam os termos
    novos UMA vez; nenhum pedido é gravado pelos termos de antes, e nenhuma limitação é dita."""
    four = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "4"}}
    for acts in ([{"act": "affirm"}, four], [four, {"act": "affirm"}]):
        step = JourneyStep(message=j4.message("j4-both", "yes and four"), understanding={"acts": acts},
                           expect_moves=(), expect_text=(), advance_seconds=30)
        turn_engine, world = engine(steps=(j4.CHANGE, j4.QUOTE, step, YES))
        results = run_journey(turn_engine, CTX, [j4.CHANGE, j4.QUOTE, step, YES])
        both = results[2].result
        assert [c.action for c in both.commands] == ["change_cart"] and world.state.carts["cart-1"] == {"ITEM-A": "4"}
        assert both.reply.template_ids == ("present_terms.confirm",), acts  # o resumo novo, uma vez
        assert "can't" not in both.text and "4 × Item A" in both.text
        assert len(world.state.orders) == 1  # só o "sim" seguinte grava, pelos termos novos


# ── revisão do #3389 ─────────────────────────────────────────────────────────────────


def _four_with(*acts, arm=None):
    step = JourneyStep(message=j4.message("j4-rev", "rev"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)
    turn_engine, world = engine(steps=(j4.CHANGE, j4.QUOTE, step))
    run_journey(turn_engine, CTX, [j4.CHANGE, j4.QUOTE])
    if arm is not None:
        arm(world)
    world.clock.advance(30)
    return turn_engine.turn(CTX, step.message), world, turn_engine


FOUR_ACT = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "4"}}


def test_a_failed_requote_under_the_offer_answers_the_effect_and_retires_the_offer():
    """1. A cotação depois da mudança falha: o documento velho não serve, o efeito é dito pelo degrau de
    baixo, e a pergunta dos termos sai do ar (o "sim" seguinte não confirma os termos velhos)."""
    from conversational_commerce.testing.fakes import Fault

    result, world, turn_engine = _four_with(FOUR_ACT, arm=lambda w: w.faults.arm("quote", Fault.PROVIDER_DOWN))
    assert [c.action for c in result.commands] == ["change_cart"] and world.state.carts["cart-1"] == {"ITEM-A": "4"}
    assert result.reply.verification.result == "pass"
    assert result.reply.template_ids == ("change_cart.done_receipt",)
    assert result.episode.state == "active"
    yes = turn_engine.turn(CTX, YES.message)  # o "sim" de depois não fecha os termos velhos
    assert "commit_order" not in [c.action for c in yes.commands] and world.state.orders == {}


def test_yes_with_a_failed_change_is_never_an_impossible_limitation():
    """2a. A mudança junto do "sim" falha: o "sim" não foi impossível, só espera a sacola."""
    from conversational_commerce.testing.fakes import Fault

    result, world, _ = _four_with({"act": "affirm"}, FOUR_ACT,
                                  arm=lambda w: w.faults.arm("execute", Fault.EFFECT_PENDING))
    assert world.state.orders == {}
    assert "inform_limitation.offer_team" not in result.reply.template_ids
    assert "inform_limitation.confirm_after_change" in result.reply.template_ids


def test_a_relative_line_with_yes_never_blocks_the_order():
    """2b. "Põe mais um, sim": a linha relativa não é mudança elegível; o "sim" segue."""
    more = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "1", "relative": True}}
    result, world, _ = _four_with(more, {"act": "affirm"})
    assert [c.action for c in result.commands] == ["commit_order"] and len(world.state.orders) == 1
