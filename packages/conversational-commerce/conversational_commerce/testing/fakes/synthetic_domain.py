"""Domínio sintético dos falsos: um catálogo neutro, sem nenhuma loja real.

Moeda ``XTS`` (o código ISO 4217 reservado para teste). Itens, clientes e
políticas com nomes genéricos. Nada aqui pode dizer "padaria", "Shopman" ou o
nome de um canal: é a regra de corte do pacote.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import Money

CURRENCY = "XTS"
START = "2026-01-05T09:00:00.000000Z"
# Expediente do domínio sintético, em UTC.
OPENING = "08:00"
CLOSING = "18:00"


@dataclass(frozen=True, slots=True)
class SyntheticItem:
    ref: str
    name: str
    unit: str
    price_minor: int
    on_hand: str
    expected: str
    planned: str

    @property
    def price(self) -> Money:
        return Money(amount_minor=self.price_minor, currency=CURRENCY)


ITEMS: tuple[SyntheticItem, ...] = (
    SyntheticItem("ITEM-A", "Item A", "unit", 450, on_hand="12", expected="4", planned="20"),
    SyntheticItem("ITEM-B", "Item B", "unit", 1200, on_hand="0", expected="6", planned="6"),
    SyntheticItem("ITEM-C", "Item C (by weight)", "kg", 3990, on_hand="2.5", expected="0", planned="5"),
)

CUSTOMERS: dict[str, dict[str, str]] = {
    "customer-1": {"display_name": "Customer One", "contact_ref": "contact-1"},
    "customer-2": {"display_name": "Customer Two", "contact_ref": "contact-2"},
}

POLICIES: dict[str, str] = {
    "returns": "Unopened items can be returned within 7 days.",
    "cancellation": "Orders can be cancelled until preparation starts.",
}

KNOWLEDGE: dict[str, str] = {
    "opening_hours": f"Open every day from {OPENING} to {CLOSING} UTC.",
    "payment_methods": "Card and cash.",
}


@dataclass
class SyntheticState:
    """Estado mutável compartilhado entre os falsos de comércio (leitura e execução)."""

    items: dict[str, SyntheticItem] = field(default_factory=lambda: {item.ref: item for item in ITEMS})
    # carrinho → item → quantidade (decimal em texto)
    carts: dict[str, dict[str, str]] = field(default_factory=lambda: {"cart-1": {"ITEM-A": "2"}})
    cart_owner: dict[str, str] = field(default_factory=lambda: {"cart-1": "customer-1"})
    orders: dict[str, dict] = field(default_factory=dict)
    # versão de cada objeto que um comando pode esperar
    versions: dict[str, int] = field(default_factory=lambda: {"cart-1": 1})
    # carrinho → hash dos termos vigentes (o último cotado, enquanto nada mudou)
    current_terms: dict[str, str] = field(default_factory=dict)
