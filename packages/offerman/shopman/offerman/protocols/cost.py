"""
CostBackend protocol.

Allows an external app to provide production cost for a product without
Offerman importing it.

O provedor precisa de receita (Craftsman) e de custo de insumo (Buyman) ao
mesmo tempo, então mora no orquestrador: ``shopman.shop.adapters.cost.
RecipeCostBackend`` responde o custo VIVO de
docs/decisions/adr-023-cost-live-and-frozen.md (custo vivo para precificar ×
custo congelado no fato para contar história). Sem provedor configurado,
``Product.reference_cost_q`` responde ``None`` e a margem se esconde no Admin.

Usage:
    # In settings.py
    OFFERMAN = {
        "COST_BACKEND": "shopman.shop.adapters.cost.RecipeCostBackend",
    }
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class CostBackend(Protocol):
    """
    Interface for retrieving production cost of a product.

    Implemented by apps that own cost data (e.g. Craftsman).
    Offerman reads cost via this Protocol for margin calculations.
    """

    def get_cost(self, sku: str) -> int | None:
        """
        Return production cost in centavos for the given SKU.

        Args:
            sku: Product SKU code

        Returns:
            Cost in centavos (int) or None if cost is unknown.
        """
        ...
