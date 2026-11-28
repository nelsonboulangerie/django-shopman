"""Várias linhas num turno são uma mudança só: um comando, atômico, com um recibo (spec 08 §5, [DECIDIDO]).

"2 itens A e 1 item B" não vira dois efeitos (o segundo seria recusado por ``one_effect_per_turn``):
a primeira necessidade de mudança leva o comando com todas as linhas, e as outras são levadas por ela.
"""

from __future__ import annotations

from conversational_commerce.testing.journeys import j4
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine


def _step(*acts, mid="lines-1"):
    return JourneyStep(message=j4.message(mid, "two lines"), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=())


A3 = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "3"}}
B1 = {"act": "change_quantity", "fields": {"item": "ITEM-B", "quantity": "1"}}


def test_two_lines_are_one_command_with_one_receipt_and_one_reply():
    step = _step(A3, B1)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert len(result.commands) == 1 and len(result.receipts) == 1
    assert [dict(line) for line in result.commands[0].parameters["lines"]] == [
        {"item": "ITEM-A", "quantity": "3"}, {"item": "ITEM-B", "quantity": "1"}]
    assert world.state.carts["cart-1"] == {"ITEM-A": "3", "ITEM-B": "1"}
    assert world.commerce_execute.effects == 1
    assert result.chosen_moves == ["change_cart", "change_cart"]  # as duas necessidades, atendidas
    assert result.reply.template_ids == ("change_cart.done",)  # uma resposta só, com a sacola inteira
    assert "one_effect_per_turn" not in str(result.fallbacks)


def test_a_relative_line_makes_the_whole_change_ineligible():
    step = _step(A3, {"act": "change_quantity", "fields": {"item": "ITEM-B", "quantity": "1", "relative": True}})
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert result.commands == () and world.commerce_execute.effects == 0  # tudo ou nada


def test_the_same_turn_twice_applies_once():
    step = _step(A3, B1)
    turn_engine, world = engine(steps=(step,))
    turn_engine.turn(CTX, step.message)
    again = turn_engine.turn(CTX, step.message)
    assert again.outcome == "duplicate" and world.commerce_execute.effects == 1



def test_a_relative_line_first_never_lets_the_carried_line_run_alone():
    """Revisão do #3375: com a relativa em PRIMEIRO, a levada herda a inelegibilidade e nada se aplica."""
    relative_first = {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "1", "relative": True}}
    step = _step(relative_first, B1)
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert result.commands == () and world.commerce_execute.effects == 0
    assert world.state.carts["cart-1"] == {"ITEM-A": "2"}  # o carrinho como estava


def test_the_same_item_in_two_lines_is_not_a_command():
    """ "2 itens A… e 1 item A": qual vale não se sabe; a última não vence em silêncio."""
    step = _step(A3, {"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "1"}})
    turn_engine, world = engine(steps=(step,))
    result = turn_engine.turn(CTX, step.message)
    assert result.commands == () and world.commerce_execute.effects == 0
    assert "change_cart" not in result.chosen_moves


def test_the_harness_fails_an_executor_that_applies_malformed_lines():
    """A conformidade mora no arnês do pacote: outro adaptador herda a checagem."""
    from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
    from conversational_commerce.testing.fakes import FakeWorld
    from conversational_commerce.testing.fakes.commerce import FakeCommerceExecute

    class AcceptsAnything(FakeCommerceExecute):
        def _refusal(self, command):
            return None

        def _apply(self, command):
            self.effects += 1
            return f"effect-{self.effects:04d}"

    world = FakeWorld()
    executor = AcceptsAnything(world.clock, world.faults, world.state)
    env = HarnessEnv(ctx=j4.CTX, clock=world.clock, cart_ref="cart-1",
                     fresh_terms=lambda: world.commerce_read.quote(j4.CTX, "cart-1"),
                     cart_lines=({"item": "ITEM-A", "quantity": "2"},))
    failures = run_checks("commerce_execute", executor, env)
    assert failures and "malformada" in failures[0].message
