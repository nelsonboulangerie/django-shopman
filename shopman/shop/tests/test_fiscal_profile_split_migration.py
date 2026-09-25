"""Migração 0075: quem é produzido aqui vira `own_production`, quem é comprado pronto vira `resale`."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0075_perfil_fiscal_producao_revenda_st")


def _product(sku: str, profile: str, **fiscal) -> Product:
    return Product.objects.create(
        sku=sku, name=sku, unit="un", base_price_q=1000,
        metadata={"fiscal": {"profile": profile, "ncm": "19059090", **fiscal}},
    )


def _profile(sku: str) -> str:
    return Product.objects.get(sku=sku).metadata["fiscal"]["profile"]


def test_os_perfis_antigos_viram_os_tres():
    _product("PAO", "standard", cest="1706200")
    _product("CAFE", "standard")  # bebida preparada: sem cadastro de compra, sem ficha
    _product("GELEIA", "standard", cest="1709400")
    Material.objects.create(sku="GELEIA", name="Geleia", unit="un")
    _product("AGUA", "tax_substitution", cest="0300500")
    Material.objects.create(sku="AGUA", name="Água", unit="un")
    # Comprável E produzido aqui: a ficha ativa manda, é produção própria.
    _product("MANTEIGA-DA-CASA", "standard")
    Material.objects.create(sku="MANTEIGA-DA-CASA", name="Manteiga", unit="un")
    Recipe.objects.create(ref="manteiga-da-casa", name="Manteiga", output_sku="MANTEIGA-DA-CASA", batch_size=1)

    migration.forward(apps, None)

    assert _profile("PAO") == "own_production"
    assert _profile("CAFE") == "own_production"
    assert _profile("GELEIA") == "resale"
    assert _profile("AGUA") == "resale_tax_substitution"
    assert _profile("MANTEIGA-DA-CASA") == "own_production"
    assert Product.objects.get(sku="PAO").metadata["fiscal"]["cest"] == "1706200"
