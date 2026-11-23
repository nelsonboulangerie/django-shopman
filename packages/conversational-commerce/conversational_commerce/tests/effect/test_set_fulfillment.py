"""Recebimento: dia, retirada ou entrega, janela ou hora, como efeito reversível no carrinho (A2).

O ato ``choose_fulfillment`` vira o movimento ``set_fulfillment``: concessão pela
linha do perfil, comando ``set_fulfillment`` no carrinho do sujeito, recibo com o
recebimento depois do efeito, e a resposta pelo molde que o recibo sustenta.
"""

from __future__ import annotations

import dataclasses

from conversational_commerce.engine.moves.set_fulfillment import is_absolute
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.fakes.commerce import FakeCommerceExecute, fulfillment_problem
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

# O relógio sintético começa em 2026-01-05: amanhã é 2026-01-06.
TOMORROW = "2026-01-06"


def step(mid: str, fields, *, moves=("set_fulfillment",), text=(), alternatives=None) -> JourneyStep:
    understanding = {"acts": [{"act": "choose_fulfillment", "fields": fields}]}
    if alternatives is not None:
        understanding["alternatives"] = [[{"act": "choose_fulfillment", "fields": alternatives}]]
    return JourneyStep(message=j4.message(mid, f"fulfillment {mid}"), understanding=understanding,
                       expect_moves=moves, expect_text=text)


def run(*steps, world=None):
    turn_engine, world = engine(steps=steps, world=world)
    results = run_journey(turn_engine, CTX, steps)
    assert [r.problems for r in results] == [()] * len(steps)
    return [r.result for r in results], world


def test_date_mode_and_time_are_applied_with_a_line_grant():
    [result], world = run(step("f1", {"date": TOMORROW, "mode": "pickup", "time": "16:00"},
                               text=(f"Done: pickup on {TOMORROW} at 16:00.",)))
    grant, command, receipt = result.grants[0], result.commands[0], result.receipts[0]
    assert grant.basis == "profile_line" and grant.action == "set_fulfillment"
    assert command.action == "set_fulfillment" and command.targets == ("cart-1",)
    assert dict(command.parameters) == {"date": TOMORROW, "mode": "pickup", "time": "16:00"}
    assert (receipt.status, receipt.effect) == ("success", "applied")
    assert {k: receipt.domain_refs[k] for k in ("date", "mode", "time")} == dict(command.parameters)
    assert world.state.fulfillment["cart-1"] == {"date": TOMORROW, "mode": "pickup", "time": "16:00"}
    assert result.reply.plan.parts[0].claims[0].backing == "receipt"  # o efeito afirmado tem recibo


def test_window_reaches_the_reply_through_the_house_formatter():
    steps = (step("f1", {"date": TOMORROW, "mode": "delivery", "window": "window-afternoon"}),)
    turn_engine, world = engine(steps=steps)
    labels = {"window-afternoon": "between noon and six"}
    turn_engine.formatters = {**turn_engine.formatters, "window": labels.__getitem__}
    result = turn_engine.turn(CTX, steps[0].message)
    assert result.text == f"Done: delivery on {TOMORROW}, between noon and six."
    # Entrega definida: a cotação seguinte já sai com o modo do carrinho.
    assert world.commerce_read.quote(j4.CTX, "cart-1").fulfillment.mode == "delivery"


def test_date_only_is_applied_without_inventing_the_rest():
    [result], world = run(step("f1", {"date": TOMORROW}, text=(f"Done: noted for {TOMORROW}.",)))
    assert dict(result.commands[0].parameters) == {"date": TOMORROW}
    assert world.state.fulfillment["cart-1"] == {"date": TOMORROW}


def test_mode_only_is_applied_without_inventing_the_rest():
    [result], world = run(step("f1", {"mode": "delivery"}, text=("Done: noted as delivery.",)))
    assert dict(result.commands[0].parameters) == {"mode": "delivery"}
    assert world.state.fulfillment["cart-1"] == {"mode": "delivery"}


def test_what_was_said_before_stays_and_the_reply_says_the_whole():
    (_, second, third), world = run(
        step("f1", {"mode": "pickup"}),
        step("f2", {"date": TOMORROW}, text=(f"Done: pickup on {TOMORROW}.",)),
        step("f3", {"window": "window-morning"}, text=(f"Done: pickup on {TOMORROW}, window-morning.",)),
    )
    assert dict(second.commands[0].parameters) == {"date": TOMORROW}
    assert world.state.fulfillment["cart-1"] == {"mode": "pickup", "date": TOMORROW, "window": "window-morning"}


def test_window_and_time_replace_each_other():
    _, world = run(step("f1", {"window": "window-morning"}), step("f2", {"time": "15:30"}))
    assert world.state.fulfillment["cart-1"] == {"time": "15:30"}


def test_unknown_window_is_refused_with_a_stable_code_and_nothing_changes():
    [result], world = run(step("f1", {"date": TOMORROW, "window": "window-midnight"},
                               moves=("inform_limitation",), text=("I can't do that here",)))
    receipt = result.receipts[0]
    assert (receipt.status, receipt.effect) == ("failure", "not_applied")
    assert receipt.error.code == "fulfillment_window_unknown"
    assert "cart-1" not in world.state.fulfillment and world.commerce_execute.effects == 0


