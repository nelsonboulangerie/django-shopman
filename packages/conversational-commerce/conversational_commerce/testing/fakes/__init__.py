"""Um adaptador falso por porta, com falhas injetáveis (``faults.FaultPlan``).

``FakeWorld`` monta os oito sobre um relógio e um estado sintético
compartilhados, que é como a suíte do núcleo os usa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .channel import FakeChannel
from .clock import FakeClock
from .commerce import FakeCommerceExecute, FakeCommerceRead
from .faults import Fault, FaultPlan
from .model import FakeModel
from .outcomes import FakeOutcomes
from .staff import FakeStaff
from .store import FakeStore
from .synthetic_domain import SyntheticState


@dataclass
class FakeWorld:
    clock: FakeClock = field(default_factory=FakeClock)
    faults: FaultPlan = field(default_factory=FaultPlan)
    state: SyntheticState = field(default_factory=SyntheticState)

    def __post_init__(self) -> None:
        self.channel = FakeChannel(self.clock, self.faults)
        self.model = FakeModel(self.clock, self.faults)
        self.commerce_read = FakeCommerceRead(self.clock, self.faults, self.state)
        self.commerce_execute = FakeCommerceExecute(self.clock, self.faults, self.state)
        self.staff = FakeStaff(self.clock, self.faults)
        self.store = FakeStore(self.clock, self.faults)
        self.outcomes = FakeOutcomes(self.clock, self.faults)

    def ports(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "model": self.model,
            "commerce_read": self.commerce_read,
            "commerce_execute": self.commerce_execute,
            "staff": self.staff,
            "store": self.store,
            "clock": self.clock,
            "outcomes": self.outcomes,
        }


__all__ = [
    "FakeChannel",
    "FakeClock",
    "FakeCommerceExecute",
    "FakeCommerceRead",
    "FakeModel",
    "FakeOutcomes",
    "FakeStaff",
    "FakeStore",
    "FakeWorld",
    "Fault",
    "FaultPlan",
    "SyntheticState",
]
