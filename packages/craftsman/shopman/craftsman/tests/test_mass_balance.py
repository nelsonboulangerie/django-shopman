"""Misturar massa não cria matéria — o invariante de massa da ficha técnica.

Duas fichas do catálogo semeado rendiam MAIS do que pesavam: massa de brioche,
10 kg saídos de 8,04 kg de ingredientes (+24,4%); massa de pães macios, 10 de
8,36 (+19,6%); e a folhada, 10 de 9,456 (+5,8%). Não era erro cosmético: o
``CraftExecution.finish`` escala o BOM por ``quantity / batch_size`` e o handler
do ledger usa o MESMO coeficiente, então o sistema debitava ~20% menos insumo do
que o padeiro usava, todo dia, e a sugestão de compra nascia curta na mesma
proporção.

A suíte tinha testes de ficha (unidade, SKU de saída, rendimento positivo) e
nenhum perguntava se a conta FECHA.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from shopman.craftsman.models import Recipe, RecipeItem

pytestmark = pytest.mark.django_db


def _dough(batch_size: str, *, ref: str = "massa-teste") -> Recipe:
    """Ficha de massa: saída em kg declarada no meta (não existe no catálogo)."""
    return Recipe.objects.create(
        ref=ref,
        name="Massa de teste",
        output_sku=f"MASSA-{ref.upper()}",
        batch_size=Decimal(batch_size),
        meta={"output_unit": "kg"},
    )


def _flour_and_water(recipe: Recipe) -> None:
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA", quantity=Decimal("5.000"), unit="kg"
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="AGUA",
        quantity=Decimal("3.000"),
        unit="L",
        meta={"density_g_per_ml": 1.0},
    )


def test_yield_above_the_sum_of_the_ingredients_is_refused():
    recipe = _dough("8")
    _flour_and_water(recipe)  # 8,000 kg de insumo

    recipe.batch_size = Decimal("10")
    with pytest.raises(ValidationError) as exc:
        recipe.save()
    assert "batch_size" in exc.value.message_dict


def test_mixing_loss_passes():
    """Perda é esperada: masseira e forno tiram água e deixam massa na bacia."""
    recipe = _dough("8")
    _flour_and_water(recipe)

    recipe.batch_size = Decimal("7.6")  # 5% de perda
    recipe.save()
    recipe.refresh_from_db()
    assert recipe.batch_size == Decimal("7.600")


def test_volume_travels_by_the_declared_density():
    """Litro só vira quilo com densidade declarada — ADR-024, sem adivinhar."""
    recipe = _dough("8", ref="massa-azeite")
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA", quantity=Decimal("5.000"), unit="kg"
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="AZEITE",
        quantity=Decimal("3.000"),
        unit="L",
        meta={"density_g_per_ml": 0.91},
    )  # 5,000 + 2,730 = 7,730 kg

    recipe.batch_size = Decimal("7.9")
    with pytest.raises(ValidationError):
        recipe.save()

    recipe.batch_size = Decimal("7.5")
    recipe.save()


def test_a_sheet_it_cannot_compare_is_left_alone():
    """Sem densidade, o litro não vira quilo — e o invariante se cala."""
    recipe = _dough("8", ref="massa-sem-densidade")
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA", quantity=Decimal("1.000"), unit="kg"
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="AGUA", quantity=Decimal("3.000"), unit="L"
    )

    recipe.batch_size = Decimal("50")
    recipe.save()  # não opina: adivinhar seria pior que calar


def test_a_sheet_that_yields_pieces_is_not_a_mass_balance():
    """Croissant: 48 unidades de 8,5 kg de massa. 48 > 8,5 e está tudo certo."""
    recipe = Recipe.objects.create(
        ref="croissant-teste",
        name="Croissant",
        output_sku="CT-TESTE",
        batch_size=Decimal("48"),
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="MASSA-FOLHADA", quantity=Decimal("8.500"), unit="kg"
    )

    recipe.batch_size = Decimal("48")
    recipe.save()


def test_a_brand_new_sheet_is_not_refused_for_having_no_items_yet():
    """No ``create`` os itens ainda não existem: somar zero reprovaria tudo."""
    _dough("10", ref="massa-nova")
