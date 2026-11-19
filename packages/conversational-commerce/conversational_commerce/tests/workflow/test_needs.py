"""Necessidades: satisfeita com evidência, retirada nunca por silêncio, bloqueada segura as dependentes."""

from __future__ import annotations

import dataclasses

import pytest

from conversational_commerce.workflow import InvalidTransition, actionable, held_by_blocked, update_need

from .helpers import T1, need


def test_satisfied_needs_evidence():
    with pytest.raises(InvalidTransition, match="evidência"):
        update_need(need("n1", "open"), "satisfied", record_id="r", at=T1)
    done = update_need(need("n1", "open"), "satisfied", record_id="r", at=T1, evidence=("receipt-1",))
    assert done.state == "satisfied" and "receipt-1" in done.evidence


def test_withdrawn_is_never_silence():
    with pytest.raises(InvalidTransition, match="silêncio"):
        update_need(need("n1", "open"), "withdrawn", record_id="r", at=T1, evidence=("evt-3",))
    gone = update_need(need("n1", "open"), "withdrawn", record_id="r", at=T1, evidence=("evt-3",),
                       withdrawn_by="customer_act")
    assert gone.state == "withdrawn"


def test_need_can_come_back():
    again = update_need(need("n1", "satisfied"), "open", record_id="r", at=T1)
    assert (again.state, again.evidence) == ("open", ())
    with pytest.raises(InvalidTransition):
        update_need(need("n1", "satisfied"), "blocked", record_id="r", at=T1)


def test_blocked_holds_its_dependents_transitively():
    a = need("a", "blocked")
    b = dataclasses.replace(need("b", "open"), depends_on=("a",))
    c = dataclasses.replace(need("c", "open"), depends_on=("b",))
    d = need("d", "open")
    assert held_by_blocked((a, b, c, d)) == {"b", "c"}
    assert [n.need_id for n in actionable((a, b, c, d))] == ["d"]


def test_complaint_does_not_erase_the_question():
    """Duas necessidades na mesma entrada: as duas seguem acionáveis."""
    complaint = dataclasses.replace(need("complaint", "open"), type="complaint")
    question = need("question", "open")
    assert {n.need_id for n in actionable((complaint, question))} == {"complaint", "question"}
