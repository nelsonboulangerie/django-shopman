"""Custo desconhecido veta a comparação econômica (K34), e a exposição efetiva é registro à parte."""

from __future__ import annotations

from conversational_commerce.contracts import Producer
from conversational_commerce.evaluation import compare_costs
from conversational_commerce.ports import Consumption
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.journeys import j6

from .helpers import CTX, engine

MODEL = Producer(name="model", version="1")


def priced(minor, currency="XTS"):
    return Consumption(model=MODEL, calls=1, cost={"status": "known",
                                                   "amount": {"amount_minor": minor, "currency": currency}})


UNPRICED = Consumption(model=MODEL, calls=1, cost={"status": "unavailable", "reason": "no_price"})


@conformance("K34", invariants=("N21",), scope="core")
def test_k34_model_without_price_is_unknown_cost_and_vetoes_the_comparison():
    vetoed = compare_costs({"a": [priced(30), priced(20)], "b": [UNPRICED]})
    assert vetoed.status == "vetoed" and vetoed.reason == "cost_unknown:b"
    assert vetoed.totals is None and vetoed.cheapest is None  # desconhecido não vira zero, nem "mais barato"
    compared = compare_costs({"a": [priced(30), priced(20)], "b": [priced(40)]})
    assert compared.status == "compared" and compared.totals == {"a": 50, "b": 40} and compared.cheapest == "b"
    assert compare_costs({"a": [priced(1)], "b": [priced(1, "XXX")]}).reason == "currency_mismatch"


def test_the_turn_records_the_exposure_and_accepted_is_not_exposed():
    turn_engine, world = engine()
    result = turn_engine.turn(CTX, j6.ASK.message)
    decision_id = result.decision.decision_id
    assert turn_engine.exposures.latest(decision_id) == result.exposure
    assert result.exposure.state == "accepted" and not turn_engine.exposures.exposed(decision_id)
    # Entregue, observado pelo canal: aí sim é exposição efetiva, e o histórico guarda os dois estados.
    world.channel.mark(f"send:{decision_id}", "delivered")
    delivered = turn_engine.observe_delivery(CTX, decision_id)
    assert delivered.state == "delivered" and turn_engine.exposures.exposed(decision_id)
    assert [e.state for e in turn_engine.exposures.history] == ["accepted", "delivered"]
