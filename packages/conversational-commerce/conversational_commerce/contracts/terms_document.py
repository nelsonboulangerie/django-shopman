"""``TermsDocument``: os termos que o cliente confirma (estrito, com hash).

Produzido pelo sistema de registro; referenciado pelo hash, nunca
reconstruído (v2 4.7, 5.5). Mudança material (item, quantidade, preço, moeda,
destinatário, cumprimento, condição) é outro documento, com outro hash.

Regras de valor: uma moeda só no documento inteiro; o total é a soma das
linhas mais os ajustes (frete, taxa, desconto), em centavos exatos. O preço
unitário vezes a quantidade NÃO é conferido aqui: arredondamento é do sistema
de registro, e ``line_total`` é o que ele cobra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .common import (
    CONTRACT_DATACLASS,
    Hash,
    Identifier,
    Instant,
    JsonValue,
    Money,
    PositiveInt,
    Quantity,
    StrictRecord,
    Value,
)
from .errors import invalid
from .validate import require_order, require_unique


@dataclass(**CONTRACT_DATACLASS)
class TermsItem(Value):
    ref: Identifier
    quantity: Quantity
    unit_price: Money
    line_total: Money


@dataclass(**CONTRACT_DATACLASS)
class Adjustment(Value):
    """Valor que entra no total fora das linhas: frete, taxa, desconto (negativo)."""

    code: Identifier
    amount: Money


@dataclass(**CONTRACT_DATACLASS)
class Recipient(Value):
    subject_ref: Identifier
    contact_ref: Identifier | None = None


@dataclass(**CONTRACT_DATACLASS)
class Fulfillment(Value):
    mode: Identifier
    address_ref: Identifier | None = None
    window_start: Instant | None = None
    window_end: Instant | None = None

    def check(self) -> None:
        require_order(self.window_start, self.window_end, "window_end", strict=True)


@dataclass(**CONTRACT_DATACLASS)
class Condition(Value):
    code: Identifier
    value: JsonValue = None


@dataclass(**CONTRACT_DATACLASS)
class TermsDocument(StrictRecord):
    SCHEMA = "cc.terms_document"
    KIND = "TermsDocument"
    HASH_FIELD: ClassVar[str | None] = "hash"

    terms_id: Identifier
    version: PositiveInt
    items: tuple[TermsItem, ...]
    adjustments: tuple[Adjustment, ...] = ()
    total: Money
    recipient: Recipient
    fulfillment: Fulfillment
    conditions: tuple[Condition, ...] = ()
    valid_until: Instant
    # None só no rascunho, antes de ``seal()``; no documento é obrigatório.
    hash: Hash | None = None

    def check(self) -> None:
        if not self.items:
            raise invalid("termos sem item", "items")
        require_unique((item.ref for item in self.items), "items")
        require_unique((condition.code for condition in self.conditions), "conditions")
        require_order(self.occurred_at, self.valid_until, "valid_until", strict=True)
        currency = self.total.currency
        amounts = [("items", index, "line_total", item.line_total) for index, item in enumerate(self.items)]
        amounts += [("items", index, "unit_price", item.unit_price) for index, item in enumerate(self.items)]
        amounts += [("adjustments", index, "amount", adj.amount) for index, adj in enumerate(self.adjustments)]
        for section, index, name, money in amounts:
            if money.currency != currency:
                raise invalid(f"moeda {money.currency} difere da do total ({currency})", section, index, name, "currency")
        for index, item in enumerate(self.items):
            if item.line_total.amount_minor < 0 or item.unit_price.amount_minor < 0:
                raise invalid("linha com valor negativo; desconto é ajuste", "items", index)
        expected = sum(item.line_total.amount_minor for item in self.items)
        expected += sum(adj.amount.amount_minor for adj in self.adjustments)
        if expected != self.total.amount_minor:
            raise invalid(f"total {self.total.amount_minor} difere de linhas + ajustes ({expected})", "total")
        if self.total.amount_minor < 0:
            raise invalid("total negativo", "total")
