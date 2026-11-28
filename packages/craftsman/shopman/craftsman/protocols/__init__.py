"""
Craftsman Protocols.

Defines interfaces for external integrations:
- InventoryProtocol: read-only material availability (Stockman/Buyman)
- DemandProtocol: demand history and committed orders
"""

from shopman.craftsman.protocols.demand import (
    DailyDemand,
    DemandProtocol,
)
from shopman.craftsman.protocols.inventory import (
    AvailabilityResult,
    InventoryProtocol,
    MaterialNeed,
    MaterialStatus,
)

__all__ = [
    # Inventory Protocol (read-only availability)
    "InventoryProtocol",
    "MaterialNeed",
    "MaterialStatus",
    "AvailabilityResult",
    # Demand Protocol
    "DemandProtocol",
    "DailyDemand",
]
