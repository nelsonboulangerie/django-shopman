"""Resultados: censura (K33), supersessão (K35), fonte independente, desconhecido que não vira zero."""

from __future__ import annotations

import pytest

from conversational_commerce.contracts import MetricRef, OutcomeEvent, Window
from conversational_commerce.ledger import LedgerError, OutcomeLedger, summarize
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.fakes import FakeWorld, Fault

from .helpers import CTX, record

METRIC = MetricRef(id="repeat_purchase_30d", definition_version="1")


def window(world, start=-3600, end=-60):
    return Window(start=world.clock.at(start), end=world.clock.at(end))


@conformance("K33", invariants=("N21",), scope="adapter")
def test_k33_open_window_is_censored_not_zero():
    world = FakeWorld()
    ledger = OutcomeLedger()
    world.outcomes.seed(METRIC.id, "subject-1", 1)
    open_window = Window(start=world.clock.at(-60), end=world.clock.at(30 * 24 * 3600))
    outcome = ledger.harvest(CTX, world.outcomes, METRIC, "subject-1", open_window)
    assert outcome.observation == "censored" and outcome.value is None
    closed = ledger.harvest(CTX, world.outcomes, METRIC, "subject-1", window(world))
    assert closed.observation == "observed"
    summary = summarize(ledger.current())
    # O censurado é contado à parte; a média é só do observado, nunca puxada para zero.
    assert (summary.observed, summary.censored, summary.mean) == (1, 1, "1")
    assert summarize([outcome]).mean is None


@conformance("K35", invariants=("N14",), scope="adapter")
def test_k35_external_correction_supersedes_and_history_is_kept():
    world = FakeWorld()
    ledger = OutcomeLedger()
    world.outcomes.seed(METRIC.id, "subject-1", 1)
    first = ledger.harvest(CTX, world.outcomes, METRIC, "subject-1", window(world))
    world.outcomes.seed(METRIC.id, "subject-1", 0)
    world.faults.arm("harvest", Fault.CORRECTED_LATER)
    correction = ledger.harvest(CTX, world.outcomes, METRIC, "subject-1", window(world))
    assert correction.supersedes == first.id
    assert ledger.current(METRIC.id, "subject-1") == (correction,)
    assert ledger.chain(first.id) == (first, correction) == ledger.chain(correction.id)
    assert first in ledger.history and first.value == 1  # o anterior fica como estava
    assert summarize(ledger.current()).mean == "0"


def test_unknown_is_counted_apart_and_never_zero():
    world = FakeWorld()
    ledger = OutcomeLedger()
    outcome = ledger.harvest(CTX, world.outcomes, METRIC, "nobody", window(world))
    assert outcome.observation == "unknown"
    summary = summarize(ledger.current())
    assert (summary.unknown, summary.observed, summary.mean) == (1, 0, None)


def test_the_agent_never_writes_its_own_outcome():
    """N20: quem aprende não escreve o resultado pelo qual é avaliado."""
    ledger = OutcomeLedger()
    own = OutcomeEvent(**record(1), metric=METRIC, window=Window(start="2026-01-01T00:00:00.000000Z",
                                                                   end="2026-01-02T00:00:00.000000Z"),
                       observation="observed", value=1, source="conversational-commerce")
    with pytest.raises(LedgerError):
        ledger.record(own)


def test_supersession_must_point_to_a_recorded_outcome_once():
    ledger = OutcomeLedger()
    span = Window(start="2026-01-01T00:00:00.000000Z", end="2026-01-02T00:00:00.000000Z")
    base = OutcomeEvent(**record(1), metric=METRIC, window=span, observation="observed", value=1, source="ledger")
    ledger.record(base)
    with pytest.raises(LedgerError):
        ledger.record(OutcomeEvent(**record(2), metric=METRIC, window=span, observation="observed", value=0,
                                   source="ledger", supersedes="rec-missing"))
    ledger.record(OutcomeEvent(**record(3), metric=METRIC, window=span, observation="observed", value=0,
                               source="ledger", supersedes="rec-1"))
    with pytest.raises(LedgerError):
        ledger.record(OutcomeEvent(**record(4), metric=METRIC, window=span, observation="observed", value=2,
                                   source="ledger", supersedes="rec-1"))
