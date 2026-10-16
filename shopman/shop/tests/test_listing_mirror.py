"""A vitrine do WhatsApp espelha a da loja online sem ninguém rodar comando (P1-14)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import transaction
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.offerman.service import CatalogService

from shopman.shop.models import Channel
from shopman.shop.services import listing_mirror

pytestmark = pytest.mark.django_db


@pytest.fixture
def lojas():
    web = Listing.objects.create(ref="web", name="Loja online", priority=7)
    Channel.objects.create(ref="web", name="Loja online", is_active=True)
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=web, product=pao, price_q=550)
    Channel.objects.create(
        ref="whatsapp", name="WhatsApp", is_active=True, config={"pricing": {"listing_from": "web"}},
    )
    return web


def _whatsapp() -> dict:
    return {
        (row.product.sku, row.min_qty): (row.price_q, row.is_published, row.is_sellable)
        for row in ListingItem.objects.filter(listing__ref="whatsapp").select_related("product")
    }


def test_ligar_o_ponteiro_no_canal_ja_alinha_a_vitrine(lojas):
    assert Listing.objects.filter(ref="whatsapp").exists()
    assert _whatsapp() == {("PAO", Decimal("1")): (550, True, True)}


def test_produto_novo_no_site_aparece_no_whatsapp(lojas):
    bolo = Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=lojas, product=bolo, price_q=4800)

    assert _whatsapp()[("BOLO", Decimal("1"))] == (4800, True, True)
    assert CatalogService.unit_price("BOLO", channel="whatsapp") == 4800


def test_preco_e_faixa_mudados_no_site_chegam_ao_whatsapp(lojas):
    item = ListingItem.objects.get(listing=lojas, product__sku="PAO")
    item.price_q = 600
    item.save()
    ListingItem.objects.create(listing=lojas, product=item.product, price_q=450, min_qty=Decimal("10"))

    assert _whatsapp() == {
        ("PAO", Decimal("1")): (600, True, True),
        ("PAO", Decimal("10")): (450, True, True),
    }
    assert CatalogService.unit_price("PAO", qty=Decimal("12"), channel="whatsapp") == 450


def test_despublicado_ou_pausado_no_site_some_do_whatsapp(lojas):
    item = ListingItem.objects.get(listing=lojas, product__sku="PAO")
    item.is_published = False
    item.is_sellable = False
    item.save(update_fields=["is_published", "is_sellable"])

    assert _whatsapp() == {("PAO", Decimal("1")): (550, False, False)}


def test_item_tirado_do_site_sai_do_whatsapp(lojas):
    ListingItem.objects.filter(listing=lojas, product__sku="PAO").delete()

    assert _whatsapp() == {}


def test_edicao_direta_no_whatsapp_volta_a_ser_a_do_site(lojas):
    item = ListingItem.objects.get(listing__ref="whatsapp", product__sku="PAO")
    item.price_q = 999
    item.save()
    extra = Product.objects.create(sku="XEPA", name="Só no zap", base_price_q=100, is_published=True)
    ListingItem.objects.create(listing=item.listing, product=extra, price_q=100)

    assert _whatsapp() == {("PAO", Decimal("1")): (550, True, True)}


def test_escrita_que_volta_atras_leva_o_espelho_junto(lojas):
    item = ListingItem.objects.get(listing=lojas, product__sku="PAO")
    with pytest.raises(RuntimeError), transaction.atomic():
        item.price_q = 700
        item.save()
        assert _whatsapp()[("PAO", Decimal("1"))][0] == 700
        raise RuntimeError

    assert _whatsapp()[("PAO", Decimal("1"))][0] == 550


def test_canal_sem_ponteiro_tem_vitrine_propria(lojas):
    Channel.objects.create(ref="pdv", name="PDV", is_active=True)
    pdv = Listing.objects.create(ref="pdv", name="PDV")
    pao = Product.objects.get(sku="PAO")
    ListingItem.objects.create(listing=pdv, product=pao, price_q=480)

    item = ListingItem.objects.get(listing=lojas, product=pao)
    item.price_q = 610
    item.save()

    assert ListingItem.objects.get(listing=pdv, product=pao).price_q == 480


def test_ponteiro_na_config_da_loja_nao_vira_espelho_de_todo_canal(lojas):
    """Lido cru do canal: um default da casa não pode ligar o espelho em todo canal."""
    from shopman.shop.models import Shop

    Shop.objects.create(name="Nelson", defaults={"pricing": {"listing_from": "web"}})
    Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    assert listing_mirror.source_ref("pdv") == ""
    assert listing_mirror.mirror_refs("web") == ["whatsapp"]


def test_fonte_inexistente_nao_apaga_o_espelho(lojas):
    channel = Channel.objects.get(ref="whatsapp")
    channel.config = {"pricing": {"listing_from": "nao-existe"}}
    channel.save()

    assert _whatsapp() == {("PAO", Decimal("1")): (550, True, True)}


def test_realinhar_sem_diferenca_nao_grava(lojas):
    assert listing_mirror.realign("web").changed == 0
    assert listing_mirror.realign("whatsapp").changed == 0
