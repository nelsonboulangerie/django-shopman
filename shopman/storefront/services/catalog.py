"""Storefront catalog read service."""

from __future__ import annotations

import logging

from django.http import Http404
from shopman.utils.monetary import format_money

from shopman.shop.projections import catalog_context

logger = logging.getLogger(__name__)


def published_products(listing_ref: str | None):
    return catalog_context.published_products(listing_ref)


def filter_by_collection(qs, collection_ref: str):
    """Filtra produtos por coleção (smart collections resolvem por regra).

    Rota pública e anônima: coleção exclusiva de grupo é vazia, como a inexistente.
    """
    from shopman.shop.projections.exclusive_collections import access_for_tiers

    if access_for_tiers(()).is_hidden(collection_ref):
        return qs.none()
    return catalog_context.filter_by_collection(qs, collection_ref)


def get_active_collection_or_404(collection_ref: str, *, request=None):
    """A coleção ativa que o visitante enxerga, ou 404. Só lê.

    A coleção exclusiva de um grupo é 404 para quem não é do grupo, anônimo
    incluído: para ele, ela não existe (e não vira "coleção vazia").
    """
    collection = catalog_context.get_active_collection(collection_ref)
    if collection is None:
        raise Http404
    from shopman.storefront.presentation.catalog import viewer_collection_access

    if viewer_collection_access(request).is_hidden(collection.ref):
        raise Http404
    return collection


def product_exists(sku: str) -> bool:
    return catalog_context.product_exists(sku)


def get_published_product(sku: str):
    return catalog_context.get_published_product(sku)


def get_sellable_published_product(sku: str):
    return catalog_context.get_sellable_published_product(sku)


def active_collections_with_counts() -> list[dict]:
    """As coleções do catálogo público, sem as exclusivas de grupo (rota anônima)."""
    from shopman.shop.projections.exclusive_collections import access_for_tiers

    hidden = access_for_tiers(()).hidden
    return [row for row in catalog_context.active_collections_with_counts() if row["ref"] not in hidden]


def without_exclusive_only_products(qs):
    """Tira do queryset público o produto que só existe em coleção exclusiva de grupo."""
    from shopman.shop.projections.exclusive_collections import access_for_tiers, exclusive_only_product_ids

    access = access_for_tiers(())
    if not access.hidden:
        return qs
    return qs.exclude(pk__in=exclusive_only_product_ids(access))


def search_index(catalog) -> list[dict]:
    """Build the lightweight client-side search index for the menu overlay."""
    seen: set[str] = set()
    records: list[dict] = []
    keywords_by_sku: dict[str, list[str]] = {}
    # A seção carrega só SKUs; o card mora uma vez em ``catalog.items``.
    item_by_sku = {}
    for item in catalog.items:
        item_by_sku.setdefault(item.sku, item)

    try:
        skus_all = [sku for sec in catalog.sections for sku in sec.skus]
        if skus_all:
            keywords_by_sku = catalog_context.keywords_by_sku(skus_all)
    except Exception:
        logger.debug("menu_search_index_keywords_failed", exc_info=True)
        keywords_by_sku = {}

    for section in catalog.sections:
        for sku in section.skus:
            item = item_by_sku.get(sku)
            if item is None or sku in seen:
                continue
            seen.add(item.sku)
            records.append(
                {
                    "sku": item.sku,
                    "name": item.name,
                    "price": f"R$ {format_money(item.quote.final_unit_price_q)}",
                    "image": item.image_url or "",
                    "section": section.label,
                    "keywords": keywords_by_sku.get(item.sku, []),
                    "terms": item.search_terms,
                }
            )
    return records

