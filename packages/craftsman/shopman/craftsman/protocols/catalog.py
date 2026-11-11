"""
Catalog Protocol — interface for product/item information.

Craftsman defines these protocols, Offerman (or other catalog systems) implements them.

- CatalogProtocol: Generic item resolution (any ref → ItemInfo)

O ``CRAFTSMAN["CATALOG_BACKEND"]`` que a ficha técnica consulta fala só
``get_product(sku)`` (contrato em ``shopman.offerman.protocols.CatalogBackend``;
implementado pelo Offerman, pelo Buyman e pelo composto do orquestrador). Ver
``shopman.craftsman.models.recipe._catalog_product_info``.

Se não configurado: item_ref é usado como-é.
Se configurado: resolve nomes, unidades, shelf_life, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ══════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ItemInfo:
    """Item information from catalog (generic)."""

    ref: str
    name: str
    unit: str
    category: str | None = None
    description: str | None = None
    shelf_life_days: int | None = None
    lead_time_hours: int | None = None
    is_active: bool = True
    meta: dict | None = None


# ══════════════════════════════════════════════════════════════
# PROTOCOLS
# ══════════════════════════════════════════════════════════════


@runtime_checkable
class CatalogProtocol(Protocol):
    """
    Generic item resolution protocol.

    Se não configurado: item_ref é usado como-é.
    Se configurado: resolve nomes, unidades, etc.
    """

    def resolve(self, item_ref: str) -> ItemInfo | None:
        """
        Resolve an item_ref to its catalog info.

        Args:
            item_ref: Item reference string

        Returns:
            ItemInfo or None if not found
        """
        ...

