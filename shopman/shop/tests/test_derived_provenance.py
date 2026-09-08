"""A relação derivada: nada do catálogo fica velho em silêncio.

Bloco C do WP-FICHA-DE-PRODUTO-E-PROMESSA. Cobre:

- derivar carimba a versão de origem;
- publicar versão nova marca o derivado como vencido e o recalcula;
- override manual NÃO é recalculado, mas É marcado vencido, com autor e data;
- ficha sem ``version_ref`` não inventa versão;
- carimbo anda mesmo quando os números não andam.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product

from shopman.shop.services.derived_provenance import (
    FACT_DIETARY,
    FACT_NUTRITION,
    SOURCE_MANUAL,
    SOURCE_RECIPE,
    ManualAuditWithoutActor,
    read_stamp,
    record_manual_audit,
    stamp_is_stale,
)
from shopman.shop.services.dietary_from_recipe import aggregate_dietary_from_recipe
from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe

pytestmark = pytest.mark.django_db


FLOUR_PROFILE = {
    "label": "Farinha de trigo",
    "diet": "vegan",
    "allergens": ["glúten"],
    "nutrition": {
        "energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3,
        "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2,
        "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2,
    },
}
WATER_PROFILE = {"label": "Água", "diet": "vegan", "allergens": [], "nutrition": {"energy_kcal": 0}}


def _product(sku: str = "PAO", **extra) -> Product:
    return Product.objects.create(
        sku=sku, name="Pão de Teste", base_price_q=500, unit_weight_g=50, **extra
    )


def _recipe(sku: str = "PAO", *, version_ref: str | None = "pao@1", batch_size="10") -> Recipe:
    meta = {} if version_ref is None else {"version_ref": version_ref}
    recipe = Recipe.objects.create(
        ref=f"{sku.lower()}-v1", name=f"Receita {sku}", output_sku=sku,
        batch_size=Decimal(batch_size), is_active=True, meta=meta,
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA", quantity=Decimal("1.000"), meta=dict(FLOUR_PROFILE),
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="AGUA", quantity=Decimal("0.650"), meta=dict(WATER_PROFILE),
    )
    return recipe


class TestStampOnDerivation:
    def test_nutrition_derivation_stamps_the_source_version(self):
        product = _product()
        _recipe()

        assert fill_nutrition_from_recipe(product) is True
        product.refresh_from_db()

        stamp = read_stamp(product, FACT_NUTRITION)
        assert stamp["source"] == SOURCE_RECIPE
        assert stamp["version_ref"] == "pao@1"
        assert stamp["recipe_ref"] == "pao-v1"
        assert stamp["at"]

    def test_dietary_derivation_stamps_the_source_version(self):
        product = _product()
        _recipe()

        assert aggregate_dietary_from_recipe(product) is True
        product.refresh_from_db()

        stamp = read_stamp(product, FACT_DIETARY)
        assert stamp["source"] == SOURCE_RECIPE
        assert stamp["version_ref"] == "pao@1"

    def test_a_recipe_never_published_stamps_no_invented_version(self):
        product = _product()
        _recipe(version_ref=None)

        fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        stamp = read_stamp(product, FACT_NUTRITION)
        # Derivou de verdade (há carimbo), mas a versão é vazia — nada de "@1"
        # inventado para uma ficha que nunca passou pelo inventário.
        assert stamp is not None
        assert stamp["version_ref"] == ""
        assert "@" not in stamp["version_ref"]


class TestStale:
    def test_publishing_a_new_version_makes_the_derived_fact_stale(self):
        product = _product()
        recipe = _recipe()
        fill_nutrition_from_recipe(product)
        product.refresh_from_db()

        recipe.meta = {**recipe.meta, "version_ref": "pao@2"}
        recipe.save(update_fields=["meta"])

        # O carimbo antigo (lido antes de qualquer recálculo) está vencido.
        assert stamp_is_stale({"version_ref": "pao@1"}, "pao@2") is True

    def test_the_new_version_recalculates_and_moves_the_stamp(self):
        product = _product()
        recipe = _recipe()
        fill_nutrition_from_recipe(product)

        recipe.meta = {**recipe.meta, "version_ref": "pao@2"}
        recipe.items.filter(input_sku="FARINHA").update(quantity=Decimal("2.000"))
        recipe.save()  # o signal derruba a derivação inteira

        product.refresh_from_db()
        stamp = read_stamp(product, FACT_NUTRITION)
        assert stamp["version_ref"] == "pao@2"
        assert stamp_is_stale(stamp, "pao@2") is False
        # E o número acompanhou: o dobro de farinha por peça.
        assert product.nutrition_facts["energy_kcal"] > 500

    def test_the_stamp_moves_even_when_the_numbers_do_not(self):
        """Versão nova com os mesmos nutrientes ainda move a origem.

        Se o carimbo ficasse parado, o fato ficaria vencido para sempre — a
        derivação rodaria, não mudaria nada e nunca reconheceria a versão nova.
        """
        product = _product()
        recipe = _recipe()
        fill_nutrition_from_recipe(product)

        recipe.meta = {**recipe.meta, "version_ref": "pao@2"}
        recipe.save()

        product.refresh_from_db()
        assert read_stamp(product, FACT_NUTRITION)["version_ref"] == "pao@2"

    def test_an_unversioned_recipe_never_reads_as_stale(self):
        """Vazio contra vazio não vence — e a leitura avisa que não dá para saber."""
        assert stamp_is_stale({"version_ref": ""}, "") is False

    def test_without_a_stamp_there_is_nothing_to_compare(self):
        assert stamp_is_stale(None, "pao@3") is False


class TestManualOverrideIsSacredButAgeable:
    def test_manual_nutrition_is_not_recalculated(self):
        product = _product(nutrition_facts={"energy_kcal": 111, "serving_size_g": 50, "auto_filled": False})
        _recipe()

        assert fill_nutrition_from_recipe(product) is False
        product.refresh_from_db()
        assert product.nutrition_facts["energy_kcal"] == 111

    def test_manual_nutrition_can_be_signed_and_then_goes_stale(self):
        product = _product(nutrition_facts={"energy_kcal": 111, "serving_size_g": 50, "auto_filled": False})
        recipe = _recipe()

        record_manual_audit(product, FACT_NUTRITION, actor="pablo")
        product.refresh_from_db()
        stamp = read_stamp(product, FACT_NUTRITION)
        assert stamp["source"] == SOURCE_MANUAL
        assert stamp["by"] == "pablo"
        assert stamp["at"]
        assert stamp["version_ref"] == "pao@1"
        assert stamp_is_stale(stamp, "pao@1") is False

        recipe.meta = {**recipe.meta, "version_ref": "pao@2"}
        recipe.save()

        product.refresh_from_db()
        stamp = read_stamp(product, FACT_NUTRITION)
        # Vencido, e mesmo assim intocado: autor, data e valor continuam ali.
        assert stamp_is_stale(stamp, "pao@2") is True
        assert stamp["source"] == SOURCE_MANUAL
        assert stamp["by"] == "pablo"
        assert product.nutrition_facts["energy_kcal"] == 111

    def test_a_manual_audit_without_a_signer_is_refused(self):
        product = _product()
        _recipe()
        with pytest.raises(ManualAuditWithoutActor):
            record_manual_audit(product, FACT_NUTRITION, actor="   ")

    def test_a_manual_audit_on_a_product_without_recipe_stamps_no_version(self):
        product = _product(sku="AGUA-MINERAL")
        record_manual_audit(product, FACT_NUTRITION, actor="pablo")
        product.refresh_from_db()
        stamp = read_stamp(product, FACT_NUTRITION)
        assert stamp["version_ref"] == ""
        assert stamp["recipe_ref"] == ""
        assert stamp["by"] == "pablo"