def test_relative_input_is_not_applied():
    for fields in ({"date": "tomorrow"}, {"date": TOMORROW, "relative": True}, {"time": "4pm"},
                   {"mode": "drive-through"}, {"date": "2026-02-30"}):
        [result], world = run(step("f1", fields, moves=("inform_limitation",)))
        assert world.commerce_execute.calls == [] and result.commands == (), fields
        blocked = next(c for c in result.decision.candidates if c.move == "set_fulfillment")
        assert "relative_fulfillment" in blocked.blocked_by, fields


def test_ambiguous_input_asks_and_is_not_applied():
    [result], world = run(step("f1", {"date": TOMORROW}, alternatives={"date": "2026-01-07"},
                               moves=("ask_clarification",)))
    assert world.commerce_execute.calls == [] and result.episode.state == "waiting_input"


def test_nothing_said_is_not_a_fulfillment_change():
    [result], world = run(step("f1", {}, moves=("inform_limitation",)))
    assert world.commerce_execute.calls == []


def test_the_same_event_repeated_does_not_apply_twice():
    first = step("f1", {"date": TOMORROW, "mode": "pickup"})
    turn_engine, world = engine(steps=(first,))
    applied = turn_engine.turn(CTX, first.message)
    again = turn_engine.turn(CTX, first.message)
    assert applied.chosen_moves == ["set_fulfillment"] and again.outcome == "duplicate"
    assert world.commerce_execute.effects == 1 and len(world.commerce_execute.by_key) == 1


def test_the_same_command_repeated_returns_the_same_receipt():
    [result], world = run(step("f1", {"date": TOMORROW, "mode": "pickup"}))
    command, receipt = result.commands[0], result.receipts[0]
    again = world.commerce_execute.execute(CTX, command, _Allow())
    assert again.id == receipt.id and world.commerce_execute.effects == 1


def test_without_the_subject_cart_nothing_is_proposed():
    first = step("f1", {"date": TOMORROW}, moves=("inform_limitation",))
    turn_engine, world = engine(steps=(first,))
    turn_engine.subject_of = lambda ctx, event: dataclasses.replace(j4.subject(ctx, event), cart_ref=None)
    result = turn_engine.turn(CTX, first.message)
    assert result.chosen_moves == ["inform_limitation"] and world.commerce_execute.calls == []


def test_shadow_decides_but_never_sets_the_fulfillment():
    first = step("f1", {"date": TOMORROW})
    turn_engine, world = engine(steps=(first,))
    shadow = dataclasses.replace(CTX, environment="shadow")
    result = turn_engine.turn(shadow, first.message)
    assert result.chosen_moves == ["set_fulfillment"] and "shadow:effect_not_executed:set_fulfillment" in result.fallbacks
    assert world.commerce_execute.calls == []


def test_the_reading_rule_and_the_executor_agree_on_the_form():
    windows, modes = {"window-morning": ("08:00", "12:00")}, ("pickup", "delivery")
    cases = {
        (("date", TOMORROW), ("mode", "pickup"), ("window", "window-morning")): None,
        (("time", "17:59"),): None,
        (("date", "06/01/2026"),): "invalid_fulfillment",
        (("time", "25:00"),): "invalid_fulfillment",
        (("mode", "teleport"),): "invalid_fulfillment",
        (("note", "x"),): "invalid_fulfillment",
        (): "invalid_fulfillment",
        (("date", "2026-01-04"),): "fulfillment_unavailable",
        (("time", "19:00"),): "fulfillment_unavailable",
        (("window", "window-midnight"),): "fulfillment_window_unknown",
    }
    for fields, expected in cases.items():
        problem = fulfillment_problem(dict(fields), today="2026-01-05", modes=modes, windows=windows)
        assert (problem.value if problem else None) == expected, fields
        if expected in (None, "invalid_fulfillment") and fields and fields[0][0] != "note":
            assert is_absolute(dict(fields)) is (expected is None), fields


def test_delivery_not_offered_is_unavailable():
    world = FakeWorld()
    world.state.fulfillment_modes = ("pickup",)
    [result], _ = run(step("f1", {"mode": "delivery"}, moves=("inform_limitation",)), world=world)
    assert result.receipts[0].error.code == "fulfillment_unavailable"


class _AcceptsAnyWindow(FakeCommerceExecute):
    def _refusal(self, command):
        return None  # aceita tudo: a janela desconhecida passaria


def test_the_harness_fails_an_executor_that_accepts_any_window():
    world = FakeWorld()
    executor = _AcceptsAnyWindow(world.clock, world.faults, world.state)
    env = HarnessEnv(ctx=j4.CTX, clock=world.clock, cart_ref="cart-1",
                     fresh_terms=lambda: world.commerce_read.quote(j4.CTX, "cart-1"),
                     fulfillment={"date": TOMORROW, "mode": "pickup"}, unknown_window="window-midnight")
    failures = run_checks("commerce_execute", executor, env)
    assert failures and "janela desconhecida" in failures[0].message


class _Allow:
    def verify(self, state) -> None:
        return None
