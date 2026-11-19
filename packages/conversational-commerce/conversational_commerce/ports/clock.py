"""Porta de relógio e agenda: agora, identificador novo, agendar, cancelar, expediente.

Garantias (v2 5.4): prazo vencido vira evento reivindicável, não laço; relógio
e identificadores substituíveis em teste (determinísticos no falso).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from conversational_commerce.contracts.common import Fact

from .common import Capabilities
from .store import WorkItem

OPERATIONS = ("now", "new_id", "schedule", "cancel", "business_hours")


@runtime_checkable
class ClockPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def now(self) -> str: ...

    def new_id(self, prefix: str) -> str: ...

    def schedule(self, at: str, work: WorkItem) -> str: ...

    def cancel(self, handle: str) -> bool: ...

    def business_hours(self, at: str) -> Fact: ...
