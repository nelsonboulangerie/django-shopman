"""Contrato de arquivamento do produto no Core."""

from decimal import Decimal

import pytest
from shopman.offerman.adapters.product_info import ProductInfoBackend
from shopman.offerman.adapters.sku_validator import SkuValidator
from shopman.offerman.exceptions import CatalogError
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.offerman.service import CatalogService

pytestmark = pytest.mark.django_db


def _archived_product(*, sku="ARCHIVED"):
    return Product.objects.create(
        sku=sku,
        name="Produto arquivado",
        base_price_q=900,
        is_active=False,
        is_published=True,
        is_sellable=True,
    )


def test_archived_product_is_absent_from_canonical_search_and_api_queryset():
    archived = _archived_product()
    Product.objects.create(sku="ACTIVE", name="Produto ativo")

    assert archived not in CatalogService.search(query="Produto")
    assert list(Product.objects.available_for_sale().values_list("sku", flat=True)) == ["ACTIVE"]


def test_archived_product_is_unavailable_to_sale_decisions_and_price():
    archived = _archived_product()
    listing = Listing.objects.create(ref="ifood", name="iFood")
    ListingItem.objects.create(listing=listing, product=archived, price_q=900)

    validation = CatalogService.validate(archived.sku)
    stock_validation = SkuValidator().validate_sku(archived.sku)
    product_info = ProductInfoBackend().get_product_info(archived.sku)

    assert validation.valid is True
    assert validation.is_published is False
    assert validation.is_sellable is False
    assert validation.message == "Product is archived"
    assert stock_validation.is_published is False
    assert stock_validation.is_sellable is False
    assert product_info.is_active is False
    with pytest.raises(CatalogError, match="SKU_NOT_FOUND"):
        CatalogService.unit_price(archived.sku, qty=Decimal("1"), listing="ifood")


def test_archived_projection_state_retracts_without_erasing_ephemeral_toggles():
    archived = _archived_product()
    listing = Listing.objects.create(ref="ifood", name="iFood")
    ListingItem.objects.create(listing=listing, product=archived, price_q=900)

    [projected] = CatalogService.get_projection_items("ifood")

    assert projected.is_published is False
    assert projected.is_sellable is False
    archived.refresh_from_db()
    assert archived.is_published is True
    assert archived.is_sellable is True


def test_unarchive_restores_previous_publication_and_sellability_states():
    product = Product.objects.create(
        sku="PRESERVED",
        name="Estados preservados",
        is_active=True,
        is_published=False,
        is_sellable=True,
    )
    original_states = (product.is_published, product.is_sellable)

    product.is_active = False
    product.save(update_fields=["is_active"])
    product.is_active = True
    product.save(update_fields=["is_active"])
    product.refresh_from_db()

    assert product.is_active is True
    assert (product.is_published, product.is_sellable) == original_states


def test_archived_product_is_not_listed_published_or_sellable():
    archived = _archived_product()
    listing = Listing.objects.create(ref="ifood", name="iFood")
    ListingItem.objects.create(listing=listing, product=archived, price_q=900)

    assert not CatalogService.get_listed_products("ifood").filter(pk=archived.pk).exists()
    assert CatalogService.is_product_listed(archived, "ifood") is False
    assert CatalogService.is_product_published(archived, "ifood") is False
    assert CatalogService.is_product_sellable(archived, "ifood") is False
