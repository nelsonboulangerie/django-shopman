from __future__ import annotations

import dataclasses

from conversational_commerce.catalog import Situation
from conversational_commerce.contracts import ContextSnapshot, Known, Unknown
from conversational_commerce.policy import DecisionInput, Proposal
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.tests.catalog.situations import BASE, NOW
from conversational_commerce.tests.contracts.examples import context_snapshot

SNAPSHOT = ContextSnapshot.from_document(context_snapshot())
PROFILE = build_test_profile()


def situation(**changes) -> Situation:
    """A situação feliz do catálogo, com uma leitura só (sem ambiguidade) por padrão."""
    return dataclasses.replace(Situation(**BASE), **{"reading_count": 1, **changes})


def proposal(ref: str, move: str, need: str = "n1", content=None, **situation_changes) -> Proposal:
    return Proposal(candidate_ref=ref, need_id=need, move=move, content=content or {"ref": ref},
                    situation=situation(**situation_changes))


def decision_input(*proposals: Proposal, profile=PROFILE, seed=None, decision_id="dec-1") -> DecisionInput:
    return DecisionInput(decision_id=decision_id, record_id=f"rec-{decision_id}", trace_id="trace-1",
                         occurred_at=NOW, turn=3, snapshot=SNAPSHOT, profile=profile, proposals=tuple(proposals),
                         seed=seed)


UNKNOWN_FACT = {"opening_hours": Unknown(reason="source_failed")}
STALE_FACT = {"opening_hours": Known(value="07:00-19:00", source="commerce", observed_at="2026-11-18T10:00:00.000000Z",
                                     valid_until="2026-11-18T13:00:00.000000Z")}


def chosen_moves(record) -> list[str]:
    return [record.candidates[i].move for i in record.chosen]


def blocked(record, ref: str) -> tuple[str, ...]:
    return next(c.blocked_by for c in record.candidates if c.candidate_ref == ref)
