"""Resultados falsos: o teste semeia o valor; janela aberta é censurada; correção substitui."""

from __future__ import annotations

from conversational_commerce.contracts import MetricRef, OutcomeEvent, Window
from conversational_commerce.ports import Capabilities, TrustedContext
from conversational_commerce.ports.outcomes import OPERATIONS

from .base import FakeBase
from .faults import Fault


class FakeOutcomes(FakeBase):
    PORT = "outcomes"

    def __init__(self, clock, faults=None) -> None:
        super().__init__(clock, faults)
        self.values: dict[tuple[str, str], object] = {}
        self.harvested: list[OutcomeEvent] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(port="outcomes", operations=OPERATIONS,
                            guarantees={"independent_source": True, "censoring": True, "supersession": True})

    def seed(self, metric_id: str, subject: str, value) -> None:
        self.values[(metric_id, subject)] = value

    def harvest(self, ctx: TrustedContext, metric: MetricRef, subject: str, window: Window) -> OutcomeEvent:
        fault = self._fault("harvest")
        base = {**self.envelope(ctx, "out"), "customer_ref": subject, "metric": metric, "window": window,
                "source": "fake-ledger"}
        if fault is Fault.IMMATURE or window.end > self.clock.now():
            outcome = OutcomeEvent(**base, observation="censored")
        elif (metric.id, subject) not in self.values:
            outcome = OutcomeEvent(**base, observation="unknown")
        else:
            outcome = OutcomeEvent(**base, observation="observed", value=self.values[(metric.id, subject)])
        if fault is Fault.CORRECTED_LATER and self.harvested:
            outcome = OutcomeEvent(**{**base, "id": self.clock.new_id("out")}, observation=outcome.observation,
                                   value=outcome.value, supersedes=self.harvested[-1].id)
        self.harvested.append(outcome)
        return outcome
