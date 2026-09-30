"""O caminho quente do cardápio e da home: mesma resposta, menos consultas.

- ``published_products_by_collection`` monta os grupos com uma leitura de
  produtos e uma de vínculos, sem consulta por coleção — e na MESMA ordem.
- A home guarda três cards e não monta mais o cardápio inteiro para isso:
  ``build_featured_items`` escolhe os mesmos cards que
  ``(build_catalog().featured or build_catalog().items)[:3]``.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Collection, CollectionItem, ListingItem, Product

from shopman.shop.projections import catalog_context
from shopman.storefront.api.projections import projection_data
from shopman.storefront.presentation import catalog as catalog_module
from shopman.storefront.presentation import home as home_module
from shopman.storefront.presentation.catalog import build_catalog, build_featured_items

pytestmark = pytest.mark.django_db


def _product(listing, sku: str, name: str, *, published_on_listing: bool = True, **extra) -> Product:
    product = Product.objects.create(
        sku=sku,
        name=name,
        base_price_q=500,
        is_published=extra.pop("is_published", True),
        is_sellable=True,
        **extra,
    )
    if published_on_listing:
        ListingItem.objects.create(
            listing=listing, product=product, price_q=500, is_published=True, is_sellable=True,
        )
    return product


def _link(collection: Collection, product: Product, sort_order: int) -> None:
    CollectionItem.objects.create(collection=collection, product=product, sort_order=sort_order)


def _grouped(listing_ref: str = "web") -> list[tuple[str | None, list[str]]]:
    return [
        (ref, [p.sku for p in products])
        for ref, products in catalog_context.published_products_by_collection(listing_ref=listing_ref)
    ]


class TestPublishedProductsByCollection:
    def test_order_ties_uncategorized_and_inactive_collection(self, listing):
        doces = Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=1)
        paes = Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=2)
        sazonal = Collection.objects.create(ref="sazonal", name="Sazonal", is_active=False, sort_order=0)
        vazia = Collection.objects.create(ref="vazia", name="Vazia", is_active=True, sort_order=3)

        zebra = _product(listing, "ZEBRA", "Zebra")
        alfajor = _product(listing, "ALFAJOR", "Alfajor")
        baguete = _product(listing, "BAGUETE", "Baguete")
        croissant = _product(listing, "CROISSANT", "Croissant")
        panetone = _product(listing, "PANETONE", "Panetone")
        rascunho = _product(listing, "RASCUNHO", "Rascunho", is_published=False)
        fora = _product(listing, "FORA", "Fora da vitrine", published_on_listing=False)

        _link(doces, zebra, 1)
        _link(doces, baguete, 2)  # empata com o alfajor no sort_order: desempata pelo nome
        _link(doces, alfajor, 2)
        _link(paes, zebra, 5)  # em duas coleções: aparece nas duas
        _link(paes, baguete, 1)
        _link(sazonal, panetone, 1)  # só em coleção inativa: não é "sem coleção"
        _link(doces, rascunho, 0)
        _link(doces, fora, 0)
        assert vazia.pk  # coleção ativa sem produto não vira grupo

        assert _grouped() == [
            ("doces", ["ZEBRA", "ALFAJOR", "BAGUETE"]),
            ("paes", ["BAGUETE", "ZEBRA"]),
            (None, ["CROISSANT"]),
        ]
        assert croissant.pk

    def test_query_count_does_not_grow_with_active_collections(self, listing):
        products = [_product(listing, f"P{i}", f"Produto {i}") for i in range(6)]
        few = [Collection.objects.create(ref=f"c{i}", name=f"C{i}", is_active=True, sort_order=i) for i in range(2)]
        for index, product in enumerate(products):
            _link(few[index % 2], product, index)

        with CaptureQueriesContext(connection) as two:
            _grouped()

        for i in range(2, 8):
            collection = Collection.objects.create(ref=f"c{i}", name=f"C{i}", is_active=True, sort_order=i)
            _link(collection, products[i % len(products)], 0)

        with CaptureQueriesContext(connection) as eight:
            groups = _grouped()

        assert len(groups) == 8
        assert len(eight.captured_queries) == len(two.captured_queries)

    def test_empty_listing(self, listing):
        assert _grouped() == []


class TestFeaturedItems:
    @pytest.fixture
    def menu(self, listing):
        rusticos = Collection.objects.create(ref="rusticos", name="Rústicos", is_active=True, sort_order=1)
        doces = Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=2)
        for index, (sku, name, collection) in enumerate([
            ("BAGUETE", "Baguete", rusticos),
            ("CIABATTA", "Ciabatta", rusticos),
            ("MELON", "Melon pan", doces),
            ("CROISSANT", "Croissant", doces),
            ("BRIOCHE", "Brioche", doces),
        ]):
            _link(collection, _product(listing, sku, name), index)
        _link(rusticos, Product.objects.get(sku="MELON"), 9)  # em duas coleções
        _product(listing, "SOLTO", "Sem coleção")

    def _same_as_full_catalog(self, rf):
        request = rf.get("/")
        catalog = build_catalog(channel_ref="web", request=request)
        expected = [projection_data(i) for i in (catalog.featured or catalog.items)[:3]]
        got = [projection_data(i) for i in build_featured_items(channel_ref="web", request=request, limit=3)]
        assert got == expected
        return [card["sku"] for card in got]

    def test_popular_products_in_menu_order(self, rf, menu, monkeypatch):
        monkeypatch.setattr(catalog_module, "popular_skus", lambda limit=5: {"BRIOCHE", "MELON", "SOLTO"})
        # MELON está em duas coleções: o cardápio o destaca duas vezes, e a home também.
        assert self._same_as_full_catalog(rf) == ["MELON", "MELON", "BRIOCHE"]

    def test_without_popular_products_takes_the_first_cards(self, rf, menu, monkeypatch):
        monkeypatch.setattr(catalog_module, "popular_skus", lambda limit=5: set())
        assert self._same_as_full_catalog(rf) == ["BAGUETE", "CIABATTA", "MELON"]

    def test_fewer_popular_than_the_rail(self, rf, menu, monkeypatch):
        monkeypatch.setattr(catalog_module, "popular_skus", lambda limit=5: {"SOLTO"})
        assert self._same_as_full_catalog(rf) == ["SOLTO"]

    def test_empty_catalog(self, rf, listing):
        assert build_featured_items(channel_ref="web", request=rf.get("/")) == ()

    def test_home_does_not_build_the_full_catalog(self, rf, menu, monkeypatch):
        def full_catalog(*_args, **_kwargs):
            raise AssertionError("a home montou o cardápio inteiro para guardar três cards")

        monkeypatch.setattr(catalog_module, "build_catalog", full_catalog)
        home = home_module.build_home(rf.get("/"))
        assert len(home.featured_items) == 3
