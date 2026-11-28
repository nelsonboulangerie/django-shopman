"""``bootstrap_whatsapp_channel``: liga canal e vitrine espelhada no banco vivo, sem reseed."""

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
    assert channel.config["pricing"] == {"listing_from": "web"}

    listing = Listing.objects.get(ref="whatsapp")
    items = {i.product.sku: i for i in ListingItem.objects.filter(listing=listing).select_related("product")}
    assert set(items) == {"PAO", "BOLO"}
    assert items["PAO"].price_q == 550 and items["PAO"].is_published is True
    assert items["BOLO"].price_q == 4500 and items["BOLO"].is_published is False and items["BOLO"].is_sellable is False
    assert "criado" in out and "2 novo(s)" in out


def test_segunda_rodada_nao_muda_nada(web_listing):
    _run()
    before = list(ListingItem.objects.filter(listing__ref="whatsapp").values_list("id", "price_q"))
    out = _run()
    after = list(ListingItem.objects.filter(listing__ref="whatsapp").values_list("id", "price_q"))
    assert before == after
    assert "nada a fazer" in out and "nada a alinhar" in out


def test_nao_sobrescreve_edicao_do_admin_no_canal_e_alinha_a_vitrine(web_listing):
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
    assert channel.config["pricing"] == {"listing_from": "web"}

    # A vitrine espelha: o preço que só o WhatsApp tinha vira o do site.
    items = {i.product.sku: i.price_q for i in ListingItem.objects.filter(listing=whatsapp).select_related("product")}
    assert items == {"PAO": 550, "BOLO": 4500}


def test_depois_do_bootstrap_o_site_chega_ao_whatsapp_sem_rodar_nada(web_listing):
    _run()
    item = ListingItem.objects.get(listing=web_listing, product__sku="PAO")
    item.price_q = 620
    item.save()

    assert ListingItem.objects.get(listing__ref="whatsapp", product__sku="PAO").price_q == 620


def test_ponteiro_vazio_no_canal_mantem_vitrine_propria(web_listing):
    Channel.objects.create(
        ref="whatsapp", name="WhatsApp", is_active=True, config={"pricing": {"listing_from": ""}},
    )
    whatsapp = Listing.objects.create(ref="whatsapp", name="WhatsApp")
    ListingItem.objects.create(listing=whatsapp, product=Product.objects.get(sku="PAO"), price_q=999)

    out = _run()

    assert Channel.objects.get(ref="whatsapp").config["pricing"] == {"listing_from": ""}
    assert list(ListingItem.objects.filter(listing=whatsapp).values_list("price_q", flat=True)) == [999]
    assert "própria" in out


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


def test_canal_criado_nasce_em_aceite_manual_como_o_seed(web_listing):
    """Pedido remoto só é aceito quando uma pessoa confere (seed + migração ``shop.0054``).

    O bootstrap recriava o canal em ``auto_confirm``, desfazendo a decisão da 0054
    em todo banco onde o canal ainda não existia.
    """
    _run()

    confirmation = Channel.objects.get(ref="whatsapp").config["confirmation"]
    assert confirmation == {"mode": "manual", "stale_new_alert_minutes": 10}


def test_o_canal_criado_e_o_que_o_descritor_declara(web_listing):
    """Uma definição só: o canal novo nasce igual ao item ``whatsapp`` do descritor."""
    from config.instance_descriptors import configured_descriptor, declared_channel

    _run()

    declared = declared_channel(configured_descriptor(), "whatsapp")
    channel = Channel.objects.get(ref="whatsapp")
    assert channel.config == declared["config"]["overrides"]
    assert channel.name == declared["config"]["name"]
    assert channel.display_order == declared["config"]["display_order"]


def test_instancia_sem_canal_whatsapp_nao_ganha_canal(web_listing, settings):
    from pathlib import Path

    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(
        Path(__file__).resolve().parents[1] / "instances/counter-minimal.json"
    )

    out = _run()

    assert "não declara o canal 'whatsapp'" in out
    assert not Channel.objects.filter(ref="whatsapp").exists()
    assert not Listing.objects.filter(ref="whatsapp").exists()


def test_o_canal_existente_recebe_o_ponteiro_que_o_descritor_declara(web_listing, settings, tmp_path):
    """O valor das chaves exigidas vem do descritor; o comando só sabe QUAIS são."""
    import json
    from pathlib import Path

    descriptor = json.loads(
        (Path(__file__).resolve().parents[1] / "instances/nelson.json").read_text(encoding="utf-8")
    )
    item = next(c for c in descriptor["bootstrap"]["channels"] if c["ref"] == "whatsapp")
    item["config"]["overrides"]["pricing"]["listing_from"] = "catalogo"
    path = tmp_path / "nelson.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(path)
    Channel.objects.create(ref="whatsapp", name="WhatsApp", is_active=True, config={})

    _run()

    assert Channel.objects.get(ref="whatsapp").config["pricing"] == {"listing_from": "catalogo"}
