"""A fornada avulsa era o único fechamento sem guardrail de insumo.

``apply_quick_finish`` sem partição chamava ``production_core.quick_finish``
direto, então nunca passava por ``apply_finish`` — logo nunca por
``check_finish_materials``. Sem farinha no estoque a fornada fechava calada, os
insumos "sumiam" no negativo e nenhum alerta subia. Com partição (quiosque de
QC) o mesmo fechamento já era barrado, o que tornava o buraco invisível: a
mesma ação, barrada numa tela e livre na outra.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.stockman.models import Position, PositionKind

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production as backstage_production
from shopman.backstage.services.production import ProductionStockShortError

pytestmark = pytest.mark.django_db

SKU = "PAO-QUICK-GUARD"
FLOUR = "INS-FARINHA-QUICK"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    """Receita com insumo real e ZERO farinha no estoque."""
    recipe = Recipe.objects.create(
        ref="rc-quick-guard", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku=FLOUR, quantity=Decimal("0.5"), unit="kg"
    )
    return recipe


def test_quick_finish_without_partition_blocks_on_missing_material(recipe, vitrine):
    with pytest.raises(ProductionStockShortError) as exc_info:
        backstage_production.apply_quick_finish(
            recipe_id=recipe.pk,
            quantity=Decimal("10"),
            position_id=None,
            actor="test",
        )

    assert FLOUR in str(exc_info.value)


def test_quick_finish_without_partition_alerts_when_forced(recipe, vitrine):
    """``force`` segue passando, mas deixa rastro — igual ao finish normal."""
    output_sku, wo_ref, total = backstage_production.apply_quick_finish(
        recipe_id=recipe.pk,
        quantity=Decimal("10"),
        position_id=None,
        actor="test",
        force=True,
    )

    assert output_sku == SKU
    assert wo_ref
    assert total == Decimal("10")
    assert OperatorAlert.objects.filter(type="production_stock_short").exists()
