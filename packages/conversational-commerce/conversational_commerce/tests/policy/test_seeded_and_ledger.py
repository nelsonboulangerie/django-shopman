"""Seleção sorteada (só com a linha do perfil) e K32: bloqueio posterior gera decisão nova ligada."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from conversational_commerce.ledger import DecisionLedger, LedgerError, redecide_after_block
from conversational_commerce.policy import decide, uniform_weights
from conversational_commerce.testing.conformance import conformance

from .helpers import PROFILE, chosen_moves, decision_input, proposal

POOL = (proposal("c-ack", "acknowledge"), proposal("c-inform", "inform"))


def test_uniform_weights_sum_to_exactly_one():
    for count in range(1, 8):
        weights = uniform_weights(count)
        assert sum(weights) == Decimal(1)
        assert len(weights) == count


def test_seeded_needs_the_approved_profile_line():
    lines = tuple(line for line in PROFILE.lines if line.id != "policy.seeded_selection")
    with pytest.raises(ValueError, match="policy.seeded_selection"):
        decide(decision_input(*POOL, profile=dataclasses.replace(PROFILE, lines=lines), seed="s"))


def test_seeded_decides_one_need_at_a_time():
    with pytest.raises(ValueError, match="uma necessidade"):
        decide(decision_input(proposal("a", "inform", need="n1"), proposal("b", "inform", need="n2"), seed="s"))


def test_seeded_records_distribution_after_filters_and_executed_probability():
    record = decide(decision_input(*POOL, proposal("c-reco", "recommend", friction_high=True), seed="seed-7"))
    propensity = record.selection.propensity
    assert record.selection.method == "seeded" and propensity.seed == "seed-7"
    eligible = {i for i, c in enumerate(record.candidates) if c.eligible}
    assert {w.candidate for w in propensity.distribution} <= eligible  # bloqueada fica fora da distribuição
    assert propensity.executed_probability == "0.5"


@conformance("K32", invariants=("N14", "N17"), scope="core")
def test_k32_seeded_decision_then_a_guard_blocks_it_new_linked_decision():
    ledger = DecisionLedger()
    original = ledger.append(decide(decision_input(*POOL, seed="seed-7")))
    picked = original.candidates[original.chosen[0]]
    substitute = redecide_after_block(original, blocked_candidate_ref=picked.candidate_ref, reason="authority_revoked",
                                      decision_id="dec-2", record_id="rec-dec-2",
                                      occurred_at="2026-11-18T14:01:00.000000Z")
    ledger.append(substitute)
    # A original não foi reescrita: distribuição e probabilidade seguem lá.
    assert ledger.get("dec-1") == original
    assert original.selection.propensity.status == "recorded"
    # A nova aponta a mãe, mostra o bloqueio e não herda a probabilidade.
    assert substitute.parent_decision_id == "dec-1"
    assert "authority_revoked" in substitute.candidates[original.chosen[0]].blocked_by
    assert substitute.selection.propensity.status == "not_applicable"
    assert chosen_moves(substitute) and picked.move not in chosen_moves(substitute)
    assert [r.decision_id for r in ledger.lineage("dec-2")] == ["dec-1", "dec-2"]


def test_ledger_only_appends():
    ledger = DecisionLedger()
    record = ledger.append(decide(decision_input(*POOL)))
    with pytest.raises(LedgerError):
        ledger.append(record)
    orphan = dataclasses.replace(record, decision_id="dec-9", parent_decision_id="dec-unknown")
    with pytest.raises(LedgerError):
        ledger.append(orphan)


def test_only_a_chosen_candidate_can_be_blocked_later():
    record = decide(decision_input(*POOL))
    not_chosen = next(c.candidate_ref for i, c in enumerate(record.candidates) if i not in record.chosen)
    with pytest.raises(LedgerError):
        redecide_after_block(record, blocked_candidate_ref=not_chosen, reason="x", decision_id="d2", record_id="r2",
                             occurred_at="2026-11-18T14:01:00.000000Z")
