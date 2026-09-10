"""``bootstrap_whatsapp_channel``: liga canal e vitrine no banco vivo, sem reseed."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def web_listing():
    Shop.objects.create(name="Nelson Boulangerie")
    web = Listing.objects.create(ref="web", name="Loja online", priority=7)
    pao = Product.objects.create(sku="PAO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    bolo = Product.objects.create(sku="BOLO", name="Bolo", base_price_q=4500, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=web, product=pao, price_q=550, is_published=True, is_sellable=True)
    ListingItem.objects.create(listing=web, product=bolo, price_q=4500, is_published=False, is_sellable=False)
    return web


def _run(*args) -> str:
    out = StringIO()
    call_command("bootstrap_whatsapp_channel", *args, stdout=out)
    return out.getvalue()


def test_cria_canal_e_espelha_a_vitrine_da_loja(web_listing):
    out = _run()

    channel = Channel.objects.get(ref="whatsapp")
    assert channel.is_active is True
    assert channel.config["payment"]["timing"] == "at_commit"
    assert channel.config["payment"]["method"] == ["pix", "card"]
    assert channel.config["notifications"]["backend"] == "manychat"

    listing = Listing.objects.get(ref="whatsapp")
    items = {i.product.sku: i for i in ListingItem.objects.filter(listing=listing).select_related("product")}
    assert set(items) == {"PAO", "BOLO"}
    assert items["PAO"].price_q == 550 and items["PAO"].is_published is True
    assert items["BOLO"].price_q == 4500 and items["BOLO"].is_published is False and items["BOLO"].is_sellable is False
    assert "criado" in out and "2 item(ns)" in out


def test_segunda_rodada_nao_muda_nada(web_listing):
    _run()
    before = list(ListingItem.objects.filter(listing__ref="whatsapp").values_list("id", "price_q"))
    out = _run()
    after = list(ListingItem.objects.filter(listing__ref="whatsapp").values_list("id", "price_q"))
    assert before == after
    assert "nada a fazer" in out and "nada a copiar" in out


def test_nao_sobrescreve_edicao_do_admin_e_copia_so_o_que_falta(web_listing):
    Channel.objects.create(
        ref="whatsapp", name="Zap", is_active=False,
        config={"payment": {"timing": "post_commit", "timeout_minutes": 30}, "confirmation": {"mode": "manual"}},
    )
    whatsapp = Listing.objects.create(ref="whatsapp", name="WhatsApp")
    pao = Product.objects.get(sku="PAO")
    ListingItem.objects.create(listing=whatsapp, product=pao, price_q=999)

    _run()

    channel = Channel.objects.get(ref="whatsapp")
    assert channel.is_active is True
    assert channel.name == "Zap"
    # A chave que existia fica; só entra a que faltava.
    assert channel.config["payment"] == {"timing": "post_commit", "timeout_minutes": 30, "method": ["pix", "card"]}
    assert channel.config["confirmation"] == {"mode": "manual"}
    assert channel.config["notifications"] == {"backend": "manychat"}

    items = {i.product.sku: i.price_q for i in ListingItem.objects.filter(listing=whatsapp).select_related("product")}
    assert items == {"PAO": 999, "BOLO": 4500}


def test_dry_run_nao_grava(web_listing):
    out = _run("--dry-run")
    assert "Simulação" in out
    assert "PAO" in out and "BOLO" in out
    assert not Channel.objects.filter(ref="whatsapp").exists()
    assert not Listing.objects.filter(ref="whatsapp").exists()
    assert ListingItem.objects.filter(listing__ref="whatsapp").count() == 0


def test_sem_vitrine_da_loja_avisa_e_nao_quebra():
    out = _run()
    assert Channel.objects.filter(ref="whatsapp", is_active=True).exists()
    assert Listing.objects.filter(ref="whatsapp").exists()
    assert "não existe" in out
