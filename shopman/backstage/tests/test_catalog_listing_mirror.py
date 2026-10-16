"""Catálogo do gestor x vitrine espelhada (P1-14): o WhatsApp segue a loja online."""

from __future__ import annotations

import pytest
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.services import catalog as service
from shopman.backstage.services.exceptions import CatalogError
from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def lojas():
    web = Listing.objects.create(ref="web", name="Loja online", priority=7)
    Channel.objects.create(ref="web", name="Loja online", is_active=True, display_order=2)
    for sku, price in (("PAO", 550), ("BOLO", 4500)):
        product = Product.objects.create(sku=sku, name=sku, base_price_q=price, is_published=True, is_sellable=True)
        ListingItem.objects.create(listing=web, product=product, price_q=price)
    Channel.objects.create(
        ref="whatsapp", name="WhatsApp", is_active=True, display_order=4,
        config={"pricing": {"listing_from": "web"}},
    )
    return web


def _price(ref: str, sku: str) -> int:
    return ListingItem.objects.get(listing__ref=ref, product__sku=sku).price_q


def test_celula_do_whatsapp_recusa_com_o_motivo(lojas):
    with pytest.raises(CatalogError, match="A vitrine de WhatsApp segue a de Loja online"):
        service.set_cell("PAO", "whatsapp", price_q=999)
    assert _price("whatsapp", "PAO") == 550


def test_celula_do_site_chega_ao_whatsapp(lojas):
    service.set_cell("PAO", "web", price_q=600)
    assert _price("whatsapp", "PAO") == 600


def test_lote_de_preco_no_site_chega_ao_whatsapp(lojas):
    """``bulk_update`` não dispara signal: o lote realinha o espelho ao terminar."""
    assert service.bulk_price(["PAO", "BOLO"], "web", op="delta", value=100) == 2
    assert (_price("whatsapp", "PAO"), _price("whatsapp", "BOLO")) == (650, 4600)


def test_lote_de_pausa_no_site_chega_ao_whatsapp(lojas):
    service.bulk_set(["PAO"], "web", is_sellable=False)
    assert ListingItem.objects.get(listing__ref="whatsapp", product__sku="PAO").is_sellable is False


def test_lote_no_whatsapp_recusa(lojas):
    with pytest.raises(CatalogError, match="segue a de Loja online"):
        service.bulk_price(["PAO"], "whatsapp", op="set", value=1)
    with pytest.raises(CatalogError, match="segue a de Loja online"):
        service.bulk_set(["PAO"], "whatsapp", is_published=False)


def test_todos_os_canais_escreve_na_fonte_e_o_espelho_acompanha(lojas):
    assert service.bulk_price(["PAO"], service.ALL_SURFACES, op="set", value=700) == 1
    assert (_price("web", "PAO"), _price("whatsapp", "PAO")) == (700, 700)
