"""J5 e K19: reclamação e dúvida na mesma mensagem."""

from __future__ import annotations

from conversational_commerce.catalog import MOVES
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.journeys import j5
from conversational_commerce.testing.journeys.runner import run_journey

from .helpers import CTX, engine, only_open


@conformance("K19", invariants=("N15", "N19"), scope="core")
def test_k19_complaint_and_question_two_needs_question_answered_case_owned_no_offer():
    turn_engine, world = engine()
    (run,) = run_journey(turn_engine, CTX, j5.STEPS)
    assert run.problems == ()
    result = run.result
    # Duas necessidades, cada uma com a sua resposta: a reclamação não apaga a dúvida.
    assert [c.need_id for c in (result.decision.candidates[i] for i in result.decision.chosen)] == ["n1", "n2"]
    # O caso: código do problema, solução pedida, dono e prazo.
    case = only_open(turn_engine).commitment
    assert case.type == "case" and case.problem_code == "wrong_order" and case.requested_resolution == "replacement"
    assert case.owner == "attendant" and case.deadline.status == "set"
    assert world.staff.commitments[case.commitment_id].type == "case"
    # Nenhuma oferta: nada da família comercial escolhido.
    assert all(MOVES[move].family != "commerce" for move in result.chosen_moves)
    # O caso aberto segura o episódio: nada o resolve sem o caso cumprido (N15).
    assert result.episode.state == "active" and result.episode.resolved_at is None


def test_the_case_outranks_the_limitation_for_the_complaint():
    turn_engine, _ = engine()
    result = turn_engine.turn(CTX, j5.COMPLAINT_AND_QUESTION.message)
    moves = {c.move for c in result.decision.candidates if c.need_id == "n1"}
    assert "inform_limitation" not in moves and "open_case" in moves


def test_without_a_queue_the_complaint_is_a_limitation():
    turn_engine, world = engine(staff_queue=None)
    result = turn_engine.turn(CTX, j5.COMPLAINT_AND_QUESTION.message)
    assert result.chosen_moves == ["inform_limitation", "inform"]
    assert world.staff.calls == []
