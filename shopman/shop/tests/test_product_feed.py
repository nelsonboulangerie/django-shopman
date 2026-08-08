"""Product feed — canal de exibição COM formato (Google/Meta), RSS 2.0 público."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import Shop
from shopman.shop.tests._display import display_channel

G = "{http://base.google.com/ns/1.0}"


@pytest.fixture
def feed(db):
    Shop.objects.create(name="Nelson Boulangerie")
    display_channel("google", "Google Shopping", collections=["vitrine"], fmt="google_merchant", prices_from="web")
    display_channel("meta", "Meta", collections=["vitrine"], fmt="meta_catalog", prices_from="web")
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


def test_feed_is_valid_google_rss(client, feed):
    resp = client.get("/feed/google.xml")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/xml")
    items = _items(resp.content)
    assert len(items) == 1  # só o produto COM imagem
    item = items[0]
    assert item.find(f"{G}id").text == "BAGUETE"
    assert item.find(f"{G}price").text == "13.00 BRL"
    assert item.find(f"{G}availability").text == "in_stock"  # google = underscore
    assert item.find(f"{G}brand").text == "Nelson Boulangerie"
    assert item.find(f"{G}identifier_exists").text == "no"
    assert item.find(f"{G}custom_label_0").text == "vitrine"  # coleção do feed
    assert item.find(f"{G}product_type").text == "Vitrine"


def test_meta_kind_uses_spaced_availability(client, feed):
    item = _items(client.get("/feed/meta.xml").content)[0]
    assert item.find(f"{G}availability").text == "in stock"  # meta = espaço (verificado)


def test_paused_is_out_of_stock(client, feed):
    feed["com_foto"].is_sellable = False
    feed["com_foto"].save()
    item = _items(client.get("/feed/google.xml").content)[0]
    assert item.find(f"{G}availability").text == "out_of_stock"


def test_local_pause_is_out_of_stock(client, feed):
    """Pausa por-canal (display.paused_skus) marca out_of_stock só neste feed."""
    from shopman.shop.models import Channel
    channel = Channel.objects.get(ref="google")
    channel.config = {**channel.config, "display": {**channel.config["display"], "paused_skus": ["BAGUETE"]}}
    channel.save(update_fields=["config"])
    item = _items(client.get("/feed/google.xml").content)[0]
    assert item.find(f"{G}availability").text == "out_of_stock"
    # o feed Meta (sem pausa local) segue in stock
    item_meta = _items(client.get("/feed/meta.xml").content)[0]
    assert item_meta.find(f"{G}availability").text == "in stock"


def test_smart_collection_feed(client, db):
    display_channel("caros", "Caros", collections=["regra"], fmt="google_merchant", prices_from="web")
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

    item = _items(client.get("/feed/google.xml").content)[0]
    assert item.find(f"{G}price").text == "25.00 BRL"
