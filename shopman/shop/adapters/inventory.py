"""
Inventory availability backend — answers Craftsman's read-only InventoryProtocol
via Stockman (Buyman WP-B5b).

Craftsman's ingredient-availability guardrails (over-plan on adjust, missing-on-
finish, shortage status on suggestions) are dormant until CRAFTSMAN["INVENTORY_BACKEND"]
points here. It only READS: for each MaterialNeed it asks Stockman how much of that
sku is on hand. The stock ledger is written elsewhere (signal-path). Lazy imports
keep the module loadable without Stockman/Craftsman (ADR-001).
"""

from __future__ import annotations


class InventoryAvailabilityBackend:
    """Read-only ingredient availability over Stockman (InventoryProtocol)."""

    def available(self, materials):
        from shopman.craftsman.protocols.inventory import AvailabilityResult, MaterialStatus

        items = []
        all_available = True
        for need in materials:
            on_hand = self._on_hand_for_recipe(need.sku)
            if on_hand < need.quantity:
                all_available = False
            items.append(
                MaterialStatus(sku=need.sku, needed=need.quantity, available=on_hand)
            )
        return AvailabilityResult(all_available=all_available, materials=items)

    @staticmethod
    def _on_hand_for_recipe(sku):
        """O que a ficha PODE consumir — a mesma régua de quem consome.

        O consumo sai só das posições de produção e estoque (a vitrine fica de
        fora, salvo ``CONSUME_FROM_SALEABLE_POSITIONS``; ver
        ``craftsman.contrib.stockman.handlers.consumable_quants``). Contar a
        vitrine aqui deixaria o guardrail aprovar o que o consumo depois não
        acha: o pote exposto para venda não é o pote da massa.
        """
        from shopman.craftsman.conf import get_setting
        from shopman.stockman import stock
        from shopman.stockman.models import Position

        on_hand = stock.available(sku)
        if get_setting("CONSUME_FROM_SALEABLE_POSITIONS"):
            return on_hand
        for position in Position.objects.filter(is_saleable=True):
            on_hand -= stock.available(sku, position=position)
        return max(on_hand, 0)
