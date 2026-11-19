"""Envelope dos registros que os falsos produzem, com relógio e ids determinísticos."""

from __future__ import annotations

from typing import Any

from conversational_commerce.contracts import Producer
from conversational_commerce.ports import TrustedContext

from .faults import FaultPlan

FAKE_VERSION = "fake-1"


class FakeBase:
    PORT = ""

    def __init__(self, clock: Any, faults: FaultPlan | None = None) -> None:
        self.clock = clock
        self.faults = faults if faults is not None else FaultPlan()
        self.calls: list[str] = []

    def _fault(self, operation: str):
        self.calls.append(operation)
        return self.faults.take(operation)

    def envelope(self, ctx: TrustedContext, prefix: str, **extra: Any) -> dict[str, Any]:
        return {
            "id": self.clock.new_id(prefix),
            "tenant": ctx.tenant,
            "environment": ctx.environment,
            "trace_id": self.clock.new_id("trace"),
            "occurred_at": self.clock.now(),
            "producer": Producer(name=f"fake-{self.PORT}", version=FAKE_VERSION),
            **extra,
        }
