"""Etapas estruturadas e nota de item: a forma única, o funil e o caminho até a ficha.

``Recipe.steps`` e ``RecipeVersion.steps`` são listas de objetos
``{name, instructions?, target_seconds?, note?}``; texto puro é atalho aceito.
Publicar copia a estrutura para a ficha, e a nota do item da fórmula chega ao
``RecipeItem.meta["note"]`` (antes morria no ato de publicar).
"""

import importlib
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from shopman.craftsman import craft
from shopman.craftsman.exceptions import RecipeBookError
from shopman.craftsman.models import Recipe, RecipeItem, RecipeVersion
from shopman.craftsman.recipe_steps import normalize_steps, steps_from_names
from shopman.craftsman.services import recipe_book

from .test_recipe_book import flour_formula

STRUCTURED = [
    {"name": "Autólise", "target_seconds": 2400},
    {"name": "Sova", "instructions": "Até o ponto de véu.", "note": "A masseira nova esquenta mais."},
    "Forno",
]


# ── O funil ──────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_plain_text_becomes_a_named_step(self):
        assert normalize_steps(["Mistura", "  Forno  "]) == [{"name": "Mistura"}, {"name": "Forno"}]

    def test_structured_step_keeps_its_fields_and_drops_the_empty_ones(self):
        steps = normalize_steps([
            {"name": " Sova ", "instructions": " Até o véu. ", "target_seconds": 600, "note": ""},
            {"name": "Forno", "instructions": "", "target_seconds": None},
        ])
        assert steps == [
            {"name": "Sova", "instructions": "Até o véu.", "target_seconds": 600},
            {"name": "Forno"},
        ]

    def test_none_and_tuple(self):
        assert normalize_steps(None) == []
        assert normalize_steps(("Mistura",)) == [{"name": "Mistura"}]

    @pytest.mark.parametrize("bad, fragment", [
        ([{"instructions": "sem nome"}], "nome"),
        ([{"name": "  "}], "nome"),
        ([{"name": "Sova", "minutes": 10}], "minutes"),
        ([{"name": "Sova", "target_seconds": 0}], "tempo alvo"),
        ([{"name": "Sova", "target_seconds": -5}], "tempo alvo"),
        ([{"name": "Sova", "target_seconds": "600"}], "tempo alvo"),
        ([{"name": "Sova", "target_seconds": 1.5}], "tempo alvo"),
        ([{"name": "Sova", "target_seconds": True}], "tempo alvo"),
        ([{"name": "Sova", "instructions": 42}], "instruções"),
        ([{"name": "Sova", "note": ["x"]}], "anotação"),
        ([42], "texto ou um objeto"),
    ])
    def test_invalid_step_is_refused_naming_the_step(self, bad, fragment):
        with pytest.raises(ValidationError) as exc:
            normalize_steps(["Mistura", *bad])
        message = " ".join(exc.value.message_dict["steps"])
        assert message.startswith("Etapa 2:")
        assert fragment in message

    def test_not_a_list_is_refused(self):
        with pytest.raises(ValidationError) as exc:
            normalize_steps({"name": "Sova"})
        assert "lista" in " ".join(exc.value.message_dict["steps"])


class TestStepsFromNames:
    def test_a_step_that_keeps_its_name_keeps_what_it_had(self):
        previous = normalize_steps(STRUCTURED)
        assert steps_from_names(["Pesagem", "Forno", "Sova", "", "Autólise"], previous) == [
            {"name": "Pesagem"},
            {"name": "Forno"},
            {"name": "Sova", "instructions": "Até o ponto de véu.", "note": "A masseira nova esquenta mais."},
            {"name": "Autólise", "target_seconds": 2400},
        ]

    def test_repeated_name_matches_the_next_unused_step(self):
        previous = [{"name": "Dobra", "target_seconds": 1800}, {"name": "Dobra", "target_seconds": 900}]
        assert steps_from_names(["Dobra", "Dobra", "Dobra"], previous) == [
            {"name": "Dobra", "target_seconds": 1800},
            {"name": "Dobra", "target_seconds": 900},
            {"name": "Dobra"},
        ]


