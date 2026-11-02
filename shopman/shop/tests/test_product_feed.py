"""Product feed — canal de exibição da Meta, RSS 2.0 público. O Google não tem feed."""

from __future__ import annotations

from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Shop
from shopman.shop.tests._display import display_channel

G = "{http://base.google.com/ns/1.0}"


LOJA = "https://www.loja.test"


@pytest.fixture
def feed(db, settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = LOJA
    Shop.objects.create(name="Nelson Boulangerie")
    display_channel("meta", "Meta", collections=["vitrine"], fmt="meta_catalog", prices_from="web")
    display_channel("meta-b", "Meta B", collections=["vitrine"], fmt="meta_catalog", prices_from="web")
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    com_foto = Product.objects.create(
        sku="BAGUETE", name="Baguete", unit="un", base_price_q=1300,
        is_published=True, is_sellable=True, image_url="https://cdn.test/baguete.jpg",
        long_description="Pão de tradição francesa",
    )
    sem_foto = Product.objects.create(
        sku="SEMFOTO", name="Sem Foto", unit="un", base_price_q=500, is_published=True, is_sellable=True,
    )
    CollectionItem.objects.create(collection=vitrine, product=com_foto)
    CollectionItem.objects.create(collection=vitrine, product=sem_foto)
    return {"com_foto": com_foto}


def _items(xml: bytes):
    return ET.fromstring(xml).find("channel").findall("item")


def test_feed_is_valid_meta_rss(client, feed):
    resp = client.get("/feed/meta.xml")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/xml")
    items = _items(resp.content)
    assert len(items) == 1  # só o produto COM imagem
    item = items[0]
    assert item.find(f"{G}id").text == "BAGUETE"
    # A página do produto é da LOJA, não do host que serviu o feed.
    assert item.find(f"{G}link").text == f"{LOJA}/produto/BAGUETE"
    assert ET.fromstring(resp.content).find("channel").find("link").text == LOJA
    assert item.find(f"{G}price").text == "13.00 BRL"
    assert item.find(f"{G}availability").text == "in stock"  # meta = espaço (verificado)
    assert item.find(f"{G}brand") is None  # marca da loja não prova a marca do produto
    assert item.find(f"{G}identifier_exists") is None  # vazio não comprova ausência
    assert item.find(f"{G}custom_label_0").text == "vitrine"  # coleção do feed
    assert item.find(f"{G}product_type").text == "Vitrine"
    assert item.find(f"{G}excluded_destination") is None  # atributo do Google


def test_google_channel_has_no_feed(client, feed):
    """O canal do Google é escrito só pela Merchant API: a rota do XML não o serve."""
    display_channel("google", "Google Shopping", collections=["vitrine"], fmt="google_merchant", prices_from="web")
    assert client.get("/feed/google.xml").status_code == 404


def test_feed_uses_product_commercial_attributes(client, feed):
    product = feed["com_foto"]
    product.metadata = {"social": {
        "brand": "Fabricante & Filhos", "gtin": "4006381333931",
        "mpn": "REF<123>", "condition": "new", "google_product_category": "250",
    }}
    product.save()
    item = _items(client.get("/feed/meta.xml").content)[0]
    for field, value in product.metadata["social"].items():
        assert item.find(f"{G}{field}").text == value
    assert item.find(f"{G}identifier_exists") is None


def test_feed_preserves_mpn_without_gtin(client, feed):
    product = feed["com_foto"]
    product.metadata = {"social": {"brand": "Nelson", "mpn": "BAGUETE"}}
    product.save()
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}mpn").text == "BAGUETE"
    assert item.find(f"{G}gtin") is None
    assert item.find(f"{G}identifier_exists") is None


@pytest.mark.parametrize("condition", ["used", "refurbished"])
def test_feed_preserves_condition(client, feed, condition):
    product = feed["com_foto"]
    product.metadata = {"social": {"condition": condition}}
    product.save()
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}condition").text == condition


def test_feed_does_not_hide_shop_database_failure(client, feed):
    from django.db import OperationalError

    with patch.object(Shop.objects, "only", side_effect=OperationalError("indisponível")):
        with pytest.raises(OperationalError):
            client.get("/feed/meta.xml")


