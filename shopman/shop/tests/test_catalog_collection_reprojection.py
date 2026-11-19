"""A coleção primária é a categoria no iFood: trocar reenvia o item (DEV-2026-044).

O iFood é reflexo do Catálogo da casa. Mudar a coleção primária de um produto que
já está no canal, ou mudar a categoria do iFood de uma coleção, tem que reenviar os
itens afetados pelo mesmo ``catalog.project_sku``. Produto fora do listing do canal
não é reenviado: incluir no canal é gesto explícito.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db

_OFFERMAN_IFOOD = {
    "COST_BACKEND": None,
    "PRICING_BACKEND": "shopman.shop.adapters.pricing.PromotionPricingBackend",
    "PROJECTION_BACKENDS": {"ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"},
}


@pytest.fixture(autouse=True)
def projection_registry():
    from shopman.offerman.conf import reset_projection_backends

    reset_projection_backends()
    with override_settings(OFFERMAN=_OFFERMAN_IFOOD):
        yield
    reset_projection_backends()


@pytest.fixture
def ifood():
    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    return Listing.objects.create(ref="ifood", name="iFood")


def _triggers(sku: str) -> list[str]:
    return [
        d.payload.get("trigger")
        for d in Directive.objects.filter(topic=CATALOG_PROJECT_SKU, payload__sku=sku).order_by("pk")
    ]


def test_primary_collection_change_resends_an_item_already_in_the_channel(ifood):
    product = Product.objects.create(sku="PAO", name="Pão", unit="un", base_price_q=1000)
    ListingItem.objects.create(listing=ifood, product=product, price_q=1000)
    collection = Collection.objects.create(ref="paes", name="Pães")

    CollectionItem.objects.create(collection=collection, product=product, is_primary=True)

    assert "collection_changed" in _triggers("PAO")


def test_collection_change_does_not_include_a_product_outside_the_channel(ifood):
    product = Product.objects.create(sku="BOLO", name="Bolo", unit="un", base_price_q=1000)
    collection = Collection.objects.create(ref="doces", name="Doces")

    CollectionItem.objects.create(collection=collection, product=product, is_primary=True)

    assert "collection_changed" not in _triggers("BOLO")


def test_new_category_for_a_collection_resends_its_items(ifood):
    from shopman.shop.services.ifood_catalog_categories import set_collection_category

    product = Product.objects.create(sku="CROI", name="Croissant", unit="un", base_price_q=1000)
    ListingItem.objects.create(listing=ifood, product=product, price_q=1000)
    collection = Collection.objects.create(ref="folhados", name="Folhados")
    CollectionItem.objects.create(collection=collection, product=product, is_primary=True)
    Directive.objects.all().delete()

    set_collection_category(channel_ref="ifood", collection_ref="folhados", category_ref="cat-1")

    assert _triggers("CROI") == ["category_changed"]
