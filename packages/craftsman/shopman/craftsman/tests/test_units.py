"""A unidade da ficha normaliza pela física compartilhada (UNIT-CONVERSION-PLAN, Fase 1).

O Craftsman tinha a própria tabela de apelidos. Agora ela é uma só, em
``shopman.utils.units``; aqui sobra a grafia do litro (``"L"``, o valor da
choice) e a recusa, que continua sendo da ficha.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.models.recipe import normalize_recipe_item_unit


class TestNormalizeRecipeItemUnit:
    def test_liter_keeps_the_sheet_spelling(self):
        # A física fala "l"; a ficha guarda "L" desde sempre.
        assert normalize_recipe_item_unit("l") == "L"
        assert normalize_recipe_item_unit("L") == "L"

    def test_aliases_come_from_the_shared_table(self):
        assert normalize_recipe_item_unit("un.") == "un"
        assert normalize_recipe_item_unit("litros") == "L"
        assert normalize_recipe_item_unit("liters") == "L"

    def test_case_no_longer_invents_a_unit(self):
        assert normalize_recipe_item_unit("KG") == "kg"

    def test_unknown_comes_back_untouched(self):
        assert normalize_recipe_item_unit("saco") == "saco"
        assert normalize_recipe_item_unit("") == ""
        assert normalize_recipe_item_unit(None) == ""


@pytest.mark.django_db
class TestRecipeItemUnitValidation:
    @pytest.fixture
    def recipe(self):
        return Recipe.objects.create(
            ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("10"),
        )

    def test_clean_rewrites_the_alias_to_the_sheet_spelling(self, recipe):
        item = RecipeItem(recipe=recipe, input_sku="AGUA", quantity=Decimal("3"), unit="litros")
        item.clean()
        assert item.unit == "L"

    def test_clean_accepts_the_base_unit_spelling_of_the_material(self, recipe):
        # A unidade-base do Material é "l" (minúscula); a ficha guarda "L".
        # É esta linha que faz as duas se reconhecerem.
        item = RecipeItem(recipe=recipe, input_sku="LEITE", quantity=Decimal("1"), unit="l")
        item.clean()
        assert item.unit == "L"

    def test_unit_outside_the_sheet_vocabulary_is_refused(self, recipe):
        # "dz" é física conhecida, mas não é unidade de ficha técnica: recusa.
        item = RecipeItem(recipe=recipe, input_sku="OVOS", quantity=Decimal("2"), unit="dz")
        with pytest.raises(ValidationError) as exc:
            item.full_clean()
        assert "unit" in exc.value.message_dict

    def test_unknown_unit_is_refused(self, recipe):
        item = RecipeItem(recipe=recipe, input_sku="FARINHA", quantity=Decimal("1"), unit="saco")
        with pytest.raises(ValidationError) as exc:
            item.full_clean()
        assert "unit" in exc.value.message_dict
