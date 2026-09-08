"""Tests for shopman.shop.services.dietary_from_recipe (WP-7).

Covers:
- Allergen union + diet resolution from the BOM (vegan/vegetarian/animal).
- Free-from claims ("sem glúten" / "sem lactose") only when no insumo triggers.
- valor com ``source="manual"`` bloqueia a sobrescrita pela ficha.
- Bundles are skipped.
- Incomplete insumo data (no diet declared) is a safe no-op.
- Multilevel BOM (sub-recipe) is expanded and unioned.
- The Recipe ``post_save`` signal materializes onto the Product.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.dietary import IngredientDietary
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product, ProductComponent

from shopman.shop.services import attributes
from shopman.shop.services.dietary_from_recipe import aggregate_dietary_from_recipe

pytestmark = pytest.mark.django_db


def _make_product(sku: str = "PAO", **extra) -> Product:
    return Product.objects.create(
        sku=sku, name="Pão de Teste", base_price_q=500, **extra,
    )


def _recipe(sku: str = "PAO", batch_size: Decimal = Decimal("10")) -> Recipe:
    return Recipe.objects.create(
        ref=f"{sku.lower()}-v1",
        name=f"Receita {sku}",
        output_sku=sku,
        batch_size=batch_size,
        is_active=True,
    )


def _item(recipe: Recipe, input_sku: str, *, allergens=None, diet=None, qty="1.000", declare=True):
    meta: dict = {"label": input_sku}
    if declare:
        meta.update(IngredientDietary(allergens=tuple(allergens or ()), diet=diet or "vegan").to_meta())
    return RecipeItem.objects.create(
        recipe=recipe, input_sku=input_sku, quantity=Decimal(qty), meta=meta,
    )


# ── IngredientDietary dataclass ────────────────────────────────────────


class TestIngredientDietary:
    def test_undeclared_meta_returns_none(self):
        assert IngredientDietary.from_meta({"label": "Farinha"}) is None
        assert IngredientDietary.from_meta(None) is None
        assert IngredientDietary.from_meta({}) is None

    def test_parses_declared_meta(self):
        profile = IngredientDietary.from_meta(
            {"allergens": ["glúten", ""], "diet": "vegan"}
        )
        assert profile == IngredientDietary(allergens=("glúten",), diet="vegan")

    def test_unknown_diet_falls_back_to_vegan(self):
        profile = IngredientDietary.from_meta({"diet": "nonsense"})
        assert profile.diet == "vegan"

    def test_roundtrips_through_meta(self):
        profile = IngredientDietary(allergens=("leite",), diet="vegetarian")
        assert IngredientDietary.from_meta(profile.to_meta()) == profile


# ── Aggregation service ────────────────────────────────────────────────


class TestAggregateDietaryFromRecipe:
    def test_all_vegan_with_gluten(self):
        product = _make_product()
        recipe = _recipe()
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="5")
        _item(recipe, "INS-AGUA", allergens=[], diet="vegan", qty="3")

        changed = aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert changed is True
        assert attributes.get(product, "alergenos") == ["glúten"]
        # gluten present → no "sem glúten"; vegan + no lactose → vegetal + sem lactose
        # Só "100% vegetal": lactose e glúten são lidos dos ALÉRGENOS.
        assert attributes.get(product, "dieta") == ["100% vegetal"]
        assert attributes.source(product, "alergenos") == "recipe"

    def test_gluten_free_vegan_gets_sem_gluten(self):
        product = _make_product(sku="POLVILHO")
        recipe = _recipe(sku="POLVILHO")
        _item(recipe, "INS-POLVILHO", allergens=[], diet="vegan")

        aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        # A casa NÃO afirma "sem glúten" — farinha no ar, forno compartilhado.
        assert attributes.get(product, "dieta") == ["100% vegetal"]

    def test_vegetarian_insumo_blocks_vegan_and_lactose_claim(self):
        product = _make_product(sku="BRIOCHE")
        recipe = _recipe(sku="BRIOCHE")
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="4")
        _item(recipe, "INS-LEITE", allergens=["leite"], diet="vegetarian", qty="2")
        _item(recipe, "INS-OVOS", allergens=["ovos"], diet="vegetarian", qty="1")

        aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert attributes.get(product, "alergenos") == ["glúten", "leite", "ovos"]
        # "vegetariano" saiu: leite e ovos já dizem isso, nos alérgenos.
        assert attributes.get(product, "dieta") == []

    def test_animal_insumo_blocks_positive_diet_claim(self):
        product = _make_product(sku="FOCACCIA-BACON")
        recipe = _recipe(sku="FOCACCIA-BACON")
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="5")
        _item(recipe, "INS-BACON", allergens=[], diet="animal", qty="1")

        aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        # no positive diet claim; gluten present → no sem glúten; no lactose → sem lactose
        # Insumo animal derruba a única afirmação que sobrou.
        assert attributes.get(product, "dieta") == []

    def test_allergen_union_dedups(self):
        product = _make_product(sku="MISTO")
        recipe = _recipe(sku="MISTO")
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="5")
        _item(recipe, "INS-MALTE", allergens=["glúten"], diet="vegan", qty="1")
        _item(recipe, "INS-GERGELIM", allergens=["gergelim"], diet="vegan", qty="1")

        aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert attributes.get(product, "alergenos") == ["glúten", "gergelim"]

    def test_manual_override_blocks(self):
        product = _make_product()
        # Valor escrito pelo gestor: é a proveniência que bloqueia a ficha agora.
        attributes.set(product, "alergenos", ["leite"], source="manual")
        recipe = _recipe()
        _item(recipe, "INS-LEITE", allergens=["leite"], diet="vegetarian")

        changed = aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert changed is False
        assert attributes.get(product, "alergenos") == ["leite"]

    def test_bundle_is_skipped(self):
        child = _make_product(sku="PAO-SIMPLES")
        product = _make_product(sku="COMBO")
        ProductComponent.objects.create(parent=product, component=child, qty=Decimal("1"))

        assert aggregate_dietary_from_recipe(product) is False

    def test_incomplete_data_is_noop(self):
        product = _make_product(sku="PARCIAL")
        recipe = _recipe(sku="PARCIAL")
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan")
        _item(recipe, "INS-MISTERIO", declare=False)

        changed = aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert changed is False
        assert attributes.get(product, "alergenos") is None

    def test_no_recipe_is_noop(self):
        product = _make_product(sku="REVENDIDO")
        assert aggregate_dietary_from_recipe(product) is False

    def test_idempotent(self):
        product = _make_product()
        recipe = _recipe()
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan")

        assert aggregate_dietary_from_recipe(product) is True
        product.refresh_from_db()
        assert aggregate_dietary_from_recipe(product) is False

    def test_multilevel_bom_union(self):
        # Sub-recipe MASSA carries lactose; parent uses it → product is vegetarian.
        massa = _recipe(sku="MASSA", batch_size=Decimal("10"))
        _item(massa, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="5")
        _item(massa, "INS-LEITE", allergens=["leite"], diet="vegetarian", qty="2")

        product = _make_product(sku="PAO-FORMA")
        parent = _recipe(sku="PAO-FORMA", batch_size=Decimal("6"))
        _item(parent, "MASSA", allergens=[], diet="vegan", qty="6")

        aggregate_dietary_from_recipe(product)
        product.refresh_from_db()

        assert attributes.get(product, "alergenos") == ["glúten", "leite"]
        # Leite na cadeia derruba "100% vegetal", e é só isso que dieta diz.
        assert attributes.get(product, "dieta") == []

    def test_signal_materializes_on_recipe_save(self):
        product = _make_product(sku="BAGUETE")
        recipe = _recipe(sku="BAGUETE")
        _item(recipe, "INS-FARINHA", allergens=["glúten"], diet="vegan", qty="5")
        _item(recipe, "INS-AGUA", allergens=[], diet="vegan", qty="3")

        recipe.save()  # fires post_save → derivation signal
        product.refresh_from_db()

        assert attributes.source(product, "alergenos") == "recipe"
        assert attributes.get(product, "alergenos") == ["glúten"]
        assert "100% vegetal" in attributes.get(product, "dieta")


class TestAlergenoQueVemDoInsumo:
    """A cadeia insumo → ficha → rótulo não pode ser barrada por vocabulário.

    O caso é real desta casa: **pimenta preta**. A ANVISA não a lista como
    alergênico, a casa a usa, e já houve reação. Se o insumo sabe, o rótulo
    precisa saber — e nenhuma lista canônica pode cortar isso no meio.
    """

    def test_alergeno_fora_da_lista_chega_ao_rotulo(self):
        product = _make_product()
        recipe = _recipe()
        _item(recipe, "INS-PIMENTA", allergens=["pimenta preta"], diet="vegan")

        assert aggregate_dietary_from_recipe(product) is True
        assert "pimenta preta" in attributes.get(product, "alergenos")

    def test_a_opcao_nova_entra_marcada_para_revisao(self):
        """Opção que a ficha trouxe não pode entrar parecendo curadoria."""
        from shopman.shop.models import AttributeDefinition

        product = _make_product()
        recipe = _recipe()
        _item(recipe, "INS-PIMENTA", allergens=["pimenta preta"], diet="vegan")
        aggregate_dietary_from_recipe(product)

        d = AttributeDefinition.objects.get(ref="alergenos")
        nova = next(o for o in d.options if o["value"] == "pimenta preta")
        assert nova.get("meta", {}).get("from_recipe") is True

    def test_a_mao_o_erro_de_digitacao_continua_recusado(self):
        """Ampliar é privilégio da FICHA. No Admin, "glutén" é typo, não alérgeno novo."""
        from shopman.shop.services.attributes import AttributeError_

        product = _make_product()
        with pytest.raises(AttributeError_, match="glutén"):
            attributes.set(product, "alergenos", ["glutén"], source="manual")

    def test_dieta_nao_amplia_sozinha(self):
        """`dieta` é vocabulário da CASA, não da cadeia: fecha de propósito."""
        from shopman.shop.services.attributes import AttributeError_

        product = _make_product()
        with pytest.raises(AttributeError_):
            attributes.set(product, "dieta", ["low carb"], source="recipe")
