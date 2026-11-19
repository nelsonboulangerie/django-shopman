"""J6: recomendação pela necessidade explícita, e a recusa que segura nova oferta até o cliente mudar de ideia."""

from __future__ import annotations

from conversational_commerce.engine.turn import OFFERS_DECLINED
from conversational_commerce.ports import TrustedContext
from conversational_commerce.testing.journeys import j5, j6
from conversational_commerce.testing.journeys.runner import JourneyStep, run_journey

from .helpers import CTX, engine

SHADOW = TrustedContext(tenant="tenant-a", environment="shadow")


def blocked(result, move):
    return next(c.blocked_by for c in result.decision.candidates if c.move == move)


def test_j6_recommendation_by_explicit_need_and_refusal_respected():
    turn_engine, world = engine()
    runs = run_journey(turn_engine, CTX, j6.STEPS)
    assert [run.problems for run in runs] == [()] * 5
    # Enquanto a recusa vale, a oferta fica inelegível pela recusa, com código.
    assert "customer_declined_offers" in blocked(runs[2].result, "recommend")
    # A recusa e a mudança de ideia são memória declarada: a segunda substitui a primeira.
    first, second = turn_engine.memory.history
    assert (first.value, second.value) == (True, False) and second.supersedes == first.memory_id
    assert first.evidence_state == "declared" and first.source == runs[1].result.event.id
    subject = runs[0].result.episode.subject
    assert turn_engine.memory.value(subject, OFFERS_DECLINED, world.clock.now()) is False


def test_recommendation_name_and_price_come_from_the_item_fact():
    turn_engine, world = engine()
    result = turn_engine.turn(CTX, j6.ASK.message)
    (part,) = result.reply.plan.parts
    assert {claim.backing for claim in part.claims} == {"fact"}
    assert {claim.ref for claim in part.claims} == {"item.ITEM-C"}


def test_no_item_meets_the_declared_need_means_no_recommendation():
    nothing = JourneyStep(message=j6.message("j6-x", "suggest something by the litre"),
                          understanding={"acts": [{"act": "ask_recommendation", "fields": {"need": {"unit": "l"}}}]},
                          expect_moves=("inform_limitation",))
    turn_engine, _ = engine(steps=(nothing,))
    result = turn_engine.turn(CTX, nothing.message)
    assert result.chosen_moves == ["inform_limitation"]
    assert "advisor_constraint" in blocked(result, "recommend")


def test_without_a_declared_need_there_is_nothing_to_adhere_to():
    vague = JourneyStep(message=j6.message("j6-v", "suggest something"),
                        understanding={"acts": [{"act": "ask_recommendation"}]}, expect_moves=("inform_limitation",))
    turn_engine, _ = engine(steps=(vague,))
    result = turn_engine.turn(CTX, vague.message)
    assert {"need_not_explicit", "advisor_constraint"} <= set(blocked(result, "recommend"))


def test_open_case_in_the_episode_holds_every_offer():
    """Problema aberto num turno anterior ainda trava a oferta (K31 ao longo do episódio)."""
    complaint = JourneyStep(message=j6.message("j6-c", "wrong order"), understanding=j5.COMPLAINT_AND_QUESTION
                            .understanding, expect_moves=("open_case", "inform"))
    turn_engine, _ = engine(steps=(complaint, j6.ASK))
    turn_engine.turn(CTX, complaint.message)
    result = turn_engine.turn(CTX, j6.ASK.message)
    assert result.chosen_moves == ["inform_limitation"]
    assert "open_problem" in blocked(result, "recommend")


def test_shadow_remembers_nothing():
    turn_engine, _ = engine()
    turn_engine.turn(SHADOW, j6.DECLINE.message)
    assert turn_engine.memory.history == []