# ── Nos modelos ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestModels:
    def test_recipe_save_stores_the_single_shape(self):
        recipe = Recipe.objects.create(ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("1"), steps=STRUCTURED)
        recipe.refresh_from_db()
        assert recipe.steps == [
            {"name": "Autólise", "target_seconds": 2400},
            {"name": "Sova", "instructions": "Até o ponto de véu.", "note": "A masseira nova esquenta mais."},
            {"name": "Forno"},
        ]

    def test_recipe_refuses_an_invalid_step(self):
        with pytest.raises(ValidationError) as exc:
            Recipe.objects.create(ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("1"),
                                  steps=[{"name": "Sova", "target_seconds": 0}])
        assert "Etapa 1" in " ".join(exc.value.message_dict["steps"])

    def test_version_save_normalizes_even_without_full_clean(self):
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        version = RecipeVersion.objects.create(entry=entry, number=1, formula=flour_formula(), steps=["Mistura", "Forno"])
        version.refresh_from_db()
        assert version.steps == [{"name": "Mistura"}, {"name": "Forno"}]

    def test_version_normalizes_and_refuses(self):
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        version = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg",
                                             steps=["Mistura"])
        assert version.steps == [{"name": "Mistura"}]
        with pytest.raises(ValidationError):
            recipe_book.update_draft(version, steps=[{"name": "Mistura", "temperatura": 24}])


# ── Publicar ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPublish:
    def test_publish_copies_the_structured_steps_to_the_sheet_and_the_batch_snapshot(self):
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        version = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg",
                                             steps=STRUCTURED)
        recipe = recipe_book.publish_version(version)
        recipe.refresh_from_db()
        assert recipe.steps == version.steps
        assert recipe.steps[1]["instructions"] == "Até o ponto de véu."
        work_order = craft.plan(recipe, 1)
        assert work_order.meta["_recipe_snapshot"]["production"]["steps"] == recipe.steps

    def test_the_item_note_reaches_the_sheet(self):
        formula = flour_formula()
        formula["items"][0]["note"] = "A farinha do bairro pede 2% mais água."
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        version = recipe_book.create_version(entry, formula=formula, yield_quantity="1.7", yield_unit="kg")

        recipe = recipe_book.publish_version(version)

        items = {item.input_sku: item for item in recipe.items.all()}
        assert items["FARINHA-ANACONDA-PREMIUM"].meta["note"] == "A farinha do bairro pede 2% mais água."
        assert "note" not in items["AGUA-FILTRADA"].meta

    def test_a_note_removed_from_the_formula_leaves_the_sheet(self):
        """Alérgeno da ficha sobrevive à publicação; a nota não, porque é da fórmula."""
        recipe = Recipe.objects.create(ref="massa", name="Massa", output_sku="MASSA", batch_size=Decimal("1"),
                                       meta={"output_unit": "kg"})
        RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA-ANACONDA-PREMIUM", quantity=Decimal("0.9"),
                                  unit="kg", meta={"allergens": ["gluten"], "note": "nota velha"})
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        version = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")

        published = recipe_book.publish_version(version)

        flour = published.items.get(input_sku="FARINHA-ANACONDA-PREMIUM")
        assert flour.meta == {"allergens": ["gluten"]}

    def test_two_lines_of_the_same_item_carry_both_notes(self):
        formula = flour_formula()
        formula["items"].append({"sku": "AGUA-FILTRADA", "name": "Água da bassinage", "role": "liquid",
                                 "quantity": 50, "unit": "g", "note": "Só no fim da sova."})
        formula["items"][1]["note"] = "Gelada."
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        # Rendimento baixo de propósito: a quantidade de SKU repetido na fórmula não é
        # o assunto aqui (a análise indexa a sobra por SKU); a nota é.
        version = recipe_book.create_version(entry, formula=formula, yield_quantity="1", yield_unit="kg")

        recipe = recipe_book.publish_version(version)

        water = recipe.items.get(input_sku="AGUA-FILTRADA")
        assert water.meta["note"] == "Gelada.; Só no fim da sova."

    def test_a_note_that_is_not_text_is_refused(self):
        formula = flour_formula()
        formula["items"][0]["note"] = 42
        entry = recipe_book.create_entry(ref="massa", name="Massa", kind="bread", output_sku="MASSA")
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.create_version(entry, formula=formula, yield_quantity="1.7", yield_unit="kg")
        assert exc.value.data["field"] == "items[0].note"


# ── A migração dos dados gravados ────────────────────────────────────────────


class TestMigration:
    migration = importlib.import_module("shopman.craftsman.migrations.0015_steps_as_objects")

    def test_text_becomes_a_named_step_and_blank_text_leaves(self):
        assert self.migration._as_objects(["Mistura", " ", " Forno "], label="x") == [
            {"name": "Mistura"},
            {"name": "Forno"},
        ]

    def test_an_object_is_left_as_is(self):
        assert self.migration._as_objects([{"name": "Sova", "target_seconds": 60}], label="x") == [
            {"name": "Sova", "target_seconds": 60},
        ]

    def test_something_else_stops_the_migration(self):
        with pytest.raises(ValueError, match="etapa 2"):
            self.migration._as_objects(["Mistura", 42], label="Recipe 7")

    def test_backwards_keeps_the_names(self):
        assert self.migration._as_names([{"name": "Sova", "note": "x"}, {"name": "Forno"}], label="x") == ["Sova", "Forno"]
