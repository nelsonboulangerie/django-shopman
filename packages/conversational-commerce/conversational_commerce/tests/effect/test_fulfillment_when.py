"""O quando antes dos termos (#3482): o dia, retirar ou entregar, e o horário, na ordem do fechamento.

Sem isso, os termos se apresentavam sem o que o sistema de registro exige para gravar ("Posso registrar?" de
um pedido sem dia nem horário), e o "sim" do cliente não fechava nada.
"""

from __future__ import annotations

from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _step(mid, *acts, text=None):
    return JourneyStep(message=j4.message(mid, text or mid), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)


CLOSE = _step("close", {"act": "place_order"})
TOMORROW = _step("tomorrow", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06"}})
PICKUP = _step("pickup", {"act": "choose_fulfillment", "fields": {"mode": "pickup"}})
AT_FOUR = _step("four", {"act": "choose_fulfillment", "fields": {"time": "16:00"}})
YES = _step("yes", {"act": "affirm"})


def _world():
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    world.state.pickup_slots = ("9h às 12h", "15h às 18h")
    return world


def test_the_close_asks_the_day_then_the_mode_then_the_time_and_only_then_presents_the_terms():
    steps = (CLOSE, TOMORROW, PICKUP, AT_FOUR, YES)
    turn_engine, world = engine(steps=steps, world=_world())
    close, day, mode, time, yes = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.needs_fulfillment_date",)
    assert day.reply.template_ids[-1] == "present_terms.needs_fulfillment_type"  # a resposta volta aos termos
    assert mode.reply.template_ids[-1] == "present_terms.needs_delivery_time_slot"
    assert "9h às 12h" in mode.text and "15h às 18h" in mode.text  # os horários do fato
    assert time.reply.template_ids[-1] == "present_terms.confirm"  # só agora os termos
    assert [c.action for c in yes.commands] == ["commit_order"]
    assert world.state.fulfillment["cart-1"] == {"date": "2026-01-06", "mode": "pickup", "time": "16:00"}


def test_what_was_said_with_the_order_is_not_asked_again():
    said = _step("all", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06", "mode": "pickup",
                                                                 "time": "16:00"}})
    steps = (said, CLOSE)
    turn_engine, world = engine(steps=steps, world=_world())
    _said, close = (r.result for r in run_journey(turn_engine, CTX, list(steps)))
    assert close.reply.template_ids == ("present_terms.confirm",)


def test_without_pickup_slots_the_fake_channel_does_not_ask_the_when():
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    turn_engine, world = engine(steps=(CLOSE,), world=world)
    assert turn_engine.turn(CTX, CLOSE.message).reply.template_ids == ("present_terms.confirm",)
