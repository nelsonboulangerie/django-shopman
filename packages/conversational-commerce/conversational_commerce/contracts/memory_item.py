"""``MemoryItem``: o que se guarda do cliente, com origem e validade (observação).

Invariante (v2 5.5, 6.1): correção alcança resumos e derivados; texto de
memória nunca é instrução. Na primeira versão só existe o declarado (o cliente
afirmou), com fonte e validade; nada inferido entra em decisão sem registro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, Instant, JsonValue, ObservationRecord
from .errors import invalid


@dataclass(**CONTRACT_DATACLASS)
class MemoryItem(ObservationRecord):
    SCHEMA = "cc.memory_item"
    KIND = "MemoryItem"

    memory_id: Identifier
    subject_ref: Identifier
    category: Identifier
    value: JsonValue
    evidence_state: Literal["declared", "inferred", "verified"]
    source: Identifier
    purpose: Identifier
    sensitivity: Literal["ordinary", "personal", "sensitive"]
    valid_until: Instant | None = None
    supersedes: Identifier | None = None

    def check(self) -> None:
        if self.value is None:
            raise invalid("memória sem valor; apagar é registro que substitui, não valor nulo", "value")
        if self.supersedes == self.memory_id:
            raise invalid("memória não substitui a si mesma", "supersedes")
