"""Porta de modelo: interpretar, redigir, pontuar.

Cada pedido leva finalidade, orçamento e classe de dado; cada retorno leva o
consumo, com custo conhecido ou ``Unavailable`` (custo desconhecido nunca é
zero, N21). Saída fora do esquema é falha tratada; nenhum retorno é concessão
nem recibo (v2 5.4). O texto do cliente chega por referência.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from conversational_commerce.contracts import Money, Producer, ReplyPlan, Unavailable, Understanding
from conversational_commerce.contracts.common import (
    CONTRACT_DATACLASS,
    DecimalText,
    Identifier,
    NonNegativeInt,
    Text,
    Value,
)

from .common import Capabilities, TrustedContext

OPERATIONS = ("interpret", "draft", "score")

DataClass = Literal["public", "redacted", "personal"]


@dataclass(**CONTRACT_DATACLASS)
class Budget(Value):
    max_calls: NonNegativeInt
    max_spend: Money


@dataclass(**CONTRACT_DATACLASS)
class ModelRequest(Value):
    purpose: Identifier
    budget: Budget
    data_class: DataClass


@dataclass(**CONTRACT_DATACLASS)
class KnownCost(Value):
    status: Literal["known"] = "known"
    amount: Money


@dataclass(**CONTRACT_DATACLASS)
class Consumption(Value):
    model: Producer
    calls: NonNegativeInt
    cost: KnownCost | Unavailable


@dataclass(**CONTRACT_DATACLASS)
class InterpretRequest(Value):
    request: ModelRequest
    event_id: Identifier
    content_ref: Text
    # Os atos que o leitor pode devolver; ato fora da lista vira ``unknown`` no núcleo.
    allowed_acts: tuple[Identifier, ...]


@dataclass(**CONTRACT_DATACLASS)
class Draft(Value):
    text: Text
    consumption: Consumption


@dataclass(**CONTRACT_DATACLASS)
class ScoreRequest(Value):
    request: ModelRequest
    options: tuple[Identifier, ...]


@dataclass(**CONTRACT_DATACLASS)
class Scores(Value):
    values: tuple[DecimalText, ...]
    consumption: Consumption


@runtime_checkable
class ModelPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def interpret(self, ctx: TrustedContext, request: InterpretRequest) -> tuple[Understanding, Consumption]: ...

    def draft(self, ctx: TrustedContext, request: ModelRequest, plan: ReplyPlan) -> Draft: ...

    def score(self, ctx: TrustedContext, request: ScoreRequest) -> Scores: ...
