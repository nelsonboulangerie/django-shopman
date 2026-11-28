"""
Offerman SKU Validator — Implements Stockman's SkuValidator protocol.
"""

from __future__ import annotations

import logging
import threading
from importlib.util import find_spec
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _stocking_protocols_available() -> bool:
    """Check if Stockman protocols are available."""
    try:
        return find_spec("shopman.stockman.protocols.sku") is not None
    except ModuleNotFoundError:
        return False


class SkuValidator:
    """
    SKU validator using Offerman Product model.

    Implements SkuValidator protocol from Stockman.
    """

    def validate_sku(self, sku: str):
        """Validate if SKU exists and expose orderability via the offer contract."""
        from shopman.offerman.models import Product
        from shopman.stockman.protocols.sku import SkuValidationResult

        try:
            product = Product.objects.get(sku=sku)
            is_published = product.is_active and product.is_published
            is_sellable = product.is_active and product.is_sellable
            return SkuValidationResult(
                valid=True,
                sku=sku,
                product_name=product.name,
                is_published=is_published,
                is_sellable=is_sellable,
                message=None if (is_published and is_sellable) else "Product is not sellable",
            )
        except Product.DoesNotExist:
            return SkuValidationResult(
                valid=False,
                sku=sku,
                error_code="not_found",
                message=f"SKU '{sku}' not found in catalog",
            )

    def validate_skus(self, skus: list[str]) -> dict:
        """Validate multiple SKUs at once."""
        from shopman.offerman.models import Product
        from shopman.stockman.protocols.sku import SkuValidationResult

        products = Product.objects.filter(sku__in=skus)
        found = {p.sku: p for p in products}

        result = {}
        for sku in skus:
            if sku in found:
                product = found[sku]
                result[sku] = SkuValidationResult(
                    valid=True,
                    sku=sku,
                    product_name=product.name,
                    is_published=product.is_active and product.is_published,
                    is_sellable=product.is_active and product.is_sellable,
                )
            else:
                result[sku] = SkuValidationResult(
                    valid=False,
                    sku=sku,
                    error_code="not_found",
                )

        return result

    def get_sku_info(self, sku: str):
        """Informação de um SKU, pela mesma leitura canônica do lote."""
        return self.get_sku_infos([sku])[sku]

    def get_sku_infos(self, skus: list[str]) -> dict:
        """Informações do lote em uma consulta, sem materializar models.

        Só o nome da coleção primária pertence ao contrato de estoque. O join
        filtrado preserva produto sem coleção e coleção inativa; a restrição
        de uma primária por produto impede multiplicar linhas. Não carrega as
        demais coleções, metadados ou vínculos que esta leitura não usa.
        """
        from shopman.offerman.models import Product
        from shopman.stockman.protocols.sku import SkuInfo

        rows = Product.objects.filter(sku__in=skus).annotate(
            primary_collection=models.FilteredRelation(
                "collection_items", condition=models.Q(collection_items__is_primary=True),
            ),
            primary_category=models.F("primary_collection__collection__name"),
        ).values(
            "sku", "name", "long_description", "is_active", "is_published",
            "is_sellable", "unit", "base_price_q", "availability_policy",
            "shelf_life_days", "primary_category",
        )
        found = {
            row["sku"]: SkuInfo(
                sku=row["sku"],
                name=row["name"],
                description=row["long_description"],
                is_published=row["is_active"] and row["is_published"],
                is_sellable=row["is_active"] and row["is_sellable"],
                unit=row["unit"],
                category=row["primary_category"],
                base_price_q=row["base_price_q"],
                availability_policy=row["availability_policy"],
                shelflife_days=row["shelf_life_days"],
            )
            for row in rows
        }
        return {sku: found.get(sku) for sku in skus}

    def search_skus(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list:
        """Search SKUs by name or code."""
        from shopman.offerman.models import Product
        from shopman.stockman.protocols.sku import SkuInfo

        qs = Product.objects.filter(
            models.Q(sku__icontains=query) | models.Q(name__icontains=query)
        ).prefetch_related("collection_items__collection")

        if not include_inactive:
            qs = qs.active().filter(is_published=True)

        qs = qs[:limit]

        result = []
        for p in qs:
            # Prefetchado acima; varre em Python em vez de consultar por produto.
            primary_item = next(
                (ci for ci in p.collection_items.all() if ci.is_primary), None
            )
            category = primary_item.collection.name if primary_item else None
            result.append(
                SkuInfo(
                    sku=p.sku,
                    name=p.name,
                    description=p.long_description,
                    is_published=p.is_published,
                    is_sellable=p.is_sellable,
                    unit=p.unit,
                    category=category,
                    base_price_q=p.base_price_q,
                    availability_policy=p.availability_policy,
                    shelflife_days=p.shelf_life_days,
                )
            )
        return result


# Singleton factory
_lock = threading.Lock()
_validator_instance: SkuValidator | None = None


def get_sku_validator() -> SkuValidator:
    """Return singleton instance of SkuValidator."""
    global _validator_instance
    if _validator_instance is None:
        with _lock:
            if _validator_instance is None:
                _validator_instance = SkuValidator()
    return _validator_instance


def reset_sku_validator() -> None:
    """Reset singleton (for tests)."""
    global _validator_instance
    _validator_instance = None
