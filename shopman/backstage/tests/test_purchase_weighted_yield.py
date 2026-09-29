"""O FC explica a compra sem cobrar duas vezes a perda já debitada no ledger."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem

from shopman.backstage.projections.purchase import (
    _material_projection,
    _weighted_usable_factor_map,
)
from shopman.shop.services.sku_records import SkuRoles

pytestmark = pytest.mark.django_db


def _consumption(recipe: Recipe, *, ref: str, gross: str, factor: str) -> None:
    work_order = WorkOrder.objects.create(
        ref=ref,
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal("1"),
        status=WorkOrder.Status.FINISHED,
    )
    gross_quantity = Decimal(gross)
    WorkOrderItem.objects.create(
        work_order=work_order,
        kind=WorkOrderItem.Kind.CONSUMPTION,
        item_ref="CEBOLA",
        quantity=gross_quantity,
        unit="kg",
        recorded_at=timezone.now(),
        meta={
            "net_quantity": str(gross_quantity * Decimal(factor)),
            "usable_factor": factor,
            "approximate": True,
        },
    )


def test_rendimentos_sao_ponderados_pelo_consumo_das_fichas():
    recipes = [
        Recipe.objects.create(
            ref=f"cebola-{index}",
            name=f"Cebola {index}",
            output_sku=f"PREPARO-{index}",
            batch_size=Decimal("1"),
        )
        for index in range(3)
    ]
    for index, (recipe, factor) in enumerate(
        zip(recipes, ("0.72", "0.84", "0.93"), strict=True)
    ):
        _consumption(recipe, ref=f"WO-{index}", gross="10", factor=factor)

    factors = _weighted_usable_factor_map(
        ["CEBOLA"],
        gross_daily_use={"CEBOLA": Decimal("30") / Decimal("14")},
        days=14,
    )

    # Soma 7,2 + 8,4 + 9,3 sobre 30 brutos = 83%; inverte-se só depois.
    assert factors["CEBOLA"] == Decimal("0.83")
    assert Decimal("1") / factors["CEBOLA"] == pytest.approx(Decimal("1.204819"))


def test_baixa_sem_ficha_nao_ganha_perda_inventada():
    recipe = Recipe.objects.create(
        ref="cebola-petala",
        name="Cebola em pétala",
        output_sku="CEBOLA-PETALA",
        batch_size=Decimal("1"),
    )
    _consumption(recipe, ref="WO-PETALA", gross="10", factor="0.80")

    factors = _weighted_usable_factor_map(
        ["CEBOLA"],
        # 10 brutos da ficha + 10 de outras baixas, tratadas com rendimento 1.
        gross_daily_use={"CEBOLA": Decimal("20") / Decimal("14")},
        days=14,
    )

    assert factors["CEBOLA"] == Decimal("0.90")


def test_sugestao_bruta_nao_multiplica_novamente_o_fc():
    material = Material.objects.create(sku="CEBOLA", name="Cebola", unit="kg")

    projected = _material_projection(
        material,
        stock_on_hand=Decimal("0"),
        daily_use=Decimal("10"),  # o ledger já debitou a quantidade BRUTA
        weighted_usable_factor=Decimal("0.84"),
        recipes=("Cebola em pétala",),
        lead_time_days=Decimal("1"),
        stock_is_approximate=False,
        policy={"review_period_days": 0, "safety_days": 0},
        roles=SkuRoles(purchasable=True, used_in_recipe=True),
        sale_price_q=None,
    )

    assert projected.suggestedQty == 10  # não 11,905: gross_quantity não duplica
    assert projected.suggestedNetQty == 8.4
    assert projected.weightedUsableFactor == 0.84
    assert projected.correctionFactor == 1.19