def test_paused_is_out_of_stock(client, feed):
    feed["com_foto"].is_sellable = False
    feed["com_foto"].save()
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}availability").text == "out of stock"


def _set_display(ref: str, **values):
    from shopman.shop.models import Channel
    channel = Channel.objects.get(ref=ref)
    channel.config = {**channel.config, "display": {**channel.config["display"], **values}}
    channel.save(update_fields=["config"])


def test_local_pause_is_out_of_stock(client, feed):
    """Pausa por-canal (display.paused_skus) marca out of stock só neste feed."""
    _set_display("meta", paused_skus=["BAGUETE"])
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}availability").text == "out of stock"
    assert item.find("status") is None  # Pausar = visível, sem compra
    # o outro feed (sem pausa local) segue in stock
    other = _items(client.get("/feed/meta-b.xml").content)[0]
    assert other.find(f"{G}availability").text == "in stock"


def test_local_hide_archives_the_meta_item(client, feed):
    """Ocultar = some do canal, mas o item fica no XML (tirar apagaria o produto na Meta)."""
    _set_display("meta", hidden_skus=["BAGUETE"])
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find("status").text == "archived"  # sem prefixo g: (fora da spec g:)
    # o outro feed (sem ocultação local) segue ativo
    other = _items(client.get("/feed/meta-b.xml").content)[0]
    assert other.find("status") is None
    assert other.find(f"{G}availability").text == "in stock"


def test_hidden_product_is_archived(client, feed):
    feed["com_foto"].is_published = False
    feed["com_foto"].save()
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find("status").text == "archived"


def test_hide_wins_over_pause(client, feed):
    _set_display("meta", paused_skus=["BAGUETE"], hidden_skus=["BAGUETE"])
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find("status").text == "archived"


def test_smart_collection_feed(client, db, settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = LOJA
    display_channel("caros", "Caros", collections=["regra"], fmt="meta_catalog", prices_from="web")
    Collection.objects.create(
        ref="regra", name="Regra", is_active=True,
        rule={"match": "all", "conditions": [{"field": "base_price_q", "op": "gte", "value": 1000}]},
    )
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True, image_url="https://cdn.test/bolo.jpg")
    Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True, image_url="https://cdn.test/pao.jpg")
    assert [i.find(f"{G}id").text for i in _items(client.get("/feed/caros.xml").content)] == ["BOLO"]


def test_menuboard_is_not_a_feed(client, db):
    """Canal SEM formato é quadro, não feed: o feed recusa."""
    display_channel("tv", "TV", collections=["x"], prices_from="pdv")
    assert client.get("/feed/tv.xml").status_code == 404


def test_unknown_404(client, db):
    assert client.get("/feed/fantasma.xml").status_code == 404


def test_feed_price_comes_from_the_channel_it_points_at(client, feed):
    """O feed público anuncia o preço da LOJA ONLINE, não o de tabela.

    Preço alcançável publicamente vincula o fornecedor: quem clica no anúncio compra
    na loja, então é o preço da loja que o anúncio tem de dizer.
    """
    from shopman.offerman.models import Listing, ListingItem

    web = Listing.objects.create(ref="web", name="Loja online")
    ListingItem.objects.create(listing=web, product=feed["com_foto"], price_q=2500)

    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}price").text == "25.00 BRL"


def test_feed_link_ignores_the_host_that_served_the_feed(client, feed, settings):
    """O feed sai do Django headless (api.), que não tem página de produto."""
    settings.ALLOWED_HOSTS = ["api.loja.test"]
    resp = client.get("/feed/meta.xml", HTTP_HOST="api.loja.test")
    assert resp.status_code == 200
    link = _items(resp.content)[0].find(f"{G}link").text
    assert link == f"{LOJA}/produto/BAGUETE"
    assert "api.loja.test" not in resp.content.decode()


def test_feed_without_storefront_base_fails_closed(client, feed, settings):
    """Sem a base da loja não há link certo; feed com link 404 é reprovado item a item."""
    settings.SHOPMAN_STOREFRONT_BASE_URL = ""
    assert client.get("/feed/meta.xml").status_code == 404
