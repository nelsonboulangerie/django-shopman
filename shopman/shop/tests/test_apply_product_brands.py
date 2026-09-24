"""`apply_product_brands`: a marca da casa nos feitos aqui, a do fabricante na revenda.

A tabela mora em `config/` (é dado do Nelson). O seed chama a mesma função, então
um banco novo nasce com as marcas que o comando aplica num banco que já roda.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.offerman import get_social_attributes
from shopman.offerman.contrib.social.schema import gtin_is_valid
from shopman.offerman.models import Product

from config.management.commands.apply_product_brands import HOUSE_SKUS, RESALE, apply_brands
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


def _product(sku: str, **metadata) -> Product:
    return Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=100, metadata=metadata)


@pytest.fixture
def shop():
    return Shop.objects.create(name="Nelson Boulangerie LTDA", brand_name="Nelson Boulangerie")


def test_casa_leva_a_marca_da_loja_e_revenda_a_do_fabricante(shop):
    _product("CRO")
    _product("QUEIJO-CAMEMBERT-ILEDEFRANCE-125")

    call_command("apply_product_brands", "--apply", stdout=StringIO())

    assert get_social_attributes(Product.objects.get(sku="CRO")).brand == "Nelson Boulangerie"
    camembert = get_social_attributes(Product.objects.get(sku="QUEIJO-CAMEMBERT-ILEDEFRANCE-125"))
    assert (camembert.brand, camembert.gtin) == ("Ile de France", "3161712996108")


def test_sem_apply_nao_grava(shop):
    _product("CRO")

    out = StringIO()
    call_command("apply_product_brands", stdout=out)

    assert "CRO" in out.getvalue()
    assert get_social_attributes(Product.objects.get(sku="CRO")).brand == ""


def test_curadoria_do_gestor_vence_e_sai_no_relatorio(shop):
    _product("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", social={"brand": "Président", "gtin": "3228020355741"})

    report = apply_brands(apply=True)

    attrs = get_social_attributes(Product.objects.get(sku="QUEIJO-CAMEMBERT-ILEDEFRANCE-125"))
    assert (attrs.brand, attrs.gtin) == ("Président", "3228020355741")
    assert {(sku, field) for sku, field, *_ in report["conflicts"]} == {("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "brand"), ("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "gtin")}


def test_preserva_o_resto_do_metadata_e_e_idempotente(shop):
    _product("CRO", fiscal={"ncm": "19059090"}, social={"hashtags": ["croissant"]})

    apply_brands(apply=True)
    segunda = apply_brands(apply=True)

    product = Product.objects.get(sku="CRO")
    assert product.metadata["fiscal"] == {"ncm": "19059090"}
    assert product.metadata["social"] == {"brand": "Nelson Boulangerie", "hashtags": ["croissant"]}
    assert segunda["changes"] == []


def test_loja_sem_marca_falha_fechado(db):
    Shop.objects.create(name=" ", brand_name="")
    with pytest.raises(CommandError):
        apply_brands(apply=False)


def test_revenda_nunca_leva_a_marca_da_loja():
    assert not HOUSE_SKUS & set(RESALE)
    assert all("Nelson" not in fields.get("brand", "") for fields in RESALE.values())


def test_todo_gtin_da_tabela_passa_no_digito_verificador():
    for sku, fields in RESALE.items():
        if fields.get("gtin"):
            assert gtin_is_valid(fields["gtin"]), sku


def test_a_tabela_so_nomeia_skus_que_o_seed_cria(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Brands-2026!")
    call_command("seed", verbosity=0)

    semeados = set(Product.objects.values_list("sku", flat=True))
    assert not (HOUSE_SKUS | set(RESALE)) - semeados

    # E o seed já nasce com a marca aplicada.
    croissant = get_social_attributes(Product.objects.get(sku="CRO"))
    assert croissant.brand == Shop.objects.get().brand_name
