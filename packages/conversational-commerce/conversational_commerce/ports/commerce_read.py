"""Porta de comércio, leitura: catálogo, promessa, cotação, pedido, cliente, política.

Garantias (v2 5.4): fato com fonte e validade; autorização por objeto; consulta
não é reserva; "pode prometer" não é "há unidade separada" (K27). A promessa
devolve quatro leituras, nunca "reservado".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from conversational_commerce.contracts import Money, Quantity, TermsDocument
from conversational_commerce.contracts.common import CONTRACT_DATACLASS, Fact, Identifier, Prediction, Text, Value

from .common import Capabilities, TrustedContext

OPERATIONS = (
    "search_catalog",
    "read_item",
    "promise",
    "quote",
    "read_order",
    "read_customer",
    "read_policy",
    "knowledge",
    "scarcity",
)


@dataclass(**CONTRACT_DATACLASS)
class ItemSummary(Value):
    ref: Identifier
    name: Text
    unit: Identifier
    price: Money


@dataclass(**CONTRACT_DATACLASS)
class PromiseReading(Value):
    """Decisão de promessa: o que existe, o que é esperado, o planejado e o que se pode prometer."""

    ref: Identifier
    quantity: Quantity
    factual: Fact
    expected: Fact
    planned: Fact
    promisable: Fact


@runtime_checkable
class CommerceReadPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def search_catalog(self, ctx: TrustedContext, query: str) -> tuple[ItemSummary, ...]: ...

    def read_item(self, ctx: TrustedContext, ref: str) -> Fact: ...

    def promise(self, ctx: TrustedContext, ref: str, quantity: Quantity, when: str) -> PromiseReading: ...

    def quote(self, ctx: TrustedContext, cart_ref: str) -> TermsDocument: ...

    def read_order(self, ctx: TrustedContext, ref: str) -> Fact: ...

    def read_customer(self, ctx: TrustedContext, ref: str) -> Fact: ...

    def read_policy(self, ctx: TrustedContext, policy_id: str) -> Fact: ...

    def knowledge(self, ctx: TrustedContext, query: str) -> tuple[Fact, ...]: ...

    def scarcity(self, ctx: TrustedContext, ref: str) -> Prediction:
        """Opcional; quem não sabe devolve ``Unavailable``."""
        ...
