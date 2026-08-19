"""
Composed CatalogBackend — Offerman (vendáveis) + Buyman (insumos).

Craftsman resolves a sku via this backend (RecipeItem unit cross-check etc.).
A sellable output resolves through Offerman; an ingredient (Material) resolves
through Buyman. Everything else delegates to the Offerman backend.

Wired via CRAFTSMAN["CATALOG_BACKEND"] (config/settings.py). Resolution-only —
does NOT touch stock availability; essa é a costura do SkuValidator, ligada em
STOCKMAN["SKU_VALIDATOR"] (ver shopman/shop/adapters/sku_validator.py).

⚠️ Produto e insumo dividem um namespace de SKU só, sem unicidade cruzada no
banco. Aqui a precedência é do produto — e, quando os dois existem, ela é
**anunciada** em log de erro em vez de sombrear o insumo em silêncio. O porteiro
que impede a colisão de nascer está em shopman/shop/services/sku_namespace.py.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ComposedCatalogBackend:
    """Catalog backend that resolves Products (Offerman) then Materials (Buyman)."""

    def __init__(self):
        from shopman.buyman.adapters.catalog_backend import BuymanCatalogBackend
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        self._offerman = OffermanCatalogBackend()
        self._buyman = BuymanCatalogBackend()

    def get_product(self, sku: str):
        """Resolve a sku as a sellable product first, then as an ingredient.

        Caminho frio (validação de ficha técnica, sugestão de produção), então a
        checagem de colisão custa uma consulta a mais e vale o preço: responder
        a unidade do produto para um insumo homônimo é erro caro e mudo.
        """
        product = self._offerman.get_product(sku)
        ingredient = self._buyman.get_product(sku)
        if product is not None and ingredient is not None:
            logger.error(
                "sku_namespace.collision: '%s' existe como produto vendável (unidade %s) "
                "e como insumo (unidade %s). Respondendo o produto; renomeie um dos dois "
                "(ver shopman/shop/services/sku_namespace.py).",
                sku, getattr(product, "unit", "?"), getattr(ingredient, "unit", "?"),
            )
        return product or ingredient

    def __getattr__(self, name):
        # Anything not overridden (get_price, expand, etc.) is an Offerman/sellable
        # concern — delegate. (Called only for attrs missing on this instance.)
        return getattr(self.__dict__["_offerman"], name)


_lock = threading.Lock()
_instance: ComposedCatalogBackend | None = None


def get_composed_catalog_backend() -> ComposedCatalogBackend:
    """Return the singleton ComposedCatalogBackend."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ComposedCatalogBackend()
    return _instance


def reset_composed_catalog_backend() -> None:
    """Reset the singleton (for tests)."""
    global _instance
    _instance = None
