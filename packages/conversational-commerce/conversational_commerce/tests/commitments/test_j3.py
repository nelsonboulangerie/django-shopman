"""J3: verificar com a equipe e devolver; a promessa só com dono, e o prazo só quando alguém o define."""

from __future__ import annotations

from conversational_commerce.contracts import Known
from conversational_commerce.ports import TrustedContext
from conversational_commerce.testing.fakes import FakeWorld, Fault
from conversational_commerce.testing.journeys import j1, j3
from conversational_commerce.testing.journeys.runner import run_journey

from .helpers import CTX, engine, only_open

SHADOW = TrustedContext(tenant="tenant-a", environment="shadow")


def test_j3_verify_with_the_team_and_return_the_answer():
    turn_engine, world = engine()
    runs = run_journey(turn_engine, CTX, j3.STEPS)
    assert [run.problems for run in runs] == [(), ()]
    asked, answered = runs[0].result, runs[1].result
    # A promessa: dono (a fila do perfil), prazo (o de responder da fila) e a pergunta na equipe.
    (commitment,) = [r for _, r in world.store.records if getattr(r, "SCHEMA", "") == "cc.commitment"
                     and r.state == "open"]
    assert commitment.owner == "attendant" and commitment.deadline.status == "set"
    assert [q.question for q in world.staff.questions.values()] == ["ask_price: item.ITEM-Z"]
    assert world.staff.commitments[commitment.commitment_id].obligation.startswith("answer the customer")
    # A resposta volta como fato com autoria, e o compromisso se cumpre com ela como evidência.
    entry = turn_engine.commitments.entries[commitment.commitment_id]
    assert entry.commitment.state == "fulfilled" and entry.commitment.evidence == (entry.ticket_id,)
    assert turn_engine.commitments.events_of(commitment.commitment_id) == ["acknowledged", "fulfilled"]
    fact = answered.snapshot.facts["item.ITEM-Z"]
    assert isinstance(fact, Known) and fact.source == "staff:staff-1"
    assert answered.exposure is not None and answered.decision.decision_id != asked.decision.decision_id
    assert len(world.channel.outbox) == 2


def test_the_source_being_down_is_a_limitation_not_a_question_for_the_team():
    """J1 segue igual: fonte fora volta sozinha, e não se incomoda a equipe com isso."""
    turn_engine, world = engine(steps=j1.STEPS + (j1.UNKNOWN_STEP,))
    world.faults.arm("read_item", Fault.SOURCE_FAILED)
    result = turn_engine.turn(CTX, j1.UNKNOWN_STEP.message)
    assert result.chosen_moves == ["inform_limitation"]
    assert world.staff.calls == []


def test_without_a_possible_owner_nothing_is_promised():
    """N04 no turno: sem fila declarada, a limitação; nenhuma pergunta à equipe, nenhum compromisso."""
    turn_engine, world = engine(staff_queue=None)
    result = turn_engine.turn(CTX, j3.ASK.message)
    assert result.chosen_moves == ["inform_limitation"]
    assert world.staff.calls == [] and turn_engine.commitments.entries == {}
    assert "check with the team" not in result.text


def test_a_queue_that_refuses_the_question_leaves_no_promise():
    turn_engine, world = engine()
    world.faults.arm("ask", Fault.QUEUE_REJECTS)
    result = turn_engine.turn(CTX, j3.ASK.message)
    assert result.chosen_moves == ["inform_limitation"]
    assert "commitment_refused:queue_rejected" in result.fallbacks
    assert turn_engine.commitments.entries == {}
    assert result.decisions[-1].parent_decision_id == result.decisions[0].decision_id


def test_outside_business_hours_the_promise_states_no_deadline():
    world = FakeWorld()
    world.clock.advance(10 * 3600)  # 19:00, depois do fechamento
    turn_engine, _ = engine(world=world)
    result = turn_engine.turn(CTX, j3.ASK.message)
    assert result.chosen_moves == ["verify_with_staff"]
    assert result.text == "I'll check with our attendant and answer as soon as they can."
    deadline = only_open(turn_engine).commitment.deadline
    assert deadline.status == "absent" and deadline.absent_reason == "outside_business_hours"
    assert deadline.contingency == "inform_and_wait"


def test_shadow_decides_the_promise_and_never_calls_the_team():
    turn_engine, world = engine()
    result = turn_engine.turn(SHADOW, j3.ASK.message)
    assert result.outcome == "shadow" and result.chosen_moves == ["verify_with_staff"]
    assert "shadow:staff_not_called:verify_with_staff" in result.fallbacks
    assert world.staff.calls == [] and world.channel.outbox == {}
    assert turn_engine.commitments.entries == {}
