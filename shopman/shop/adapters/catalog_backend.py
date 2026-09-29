"""
Composed CatalogBackend — Offerman (vendáveis) + Buyman (insumos).

Craftsman resolves a sku via this backend (RecipeItem unit cross-check etc.).
A sellable output resolves through Offerman; an ingredient (Material) resolves
through Buyman. Everything else delegates to the Offerman backend.

Wired via CRAFTSMAN["CATALOG_BACKEND"] (config/settings.py). Resolution-only —
does NOT touch stock availability; essa é a costura do SkuValidator, ligada em
STOCKMAN["SKU_VALIDATOR"] (ver shopman/shop/adapters/sku_validator.py).

Um SKU pode ter os dois cadastros — o de venda (Product) e o de compra
(Material) — quando a coisa comprada também se vende. Aí os dois falam a mesma
unidade (o porteiro de coerência em shopman/shop/services/sku_namespace.py
garante), e responder o produto ou o insumo dá a mesma unidade para a ficha.
A precedência é do produto; a incoerência que escapar do porteiro é
**anunciada** em log de erro em vez de responder uma unidade errada calada.
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
        conferência de coerência custa uma consulta a mais e vale o preço:
        responder a unidade do produto quando o cadastro de compra diz outra é
        erro caro e mudo.
        """
        from shopman.shop.services.sku_namespace import units_agree

        product = self._offerman.get_product(sku)
        ingredient = self._buyman.get_product(sku)
        if product is not None and ingredient is not None:
            product_unit = getattr(product, "unit", "")
            ingredient_unit = getattr(ingredient, "unit", "")
            if not units_agree(product_unit, ingredient_unit):
                logger.error(
                    "sku_namespace.incoherent_unit: '%s' tem cadastro de venda em %s e de "
                    "compra em %s. Respondendo o de venda; acerte a unidade de um dos dois "
                    "(ver shopman/shop/services/sku_namespace.py).",
                    sku, product_unit or "?", ingredient_unit or "?",
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
