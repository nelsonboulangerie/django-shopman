"""``decide``: admissível, prioritário, melhor; e os testes K04, K30, K31, K40."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.policy import AskEconomics, decide
from conversational_commerce.testing.conformance import conformance

from .helpers import (
    PROFILE,
    SNAPSHOT,
    STALE_FACT,
    UNKNOWN_FACT,
    blocked,
    chosen_moves,
    decision_input,
    proposal,
)


def test_deterministic_selection_is_not_applicable_never_probability_one():
    record = decide(decision_input(proposal("c1", "inform")))
    assert record.selection.method == "deterministic"
    assert record.selection.propensity.status == "not_applicable"
    assert record.selection.tie_break == "catalog_order"
    assert record.context.snapshot_hash == SNAPSHOT.hash
    assert (record.policy.id, record.profile.id) == ("moves", PROFILE.id)
    assert all(c.prediction.status == "unavailable" for c in record.candidates)


@conformance("K04", invariants=("N02",), scope="core")
@pytest.mark.parametrize("facts", [UNKNOWN_FACT, STALE_FACT], ids=["source_failed", "stale"])
def test_k04_critical_source_failed_or_stale_blocks_the_dependent_action(facts):
    record = decide(decision_input(
        proposal("c-inform", "inform", facts_needed=facts),
        proposal("c-verify", "verify_with_staff", facts_needed=facts),
    ))
    assert "fact_unavailable" in blocked(record, "c-inform")
    assert chosen_moves(record) == ["verify_with_staff"]  # pessoa, com promessa


@conformance("K30", scope="core")
def test_k30_two_readings_ask_on_a_change_cover_both_on_a_query():
    change = decide(decision_input(
        proposal("c-cart", "change_cart", request_kind="change", reading_count=2),
        proposal("c-ask", "ask_clarification", request_kind="change", reading_count=2),
    ))
    assert chosen_moves(change) == ["ask_clarification"]
    assert "ambiguous_change_ask_first" in blocked(change, "c-cart")

    query = decide(decision_input(
        proposal("c-inform", "inform", request_kind="query", reading_count=2),
        proposal("c-cover", "cover_readings", request_kind="query", reading_count=2),
    ))
    assert chosen_moves(query) == ["cover_readings"]
    assert "two_readings_cover_both" in blocked(query, "c-inform")


def test_cost_rule_can_say_act_on_a_change():
    confident = AskEconomics(top_probability="0.99", loss_if_wrong="10", cost_of_asking="1")
    cart = dataclasses.replace(proposal("c-cart", "change_cart", request_kind="change", reading_count=2),
                               economics=confident)
    record = decide(decision_input(cart, proposal("c-ask", "ask_clarification", request_kind="change",
                                                  reading_count=2)))
    assert chosen_moves(record) == ["change_cart"]  # (1 - 0,99) x 10 = 0,1 < 1: agir


@conformance("K31", invariants=("N19",), scope="core")
def test_k31_open_problem_or_high_friction_leaves_no_commercial_initiative():
    with_problem = decide(decision_input(
        proposal("c-case", "open_case", need="complaint"),
        proposal("c-reco", "recommend", need="n2"),
    ))
    assert chosen_moves(with_problem) == ["open_case"]
    assert "suspended_by_open_problem" in blocked(with_problem, "c-reco")

    friction = decide(decision_input(proposal("c-reco", "recommend", friction_high=True)))
    assert friction.chosen == ()
    assert "friction_high" in blocked(friction, "c-reco")


def test_complaint_and_question_are_two_needs_both_answered():
    record = decide(decision_input(
        proposal("c-case", "open_case", need="complaint"),
        proposal("c-inform", "inform", need="question"),
    ))
    assert sorted(chosen_moves(record)) == ["inform", "open_case"]


def test_family_priority_within_a_need():
    record = decide(decision_input(
        proposal("c-reco", "recommend"),
        proposal("c-inform", "inform"),
        proposal("c-ack", "acknowledge"),
    ))
    assert chosen_moves(record) == ["acknowledge"]  # resolve vence commerce; na família, a ordem do catálogo


def test_handoff_suspends_order_changes_elsewhere():
    record = decide(decision_input(
        proposal("c-handoff", "handoff", need="complaint"),
        proposal("c-cart", "change_cart", need="n2", request_kind="query", reading_count=1),
    ))
    assert "suspended_by_handoff" in blocked(record, "c-cart")


def test_one_commercial_initiative_per_decision():
    record = decide(decision_input(proposal("c-r1", "recommend", need="n1"), proposal("c-r2", "recommend", need="n2")))
    assert chosen_moves(record) == ["recommend"]
    assert "one_commercial_initiative" in blocked(record, "c-r2")


def test_move_outside_the_catalog_is_never_chosen():
    record = decide(decision_input(proposal("c-x", "transfer_all_funds")))
    assert record.chosen == () and blocked(record, "c-x") == ("move_outside_catalog",)


@conformance("K40", scope="core")
def test_k40_replaying_a_recorded_turn_with_the_same_policy_and_seed_gives_the_same_decision():
    inputs = (proposal("c-ack", "acknowledge"), proposal("c-inform", "inform"))
    assert decide(decision_input(*inputs)) == decide(decision_input(*inputs))
    first = decide(decision_input(*inputs, seed="seed-42"))
    again = decide(decision_input(*inputs, seed="seed-42"))
    assert first == again
    assert first.to_document() == again.to_document()


def test_unsealed_snapshot_is_refused():
    from conversational_commerce.policy import DecisionInput

    base = decision_input(proposal("c1", "inform"))
    with pytest.raises(ValueError):
        decide(DecisionInput(**{**{f.name: getattr(base, f.name) for f in dataclasses.fields(base)},
                                "snapshot": dataclasses.replace(SNAPSHOT, hash=None)}))
