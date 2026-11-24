"""A conferência de coerência e o verificador (ADR-051, peças 2 e 3).

Medido no ar (24/11/2026): com o horário da retirada perguntado, "vou buscar às 16h" foi lido como a pergunta do
horário da loja, e a Nice respondeu o horário de funcionamento. Com a pergunta no ar, a leitura que não a responde
nem muda de assunto vai ao verificador; na dúvida, a Nice pergunta "é isso?" em vez de agir.
"""

from __future__ import annotations

from conversational_commerce.engine.turn import coherence
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

LIMITS = {"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 2,
          "max_spend": {"amount_minor": 0, "currency": "XTS"}}
CONFERENCE = {"limits": {**LIMITS, "max_adjudications_per_turn": 1}}
AT_FOUR = {"act": "choose_fulfillment", "fields": {"time": "16:00"}}
HOURS = {"act": "ask_hours", "fields": {}}


def _step(mid, acts, **extra):
    return JourneyStep(message=j4.message(mid, mid), understanding={"acts": list(acts), **extra},
                       expect_moves=(), expect_text=(), advance_seconds=30)


CLOSE = _step("close", [{"act": "place_order"}])
TOMORROW = _step("tomorrow", [{"act": "choose_fulfillment", "fields": {"date": "2026-01-06"}}])
PICKUP = _step("pickup", [{"act": "choose_fulfillment", "fields": {"mode": "pickup"}}])
YES = _step("yes", [{"act": "affirm"}])
NO = _step("no", [{"act": "deny"}])
ASKED_TIME = (CLOSE, TOMORROW, PICKUP)  # a Nice acabou de perguntar o horário da retirada


def _run(*steps, overrides=CONFERENCE):
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    world.state.pickup_slots = ("9h às 12h", "15h às 18h")
    turn_engine, world = engine(steps=steps, world=world, profile_overrides=overrides)
    results = [r.result for r in run_journey(turn_engine, CTX, list(steps))]
    return results, world, turn_engine.ports.model


def test_the_classes_of_a_reading_before_the_question_in_the_air():
    from conversational_commerce.contracts import Act

    def acts(*names):
        return [Act(act=name, fields={}, confidence={"status": "unavailable", "reason": "test"}) for name in names]

    expected = ("choose_fulfillment",)
    assert coherence(acts("choose_fulfillment"), expected) == "answers"
    assert coherence(acts("change_quantity"), expected) == "rupture"  # "põe mais um croissant": legítimo
    assert coherence(acts("ask_hours"), expected) == "suspect"
    assert coherence(acts("greet", "unknown"), expected) == "suspect"
    assert coherence(acts("ask_hours"), ()) == "free"  # nada no ar: a frase se lê sozinha


def test_the_verifier_picks_the_reading_that_answers_the_question():
    """O leitor leu "horário da loja" e deu a hora da retirada como alternativa: o verificador escolhe a segunda."""
    four = _step("four", [HOURS], alternatives=[[AT_FOUR]], adjudication=1)
    (*_, time), world, model = _run(*ASKED_TIME, four)
    assert world.state.fulfillment["cart-1"]["time"] == "16:00"
    assert "conference:suspect:disagreement" in time.fallbacks and "adjudicate:chose:1" in time.fallbacks
    [request] = model.adjudications
    assert request.context.pending.code == "delivery_time_slot"  # o verificador vê a pergunta no ar
    assert [[act.act for act in c.acts] for c in request.candidates] == [["ask_hours"], ["choose_fulfillment"]]


def test_in_doubt_the_agent_asks_is_it_this_and_the_yes_applies_it():
    four = _step("four", [HOURS], alternatives=[[AT_FOUR]])  # o verificador não escolhe
    (*_, time, yes), world, _ = _run(*ASKED_TIME, four, YES)
    assert time.reply.template_ids == ("ask_clarification.confirm_reading",)
    assert "choose_fulfillment time=16:00" in time.text  # o que o cliente disse, repetido (lastro: a leitura)
    assert not time.commands  # na dúvida, nada se aplica
    assert world.state.fulfillment["cart-1"]["time"] == "16:00"  # o "sim" aplicou a leitura confirmada
    assert "conference:confirmed" in yes.fallbacks
    assert yes.reply.template_ids[-1] == "present_terms.confirm"


def test_no_to_the_confirmation_asks_the_close_question_again():
    four = _step("four", [HOURS], alternatives=[[AT_FOUR]])
    (*_, no), world, _ = _run(*ASKED_TIME, four, NO)
    assert no.reply.template_ids[-1] == "present_terms.needs_delivery_time_slot"
    assert "time" not in world.state.fulfillment["cart-1"]


def test_in_doubt_without_a_reading_that_answers_the_close_question_comes_back():
    four = _step("four", [HOURS])
    (*_, time), world, model = _run(*ASKED_TIME, four)
    assert time.reply.template_ids[-1] == "present_terms.needs_delivery_time_slot"
    assert len(model.adjudications) == 1 and "adjudicate:doubt" in time.fallbacks


def test_a_change_of_subject_and_an_answer_are_not_judged():
    more = _step("more", [{"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}}])
    four = _step("four", [AT_FOUR])
    (*_, changed), _, model = _run(*ASKED_TIME, more)
    assert model.adjudications == [] and not any(f.startswith("conference") for f in changed.fallbacks)
    (*_, answered), _, model = _run(*ASKED_TIME, four)
    assert model.adjudications == [] and answered.reply.template_ids[-1] == "present_terms.confirm"


def test_the_conference_is_off_without_the_profile_ceiling():
    four = _step("four", [HOURS], alternatives=[[AT_FOUR]], adjudication=1)
    (*_, time), world, model = _run(*ASKED_TIME, four, overrides={"limits": LIMITS})
    assert model.adjudications == [] and "time" not in world.state.fulfillment["cart-1"]
    assert not any(f.startswith("conference") for f in time.fallbacks)
