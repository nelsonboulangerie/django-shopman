"""A loja não resolve códigos antigos pré-go-live."""
import pytest


@pytest.mark.django_db
def test_legacy_sku_map_is_not_exposed(client):
    assert client.get("/api/v1/storefront/sku-redirects/").status_code == 404


@pytest.mark.django_db
def test_old_sku_does_not_resolve_to_current_product(client):
    from shopman.offerman.models import Product

    Product.objects.create(sku="CRO", name="Croissant", unit="un", base_price_q=1000, is_published=True)
    assert client.get("/api/v1/storefront/products/CROISSANT/").status_code == 404
