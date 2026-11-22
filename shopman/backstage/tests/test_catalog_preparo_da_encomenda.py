"""Preparo da encomenda no painel do produto do Catálogo do Gestor (#2304).

O preparo por SKU mora em ``Shop.defaults["preorder_kitchen"]["prep_minutes_by_sku"]``
desde o #2303, editado no Admin. O painel do produto edita o MESMO valor: não há
segunda fonte, e o Admin continua mostrando o que o painel gravou.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

from shopman.backstage.services import catalog
from shopman.backstage.services.exceptions import CatalogConflict, CatalogError
from shopman.shop.models import Shop
from shopman.shop.policies.preorder_kitchen_policy import resolve_preorder_kitchen_policy

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja():
    return Shop.objects.create(
        name="Loja",
        defaults={"preorder_kitchen": {"lead_minutes": 15, "default_prep_minutes": 40, "prep_minutes_by_sku": {"BOLO": 90}}},
    )


@pytest.fixture
def baguete():
    return Product.objects.create(sku="BAGUETE", name="Baguete", base_price_q=1200)


def _by_sku() -> dict:
    return dict(Shop.objects.get().defaults["preorder_kitchen"]["prep_minutes_by_sku"])


def test_o_detalhe_mostra_o_preparo_proprio_e_o_padrao_da_loja(loja, baguete):
    detail = catalog.get_product_detail("BAGUETE")
    assert detail["preorder_prep_minutes"] is None
    assert detail["preorder_prep_default_minutes"] == 40

    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=5000)
    assert catalog.get_product_detail("BOLO")["preorder_prep_minutes"] == 90


def test_gravar_escreve_na_mesma_fonte_do_admin_sem_tocar_no_resto(loja, baguete):
    result = catalog.update_product_detail("BAGUETE", {"preorder_prep_minutes": 20})

    assert result["preorder_prep_minutes"] == 20
    assert _by_sku() == {"BOLO": 90, "BAGUETE": 20}
    kitchen = Shop.objects.get().defaults["preorder_kitchen"]
    assert kitchen["lead_minutes"] == 15
    assert kitchen["default_prep_minutes"] == 40
    # A política que decide a hora de a encomenda chegar à Cozinha lê o valor novo.
    assert resolve_preorder_kitchen_policy().prep_minutes_for(["BAGUETE"]) == 20


def test_em_branco_devolve_o_sku_ao_preparo_padrao(loja):
    Product.objects.create(sku="BOLO", name="Bolo", base_price_q=5000)
    result = catalog.update_product_detail("BOLO", {"preorder_prep_minutes": None})

    assert result["preorder_prep_minutes"] is None
    assert _by_sku() == {}
    assert resolve_preorder_kitchen_policy().prep_minutes_for(["BOLO"]) == 40


@pytest.mark.parametrize("invalid", [-1, 721, True, "vinte"])
def test_fora_da_regua_e_recusado_e_nada_grava_pela_metade(loja, baguete, invalid):
    with pytest.raises(CatalogError):
        catalog.update_product_detail("BAGUETE", {"name": "Baguete nova", "preorder_prep_minutes": invalid})
    baguete.refresh_from_db()
    assert baguete.name == "Baguete"
    assert _by_sku() == {"BOLO": 90}


def test_o_preparo_tem_revisao_e_a_tela_velha_e_recusada(loja, baguete):
    revisions = catalog.product_field_revisions(catalog.get_product_detail("BAGUETE"))
    assert "preorder_prep_minutes" in revisions
    assert "preorder_prep_default_minutes" not in revisions

    # Outra pessoa grava pelo Admin depois que a tela leu.
    shop = Shop.objects.get()
    defaults = dict(shop.defaults)
    defaults["preorder_kitchen"] = {**defaults["preorder_kitchen"], "prep_minutes_by_sku": {"BOLO": 90, "BAGUETE": 35}}
    shop.defaults = defaults
    shop.save()

    with pytest.raises(CatalogConflict):
        catalog.update_product_detail(
            "BAGUETE", {"preorder_prep_minutes": 20}, expected_revisions={"preorder_prep_minutes": revisions["preorder_prep_minutes"]},
        )
    assert _by_sku()["BAGUETE"] == 35
