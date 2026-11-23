"""Meta-teste que varre o catálogo: todo movimento tem precondição, e cada uma tem um teste que a faz falhar."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.catalog import CATALOG, FAMILIES, GENERIC, MOVES, SPECIFIC, evaluate_move

from .situations import BREAKERS, happy

PAIRS = [(move.name, precondition.code) for move in CATALOG for precondition in move.preconditions]


def test_the_catalog_has_the_seventeen_moves_of_the_plan():
    assert [move.name for move in CATALOG] == [
        "acknowledge", "inform", "cover_readings", "inform_limitation", "ask_clarification", "verify_with_staff",
        "open_case", "handoff", "wait", "present_terms", "change_cart", "set_fulfillment",
        "commit_order", "cancel_order",
        "amend_order", "grant_discount", "recommend",
    ]
    assert FAMILIES == ("protect_and_fulfill", "resolve", "clarify", "commerce", "follow_up")


@pytest.mark.parametrize("move", CATALOG, ids=lambda m: m.name)
def test_every_move_has_its_own_precondition(move):
    assert move.specific, f"{move.name} sem precondição própria"
    assert move.authority != "A5", "o catálogo não tem movimento proibido à automação"


def test_every_precondition_is_used_and_has_a_breaker():
    used = {code for move in CATALOG for code in move.specific}
    assert used == set(SPECIFIC), f"precondição sem movimento: {sorted(set(SPECIFIC) - used)}"
    every = set(SPECIFIC) | {precondition.code for precondition in GENERIC}
    missing = sorted(every - set(BREAKERS))
    assert not missing, f"precondição sem teste que a faça falhar: {missing}"


@pytest.mark.parametrize("move", CATALOG, ids=lambda m: m.name)
def test_happy_situation_makes_the_move_eligible(move):
    evaluation = evaluate_move(move, *happy(move.name))
    assert evaluation.eligible, evaluation.blocked_by
    assert [result.code for result in evaluation.results] == [p.code for p in move.preconditions]
    assert all(result.result == "pass" for result in evaluation.results)


@pytest.mark.parametrize(("move_name", "code"), PAIRS)
def test_breaking_one_precondition_blocks_the_move(move_name, code):
    situation, profile = BREAKERS[code](happy(move_name), move_name)
    evaluation = evaluate_move(move_name, situation, profile)
    result = next(result for result in evaluation.results if result.code == code)
    assert result.result == "fail", (code, evaluation)
    assert not evaluation.eligible
    assert result.evidence["reason"] in evaluation.blocked_by


@pytest.mark.parametrize(
    ("move_name", "code"),
    [(m.name, p.code) for m in CATALOG for p in m.preconditions if p.reads],
)
def test_unknown_input_blocks_and_says_so(move_name, code):
    situation, profile = happy(move_name)
    precondition = next(p for p in MOVES[move_name].preconditions if p.code == code)
    if precondition.reads == ("identity",):
        pytest.skip("identidade nunca é desconhecida: o degrau mais baixo é anonymous")
    situation = dataclasses.replace(situation, **{precondition.reads[0]: None})
    evaluation = evaluate_move(move_name, situation, profile)
    result = next(result for result in evaluation.results if result.code == code)
    assert result.result == "unknown"
    assert f"{code}_unknown" in evaluation.blocked_by
    assert not evaluation.eligible


def test_every_failure_is_recorded_not_just_the_first():
    situation, profile = happy("recommend")
    situation = dataclasses.replace(situation, need_explicit=False, open_problem=True, customer_declined_offers=True)
    evaluation = evaluate_move("recommend", situation, profile)
    assert evaluation.blocked_by == ("need_not_explicit", "open_problem", "customer_declined_offers")


def test_move_outside_the_catalog_is_not_evaluable():
    with pytest.raises(KeyError):
        evaluate_move("delete_everything", *happy("inform"))
