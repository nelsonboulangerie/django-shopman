"""A leitura com contexto (ADR-051, peça 1): o leitor recebe a pergunta no ar, os atos que respondem a ela, o que o
fechamento ainda pede e as últimas falas.

Medido no ar (24/11/2026): a Nice perguntou o horário da retirada, o cliente respondeu "vou buscar às 16h", e o
leitor, que via só a frase, leu a pergunta do horário da loja. O motor sabia o que estava no ar e não dizia.
"""

from __future__ import annotations

from conversational_commerce.engine.moves import expected_acts
from conversational_commerce.engine.turn import RECENT_KEY, with_recent
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j4, run_journey
from conversational_commerce.testing.journeys.runner import JourneyStep

from .helpers import CTX, engine

WITH_CONTEXT = {"limits": {"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 2,
                           "max_spend": {"amount_minor": 0, "currency": "XTS"}, "reading_context_turns": 2}}


def _step(mid, *acts):
    return JourneyStep(message=j4.message(mid, mid), understanding={"acts": list(acts)},
                       expect_moves=(), expect_text=(), advance_seconds=30)


CLOSE = _step("close", {"act": "place_order"})
TOMORROW = _step("tomorrow", {"act": "choose_fulfillment", "fields": {"date": "2026-01-06"}})
PICKUP = _step("pickup", {"act": "choose_fulfillment", "fields": {"mode": "pickup"}})
AT_FOUR = _step("four", {"act": "choose_fulfillment", "fields": {"time": "16:00"}})
YES = _step("yes", {"act": "affirm"})
STEPS = (CLOSE, TOMORROW, PICKUP, AT_FOUR, YES)


def _world():
    world = FakeWorld()
    world.state.payment_methods = ("card",)
    world.state.pickup_slots = ("9h às 12h", "15h às 18h")
    return world


def _contexts(profile_overrides=None):
    turn_engine, _ = engine(steps=STEPS, world=_world(), profile_overrides=profile_overrides)
    run_journey(turn_engine, CTX, list(STEPS))
    return [request.context for request in turn_engine.ports.model.requests]


def test_the_acts_that_answer_each_condition_come_from_the_moves_that_fulfill_it():
    assert expected_acts("delivery_time_slot") == ("choose_fulfillment",)
    assert expected_acts("fulfillment_date") == ("choose_fulfillment",)
    assert expected_acts("payment_method") == ("choose_payment",)
    assert expected_acts("delivery_address") == ("give_address",)
    # A oferta do endereço do cadastro é de sim ou não: o endereço novo, o sim, o não e o pedido das opções.
    assert set(expected_acts("delivery_address_saved")) == {"give_address", "affirm", "deny", "ask_options"}
    assert expected_acts("condicao_que_ninguem_cumpre") == ()


def test_the_reader_sees_the_question_the_close_left_open_at_each_step():
    """O fechamento pergunta o dia, retirar ou entregar, e o horário: a cada resposta, o leitor sabe a pergunta."""
    first, day, mode, time, yes = _contexts()
    assert first.pending is None and first.expected_acts == ()  # nada no ar: a frase se lê sozinha, como antes
    assert (day.pending.kind, day.pending.code, day.expected_acts) == ("condition", "fulfillment_date",
                                                                         ("choose_fulfillment",))
    assert day.open_conditions[:2] == ("fulfillment_date", "fulfillment_type")  # o que o fechamento ainda pede
    assert (mode.pending.code, time.pending.code) == ("fulfillment_type", "delivery_time_slot")
    assert time.pending.options == ("9h às 12h", "15h às 18h")  # as opções oferecidas, pelas referências do fato
    assert (yes.pending.kind, yes.expected_acts) == ("terms_offer", ("affirm", "deny"))  # "Posso registrar?"


def test_the_last_turns_go_by_reference_up_to_the_profile_ceiling():
    *_, yes = _contexts(profile_overrides=WITH_CONTEXT)
    assert [turn.role for turn in yes.recent] == ["customer", "agent", "customer", "agent"]  # dois turnos, o teto
    assert yes.recent[-2].content_ref == AT_FOUR.message["content_ref"]  # a fala do cliente, por referência
    assert yes.recent[-1].template_ids[-1] == "present_terms.confirm"  # o que o agente disse, pelos moldes
    assert all(turn.content_ref is None for turn in yes.recent if turn.role == "agent")


def test_without_a_ceiling_no_turn_is_kept():
    *_, yes = _contexts()
    assert yes.recent == ()
    assert RECENT_KEY not in with_recent({RECENT_KEY: [{"role": "customer"}]}, "text:oi", None, 0)
