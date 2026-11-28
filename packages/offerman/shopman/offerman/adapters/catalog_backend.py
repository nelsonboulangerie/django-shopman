"""Offerman catalog backend implementation."""

from shopman.offerman.protocols import ProductInfo
from shopman.offerman.service import CatalogService


class OffermanCatalogBackend:
    """
    CatalogBackend implementation using Offerman's catalog service.

    Lets a kernel that cannot import Offerman (Craftsman, via
    ``CRAFTSMAN["CATALOG_BACKEND"]``) resolve a sellable SKU without direct
    model access.
    """

    def get_product(self, sku: str) -> ProductInfo | None:
        """Return product by SKU."""
        product = CatalogService.get(sku)
        if not product:
            return None

        primary_collection = None
        primary_item = product.collection_items.filter(is_primary=True).first()
        if primary_item:
            primary_collection = primary_item.collection.ref

        return ProductInfo(
            sku=product.sku,
            name=product.name,
            description=product.long_description or None,
            category=primary_collection,
            unit=product.unit,
            is_bundle=product.is_bundle,
            base_price_q=product.base_price_q,
            is_published=product.is_published,
            is_sellable=product.is_sellable,
            keywords=list(product.keywords.names()) if product.keywords else None,
            image_url=product.image_url or None,
        )
