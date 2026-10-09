"""
Internal catalog adapter — delegates to Offerman (Core).

Core: CatalogService (pricing, bundle expansion), Product, Listing, ListingItem, CollectionItem
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_price(sku: str, qty: int = 1, channel: str | None = None) -> int:
    """Preço em centavos. Delega para CatalogService.price()."""
    from decimal import Decimal

    from shopman.offerman.service import CatalogService

    return CatalogService.price(sku, qty=Decimal(str(qty)), channel=channel)


def expand_bundle(sku: str, qty) -> list[dict]:
    """Expande bundle em componentes. Retorna [{"sku": str, "qty": Decimal}]."""
    from shopman.offerman.service import CatalogService

    return CatalogService.expand(sku, qty)


def get_product_base_price(sku: str) -> int:
    """Preço base do produto (sem tiers). Retorna centavos."""
    from shopman.offerman.models import Product

    return Product.objects.get(sku=sku).base_price_q


def get_listing_item(sku: str, listing_ref: str) -> dict | None:
    """Retorna os flags canônicos do vínculo sku <-> listing, ou None se não houver vínculo estrutural."""
    from shopman.offerman.models import ListingItem

    try:
        item = ListingItem.objects.get(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku=sku,
        )
    except ListingItem.DoesNotExist:
        return None
    except ListingItem.MultipleObjectsReturned:
        item = (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                listing__is_active=True,
                product__sku=sku,
            ).first()
        )
        if not item:
            return None

    return {
        "price_q": item.price_q,
        "min_qty": item.min_qty,
        "is_published": item.is_published,
        "is_sellable": item.is_sellable,
    }


def find_listing_tiers(sku: str, listing_ref: str) -> list[dict]:
    """Tiers de preço vendáveis por quantidade. Retorna [{"min_qty", "price_q", "is_sellable"}] desc."""
    from shopman.offerman.models import ListingItem

    return list(
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            product__sku=sku,
            is_sellable=True,
        )
        .order_by("-min_qty")
        .values("min_qty", "price_q", "is_sellable")
    )


def listing_exists(listing_ref: str) -> bool:
    """Verifica se um Listing ativo existe para o listing_ref."""
    from shopman.offerman.models import Listing

    return Listing.objects.filter(ref=listing_ref, is_active=True).exists()


def bulk_sku_to_collection_id(skus: list[str]) -> dict[str, int]:
    """Mapa sku → collection_id (primary) para múltiplos SKUs."""
    from shopman.offerman.models import CollectionItem

    result: dict[str, int] = {}
    for ci in CollectionItem.objects.filter(
        product__sku__in=skus, is_primary=True,
    ).select_related("collection"):
        result[ci.product.sku] = ci.collection_id
    return result


def find_substitutes(sku: str, limit: int = 8) -> list:
    """Busca substitutos para o SKU via Offerman."""
    from shopman.offerman import find_substitutes as _find_substitutes

    return _find_substitutes(sku, limit=limit)


def bulk_listing_price_map(skus: list[str], listing_ref: str) -> dict[str, int]:
    """Mapa sku → price_q do listing para múltiplos SKUs (preço mais específico por qty)."""
    from shopman.offerman.models import ListingItem

    price_map: dict[str, int] = {}
    for item in (
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku__in=skus,
            is_sellable=True,
        )
        .select_related("product")
        .order_by("-min_qty")
    ):
        price_map.setdefault(item.product.sku, item.price_q)
    return price_map


def bulk_bundle_skus(skus: list[str]) -> set[str]:
    """Os SKUs da lista que são bundle (têm componente), numa consulta só.

    É o mesmo critério de ``CatalogService.expand``: bundle é o produto que tem
    ``ProductComponent``. SKU inexistente não é bundle.
    """
    from shopman.offerman.models import ProductComponent

    if not skus:
        return set()
    return set(
        ProductComponent.objects.filter(parent__sku__in=skus)
        .values_list("parent__sku", flat=True)
        .distinct()
    )


def bulk_listing_items(skus: list[str], listing_ref: str) -> dict[str, dict]:
    """``get_listing_item`` para vários SKUs numa consulta só.

    Mesmo filtro e mesma forma de ``get_listing_item``; SKU sem vínculo fica de
    fora do mapa. Com mais de um vínculo (faixas de quantidade) vale o primeiro
    na ordem do modelo, como o ``.first()`` de lá.
    """
    from shopman.offerman.models import ListingItem

    result: dict[str, dict] = {}
    if not skus:
        return result
    for item in ListingItem.objects.filter(
        listing__ref=listing_ref,
        listing__is_active=True,
        product__sku__in=skus,
    ).select_related("product"):
        result.setdefault(item.product.sku, {
            "price_q": item.price_q,
            "min_qty": item.min_qty,
            "is_published": item.is_published,
            "is_sellable": item.is_sellable,
        })
    return result


def bulk_listing_tiers(skus: list[str], listing_ref: str) -> dict[str, list[dict]]:
    """``find_listing_tiers`` para vários SKUs numa consulta só (mesmo filtro, mesma ordem)."""
    from shopman.offerman.models import ListingItem

    result: dict[str, list[dict]] = {sku: [] for sku in skus}
    if not skus:
        return result
    for row in (
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            product__sku__in=skus,
            is_sellable=True,
        )
        .order_by("-min_qty")
        .values("product__sku", "min_qty", "price_q", "is_sellable")
    ):
        sku = row.pop("product__sku")
        result.setdefault(sku, []).append(row)
    return result


def bulk_product_base_prices(skus: list[str]) -> dict[str, int]:
    """``get_product_base_price`` para vários SKUs; SKU inexistente fica de fora."""
    from shopman.offerman.models import Product

    if not skus:
        return {}
    return dict(Product.objects.filter(sku__in=skus).values_list("sku", "base_price_q"))
