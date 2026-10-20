"""Modo de produção da ficha: "Em lote" é planejado; "Na hora" nunca tem ordem de produção."""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.models import ProductionMode, Recipe, WorkOrder
from shopman.craftsman.services import CraftPlanning, production_modes_for_output_skus

pytestmark = pytest.mark.django_db


def _recipe(ref: str, sku: str, *, mode: str = ProductionMode.BATCH, active: bool = True) -> Recipe:
    return Recipe.objects.create(
        ref=ref, name=ref, output_sku=sku, batch_size=Decimal("1"), is_active=active, production_mode=mode,
    )


def test_ficha_nasce_em_lote():
    assert _recipe("pao", "PAO").production_mode == ProductionMode.BATCH


def test_modos_em_lote_so_da_ficha_vigente():
    _recipe("pao", "PAO")
    _recipe("cafe", "CAFE", mode=ProductionMode.MADE_TO_ORDER)
    _recipe("cha-velho", "CHA", mode=ProductionMode.MADE_TO_ORDER, active=False)

    assert production_modes_for_output_skus(["PAO", "CAFE", "CHA", "AGUA", ""]) == {
        "PAO": ProductionMode.BATCH,
        "CAFE": ProductionMode.MADE_TO_ORDER,
    }
    assert production_modes_for_output_skus([]) == {}


def test_na_hora_nao_tem_ordem_de_producao():
    cafe = _recipe("cafe", "CAFE", mode=ProductionMode.MADE_TO_ORDER)

    with pytest.raises(CraftError) as exc:
        CraftPlanning.plan(cafe, 5)

    assert exc.value.code == "MADE_TO_ORDER_RECIPE"
    assert not WorkOrder.objects.exists()


def test_em_lote_planeja():
    pao = _recipe("pao", "PAO")
    assert CraftPlanning.plan(pao, 5).output_sku == "PAO"
