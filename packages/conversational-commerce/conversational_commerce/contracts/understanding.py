"""``Understanding``: o que o leitor entendeu de um evento (observação).

Invariante (v2 5.5): ato fora da lista vira ``unknown``; a regra local soma
atos e o modelo não os tira. A confiança é calibrada ou ``unavailable``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    Identifier,
    JsonObject,
    NonNegativeInt,
    ObservationRecord,
    Prediction,
    Producer,
    Value,
)
from .errors import invalid

Level = Literal["none", "low", "medium", "high", "unknown"]


@dataclass(**CONTRACT_DATACLASS)
class Span(Value):
    """Trecho do conteúdo, em posições de caractere: ``start`` incluso, ``end`` excluso."""

    start: NonNegativeInt
    end: NonNegativeInt

    def check(self) -> None:
        if self.end <= self.start:
            raise invalid("end precisa ser maior que start", "end")


@dataclass(**CONTRACT_DATACLASS)
class Act(Value):
    act: Identifier
    fields: JsonObject
    span: Span | None = None
    confidence: Prediction


@dataclass(**CONTRACT_DATACLASS)
class Alternative(Value):
    """Outra leitura possível do mesmo evento."""

    acts: tuple[Act, ...]
    confidence: Prediction

    def check(self) -> None:
        if not self.acts:
            raise invalid("alternativa sem ato", "acts")


@dataclass(**CONTRACT_DATACLASS)
class Signals(Value):
    friction: Level
    risk: Level


@dataclass(**CONTRACT_DATACLASS)
class Understanding(ObservationRecord):
    SCHEMA = "cc.understanding"
    KIND = "Understanding"

    event_id: Identifier
    acts: tuple[Act, ...]
    alternatives: tuple[Alternative, ...] = ()
    signals: Signals
    reader: Producer
