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


#: O tipo da pergunta no ar (ADR-051): a condição que o fechamento pediu, a condição de sim ou não, a oferta dos
#: termos ("Posso registrar?") ou o pedido de esclarecimento.
PendingKind = Literal["condition", "condition_yes_no", "terms_offer", "clarification"]


@dataclass(**CONTRACT_DATACLASS)
class PendingQuestion(Value):
    """A pergunta que a conversa deixou no ar, por código: nunca o texto dela, nunca dado pessoal (P17)."""

    kind: PendingKind
    # A condição perguntada (``delivery_time_slot``), ``terms`` na oferta, ou o ato do esclarecimento.
    code: Identifier
    # As opções oferecidas, pelas referências do fato (a porta as resolve, se puder).
    options: tuple[Text, ...] = ()


@dataclass(**CONTRACT_DATACLASS)
class RecentTurn(Value):
    """Uma fala recente da conversa, por referência: a do cliente pelo conteúdo, a do agente pelos moldes."""

    role: Literal["customer", "agent"]
    content_ref: Text | None = None
    template_ids: tuple[Identifier, ...] = ()


@dataclass(**CONTRACT_DATACLASS)
class ReadingContext(Value):
    """O que o leitor precisa saber da conversa para ler a fala nela, não sozinha (ADR-051, peça 1).

    É dado, nunca instrução: não muda os atos permitidos, e a fala que muda de assunto continua legível.
    """

    pending: PendingQuestion | None = None
    # Os atos que respondem à pergunta no ar (``engine.moves.expected_acts``).
    expected_acts: tuple[Identifier, ...] = ()
    # O que o fechamento ainda pede, em ordem, quando perguntou.
    open_conditions: tuple[Identifier, ...] = ()
    # As últimas falas, da mais antiga à mais nova (o teto é do perfil: ``reading_context_turns``).
    recent: tuple[RecentTurn, ...] = ()


@dataclass(**CONTRACT_DATACLASS)
class InterpretRequest(Value):
    request: ModelRequest
    event_id: Identifier
    content_ref: Text
    # Os atos que o leitor pode devolver; ato fora da lista vira ``unknown`` no núcleo.
    allowed_acts: tuple[Identifier, ...]
    # A conversa em volta da fala (ADR-051). Sem ela, o leitor lê a frase sozinha.
    context: ReadingContext | None = None


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
