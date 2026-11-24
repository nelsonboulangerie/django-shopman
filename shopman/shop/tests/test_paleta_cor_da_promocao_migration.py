"""``shop.0139``: a paleta salva ganha ``promotion`` por tema sem mudar a cor de quem não é a Nelson (OC-30)."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0139_paleta_cor_da_promocao")


def _shop(palette):
    shop = Shop.objects.first() or Shop.objects.create(name="Loja")
    Shop.objects.filter(pk=shop.pk).update(brand_palette=palette)
    return shop


def _run():
    migration.add_promotion(apps, None)


def test_a_paleta_escura_da_nelson_ganha_o_burgundy_300():
    shop = _shop({"light": {"primary": "124 58 64"}, "dark": {"primary": "154 79 86"}})
    _run()
    shop.refresh_from_db()
    assert shop.brand_palette["light"]["promotion"] == "124 58 64"
    assert shop.brand_palette["dark"]["promotion"] == "185 123 130"


def test_outra_marca_fica_com_o_proprio_primary():
    shop = _shop({"light": {"primary": "10 20 30"}, "dark": {"primary": "200 100 50"}})
    _run()
    shop.refresh_from_db()
    assert shop.brand_palette["light"]["promotion"] == "10 20 30"
    assert shop.brand_palette["dark"]["promotion"] == "200 100 50"


def test_promocao_ja_escolhida_e_loja_sem_paleta_ficam_como_estao():
    shop = _shop({"light": {"primary": "124 58 64", "promotion": "1 2 3"}, "dark": {"primary": "154 79 86", "promotion": "4 5 6"}})
    _run()
    shop.refresh_from_db()
    assert shop.brand_palette["light"]["promotion"] == "1 2 3"
    assert shop.brand_palette["dark"]["promotion"] == "4 5 6"

    Shop.objects.filter(pk=shop.pk).update(brand_palette={})
    _run()
    shop.refresh_from_db()
    assert shop.brand_palette == {}
