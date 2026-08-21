"""Tests for the ``apply_product_measurements`` management command.

O comando existe para levar uma correção de peso a um banco que já roda, onde
o `seed` seria destrutivo. O que ele promete, e que estes testes travam:

- sem ``--apply`` não grava nada;
- com ``--apply`` grava peso e metadata, e NÃO encosta em preço nem estoque;
- remonta o rótulo depois, porque a porção é rotulada pelo peso;
- SKU que não existe neste banco é avisado, não quebra;
- rodar duas vezes não faz nada na segunda.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product

from shopman.shop.management.commands.apply_product_measurements import MEASUREMENTS
from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe

pytestmark = pytest.mark.django_db


def _campagne(unit_weight_g: int = 500, **metadata) -> Product:
    """CGO como ele estava ANTES da correção: 500 g e a medida do pão grande."""
    return Product.objects.create(
        sku="CGO",
        name="Pain de Campagne",
        base_price_q=2200,
        unit_weight_g=unit_weight_g,
        metadata={
            "serves": "3 a 5 pessoas",
            "approx_dimensions": "aprox. 18 cm de diâmetro",
            **metadata,
        },
    )


def _ficha_do_campagne() -> Recipe:
    recipe = Recipe.objects.create(
        ref="campagne", name="Pain de Campagne", output_sku="CGO",
        batch_size=Decimal("10"), is_active=True,
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA-T65", quantity=Decimal("3.400"),
        meta={
            "label": "Farinha de trigo T65",
            "nutrition": {
                "energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3,
                "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2,
                "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2,
            },
        },
    )
    return recipe


def _rodar(*args) -> str:
    saida = StringIO()
    call_command("apply_product_measurements", *args, stdout=saida)
    return saida.getvalue()


def test_sem_apply_nao_grava_nada():
    produto = _campagne()
    saida = _rodar()

    produto.refresh_from_db()
    assert produto.unit_weight_g == 500
    assert produto.metadata["approx_dimensions"] == "aprox. 18 cm de diâmetro"
    assert "500 → 300 g" in saida
    assert "--apply" in saida


def test_com_apply_grava_peso_e_medida():
    produto = _campagne()
    _rodar("--apply")

    produto.refresh_from_db()
    assert produto.unit_weight_g == 300
    assert produto.metadata["serves"] == "2 a 3 pessoas"
    assert produto.metadata["approx_dimensions"] == "aprox. 15 cm de diâmetro x 10 cm de altura"


def test_nao_encosta_em_preco_nem_em_campo_de_metadata_alheio():
    produto = _campagne(allergens=["glúten"], dietary_info=["100% vegetal"])
    _rodar("--apply")

    produto.refresh_from_db()
    assert produto.base_price_q == 2200, "preço é do catálogo, não deste comando"
    assert produto.name == "Pain de Campagne"
    assert produto.metadata["allergens"] == ["glúten"]
    assert produto.metadata["dietary_info"] == ["100% vegetal"]


def test_remonta_o_rotulo_porque_a_porcao_e_rotulada_pelo_peso():
    produto = _campagne()
    _ficha_do_campagne()
    fill_nutrition_from_recipe(produto)
    produto.refresh_from_db()

    # 500 g e 300 g são ambos > 100 g, então a porção segue em 100 g. O que muda
    # é quantas porções a peça tem — o número que descrevia a peça errada.
    assert produto.nutrition_facts["serving_size_g"] == 100
    assert produto.nutrition_facts["servings_per_container"] == 5

    _rodar("--apply")

    produto.refresh_from_db()
    assert produto.nutrition_facts["auto_filled"] is True
    assert produto.nutrition_facts["servings_per_container"] == 3


def test_sku_fora_deste_banco_e_avisado_e_nao_quebra():
    _campagne()
    saida = _rodar("--apply")

    assert "fora do catálogo deste banco" in saida
    assert "CI" in saida
    assert Product.objects.get(sku="CGO").unit_weight_g == 300


def test_rodar_de_novo_nao_tem_o_que_fazer():
    _campagne()
    _rodar("--apply")
    saida = _rodar("--apply")

    assert "Nada a fazer" in saida


def test_um_sku_so_nao_mexe_nos_outros():
    _campagne()
    Product.objects.create(
        sku="CI", name="Ciabatta", base_price_q=1800, unit_weight_g=200, metadata={},
    )
    _rodar("--sku", "CI", "--apply")

    assert Product.objects.get(sku="CI").unit_weight_g == 180
    assert Product.objects.get(sku="CGO").unit_weight_g == 500, "CGO não era o alvo"


def test_a_tabela_cobre_o_que_o_pr_280_mudou():
    """Guarda de escopo: a tabela é a lista do que mudou, não um catálogo paralelo."""
    assert set(MEASUREMENTS) == {
        "CGO", "CPX", "CGR", "CF", "CI", "CT", "KP", "MD", "BH", "CN", "FOA", "CBT", "FOC",
    }
    for sku, valores in MEASUREMENTS.items():
        assert "unit_weight_g" in valores, sku
        assert set(valores) <= {"unit_weight_g", "serves", "approx_dimensions"}, sku
