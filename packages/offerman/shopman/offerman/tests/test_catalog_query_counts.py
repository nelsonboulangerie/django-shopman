"""Custo de leitura do catálogo: a contagem de consultas não cresce com o número de produtos.

O caminho quente do catálogo (projeção de listing e adapters de SKU/produto para Stockman
e Craftsman) prefetcha ``collection_items__collection``. O ``.filter(is_primary=True)``
dentro do laço descartava o cache e voltava ao banco uma vez por produto; a correção varre
as linhas prefetchadas em Python. Estes testes são a trava: se a contagem voltar a crescer
com N, o custo do catálogo inteiro volta junto.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.adapters.product_info import ProductInfoBackend
from shopman.offerman.adapters.sku_validator import SkuValidator
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.offerman.service import CatalogService

pytestmark = pytest.mark.django_db


def _seed_products(listing, collection, count, *, start=0, prefix="P", keywords=()):
    """Cria ``count`` produtos com coleção primária, keywords e item de listing."""
    products = []
    for index in range(start, start + count):
        product = Product.objects.create(
            sku=f"{prefix}-{index:03d}",
            name=f"Produto {index:03d}",
            base_price_q=500,
            is_published=True,
            is_sellable=True,
        )
        CollectionItem.objects.create(
            collection=collection,
            product=product,
            is_primary=True,
            sort_order=index,
        )
        if keywords:
            product.keywords.add(*keywords)
        ListingItem.objects.create(listing=listing, product=product, price_q=500)
        products.append(product)
    return products


def _listing_and_collection():
    listing = Listing.objects.create(ref="ifood", name="iFood", priority=10)
    collection = Collection.objects.create(ref="featured", name="Featured", is_active=True)
    return listing, collection


class TestGetProjectionItemsQueryCount:
    def test_query_count_does_not_grow_with_products(self):
        listing, collection = _listing_and_collection()
        _seed_products(listing, collection, 2, keywords=("artesanal", "fermentacao"))

        with CaptureQueriesContext(connection) as two:
            small = CatalogService.get_projection_items("ifood")

        _seed_products(
            listing, collection, 28, start=2, keywords=("artesanal", "fermentacao")
        )

        with CaptureQueriesContext(connection) as thirty:
            big = CatalogService.get_projection_items("ifood")

        assert len(small) == 2
        assert len(big) == 30
        assert len(thirty.captured_queries) == len(two.captured_queries), (
            "A projeção do listing consulta em número fixo; crescer com os produtos é o "
            "N+1 de collection_items/keywords."
        )
        assert len(thirty.captured_queries) <= 6

    def test_primary_collection_and_keywords_match_direct_queries(self):
        listing, _collection = _listing_and_collection()
        secondary = Collection.objects.create(
            ref="secondary", name="Secondary", is_active=True, sort_order=0
        )
        primary = Collection.objects.create(
            ref="primary", name="Primary", is_active=True, sort_order=9
        )
        product = Product.objects.create(sku="PARITY", name="Paridade", base_price_q=700)
        # Não-primário com sort_order MENOR: a escolha é por is_primary, não pela
        # primeira linha da coleção em ordem global.
        CollectionItem.objects.create(
            collection=secondary, product=product, is_primary=False, sort_order=0
        )
        CollectionItem.objects.create(
            collection=primary, product=product, is_primary=True, sort_order=5
        )
        product.keywords.add("artesanal", "fermentacao")
        ListingItem.objects.create(listing=listing, product=product, price_q=700)

        item = next(iter(CatalogService.get_projection_items("ifood")))

        assert item.category == "primary"
        assert item.keywords == list(product.keywords.names())
        assert item.keywords == ["artesanal", "fermentacao"]


class TestSkuValidatorQueryCount:
    def test_get_sku_infos_query_count_does_not_grow_with_products(self):
        listing, collection = _listing_and_collection()
        _seed_products(listing, collection, 2)
        validator = SkuValidator()

        with CaptureQueriesContext(connection) as two:
            small = validator.get_sku_infos(["P-000", "P-001"])

        _seed_products(listing, collection, 28, start=2)

        with CaptureQueriesContext(connection) as thirty:
            big = validator.get_sku_infos([f"P-{i:03d}" for i in range(30)])

        assert small["P-000"].category == "Featured"
        assert big["P-029"].category == "Featured"
        assert len(thirty.captured_queries) == len(two.captured_queries)
        assert len(thirty.captured_queries) <= 3

    def test_search_skus_query_count_does_not_grow_with_products(self):
        listing, collection = _listing_and_collection()
        _seed_products(listing, collection, 2)
        validator = SkuValidator()

        with CaptureQueriesContext(connection) as two:
            small = validator.search_skus("Produto", limit=2)

        _seed_products(listing, collection, 28, start=2)

        with CaptureQueriesContext(connection) as thirty:
            big = validator.search_skus("Produto", limit=30)

        assert len(small) == 2
        assert len(big) == 30
        assert big[0].category == "Featured"
        assert len(thirty.captured_queries) == len(two.captured_queries)
        assert len(thirty.captured_queries) <= 3


class TestProductInfoQueryCount:
    def test_get_product_infos_query_count_does_not_grow_with_products(self):
        listing, collection = _listing_and_collection()
        _seed_products(listing, collection, 2)
        backend = ProductInfoBackend()

        with CaptureQueriesContext(connection) as two:
            small = backend.get_product_infos(["P-000", "P-001"])

        _seed_products(listing, collection, 28, start=2)

        with CaptureQueriesContext(connection) as thirty:
            big = backend.get_product_infos([f"P-{i:03d}" for i in range(30)])

        assert small["P-000"].category == "featured"
        assert big["P-029"].category == "featured"
        assert len(thirty.captured_queries) == len(two.captured_queries)
        assert len(thirty.captured_queries) <= 3

    def test_search_products_query_count_does_not_grow_with_products(self):
        listing, collection = _listing_and_collection()
        _seed_products(listing, collection, 2)
        backend = ProductInfoBackend()

        with CaptureQueriesContext(connection) as two:
            small = backend.search_products("Produto", limit=2)

        _seed_products(listing, collection, 28, start=2)

        with CaptureQueriesContext(connection) as thirty:
            big = backend.search_products("Produto", limit=30)

        assert len(small) == 2
        assert len(big) == 30
        assert big[0].category == "featured"
        assert len(thirty.captured_queries) == len(two.captured_queries)
        assert len(thirty.captured_queries) <= 3
