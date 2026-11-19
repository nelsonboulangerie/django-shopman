"""J1 e J2 de ponta a ponta sobre os falsos."""

from __future__ import annotations

from conversational_commerce.testing.fakes import Fault
from conversational_commerce.testing.journeys import j1, j2, run_journey

from .helpers import CTX, engine


def test_j1_product_question_answered_with_fact():
    turn_engine, world = engine(steps=j1.STEPS)
    results = run_journey(turn_engine, CTX, j1.STEPS)
    assert [r.problems for r in results] == [(), ()]
    first = results[0].result
    assert first.decision.candidates[first.decision.chosen[0]].move == "inform"
    assert first.reply.plan.parts[0].claims[0].backing == "fact"  # o preço tem lastro
    assert first.exposure is not None and first.exposure.state == "accepted"


def test_j1_unknown_does_not_become_a_sentence():
    steps = (*j1.STEPS, j1.UNKNOWN_STEP)
    turn_engine, world = engine(steps=steps)
    run_journey(turn_engine, CTX, j1.STEPS)
    world.faults.arm("read_item", Fault.SOURCE_FAILED)
    [result] = run_journey(turn_engine, CTX, [j1.UNKNOWN_STEP])
    assert result.problems == ()
    assert "XTS" not in result.result.text  # nenhum preço inventado
    assert "fact_unavailable" in next(c.blocked_by for c in result.result.decision.candidates if c.move == "inform")


def test_j2_ambiguous_request_clarified():
    turn_engine, world = engine(steps=j2.STEPS)
    results = run_journey(turn_engine, CTX, j2.STEPS)
    assert [r.problems for r in results] == [(), (), ()]
    asked, answer = results[0].result, results[1].result
    assert "ambiguous_change_ask_first" not in asked.decision.candidates[asked.decision.chosen[0]].blocked_by
    # O "sim" se ligou à pergunta da mesma época e a fechou.
    assert answer.snapshot.dialogue_state.get("open_question") is None
