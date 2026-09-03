"""Inventário de receitas: entry, versão, publicação na ficha, bootstrap e diff.

Publicar é o único verbo que escreve na ``Recipe``; o bootstrap lê a ficha e
não a toca. As fixtures são fisicamente honestas: a ficha roda o invariante
de massa no ``save`` e o rendimento nunca passa da soma dos insumos.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from shopman.craftsman import craft
from shopman.craftsman.exceptions import RecipeBookError
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeItem, RecipeVersion
from shopman.craftsman.services import recipe_book

pytestmark = pytest.mark.django_db


def flour_formula(*, water=700, parts=None, flour_sku="FARINHA-T55"):
    return {
        "anchor": {"kind": "flour"},
        "basis_g": 1000,
        "standardized": True,
        "items": [
            {"sku": flour_sku, "name": "Farinha T55", "role": "flour", "quantity": 1000, "unit": "g"},
            {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": water, "unit": "g"},
            {"sku": "SAL", "name": "Sal", "role": "salt", "quantity": 20, "unit": "g"},
        ],
        "parts": parts or [],
    }


LEVAIN_FORMULA = {
    "anchor": {"kind": "flour"},
    "items": [
        {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 500, "unit": "g"},
        {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 500, "unit": "g"},
    ],
    "parts": [],
}


@pytest.fixture
def entry():
    return recipe_book.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO")


@pytest.fixture
def draft(entry):
    return recipe_book.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg",
                                      steps=["Mistura", "Fermentação", "Forno"])


@pytest.fixture
def published_levain():
    levain = recipe_book.create_entry(ref="creme-levain", name="Levain", kind="bread", output_sku="LEVAIN")
    version = recipe_book.create_version(levain, formula=LEVAIN_FORMULA, yield_quantity=1000, yield_unit="g")
    recipe_book.publish_version(version)
    return levain


# ── Entry e versão ───────────────────────────────────────────────────────────


class TestCreate:
    def test_entry_and_first_draft(self, entry, draft):
        assert entry.ref == "massa-tradicao"
        assert entry.current_version is None
        assert draft.number == 1
        assert draft.status == RecipeVersion.Status.DRAFT
        assert draft.yield_quantity == Decimal("1.700")
        assert draft.yield_unit == "kg"
        assert draft.source == {"kind": "manual"}
        assert draft.origin["items"][0] == {"sku": "FARINHA-T55", "name": "Farinha T55", "quantity": "1000", "unit": "g"}
        assert draft.version_ref == "massa-tradicao@1"

    def test_numbers_grow_per_entry(self, entry, draft):
        second = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=1, yield_unit="kg")
        assert second.number == 2

    def test_invalid_formula_names_the_field(self, entry):
        formula = flour_formula()
        formula["items"][1]["quantity"] = -1
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.create_version(entry, formula=formula, yield_quantity=1, yield_unit="kg")
        assert exc.value.code == "FORMULA_INVALID"
        assert exc.value.data["field"] == "items[1].quantity"

    def test_the_model_refuses_the_same_formula(self, entry):
        version = RecipeVersion(entry=entry, number=1, yield_quantity=1, yield_unit="kg", formula={"items": []})
        with pytest.raises(ValidationError) as exc:
            version.full_clean()
        assert "anchor" in exc.value.message_dict["formula"][0]

    def test_yield_unit_follows_the_sheet_spelling(self, entry):
        version = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=1, yield_unit="litros")
        assert version.yield_unit == "L"
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=1, yield_unit="dz")
        assert exc.value.data["field"] == "yield_unit"

    def test_archived_entry_takes_no_version(self, entry):
        entry.is_archived = True
        entry.save()
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=1, yield_unit="kg")
        assert exc.value.code == "ENTRY_ARCHIVED"

    def test_update_draft_only_touches_drafts(self, draft):
        recipe_book.update_draft(draft, formula=flour_formula(water=750), label="mais água", notes="teste")
        draft.refresh_from_db()
        assert draft.formula["items"][1]["quantity"] == 750
        assert draft.label == "mais água"

        recipe_book.publish_version(draft)
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.update_draft(draft, notes="tarde demais")
        assert exc.value.code == "VERSION_NOT_DRAFT"


# ── Publicar ─────────────────────────────────────────────────────────────────


class TestPublish:
    def test_publish_writes_the_execution_sheet(self, entry, draft):
        recipe = recipe_book.publish_version(draft, actor="pablo")

        assert recipe.ref == "massa-tradicao"
        assert recipe.output_sku == "MASSA-TRADICAO"
        assert recipe.batch_size == Decimal("1.700")
        assert recipe.steps == ["Mistura", "Fermentação", "Forno"]
        assert recipe.is_active is True
        assert recipe.meta["version_ref"] == "massa-tradicao@1"
        assert recipe.meta["output_unit"] == "kg"
        items = {item.input_sku: item for item in recipe.items.order_by("sort_order")}
        assert set(items) == {"FARINHA-T55", "AGUA-FILTRADA", "SAL"}
        assert items["FARINHA-T55"].quantity == Decimal("1000")
        assert items["FARINHA-T55"].unit == "g"

        draft.refresh_from_db()
        entry.refresh_from_db()
        assert draft.status == RecipeVersion.Status.PUBLISHED
        assert draft.published_at is not None
        assert draft.meta["published_by"] == "pablo"
        assert entry.current_version == draft

    def test_publish_updates_the_sheet_in_place_and_keeps_item_meta(self, entry, draft):
        """A ficha é uma só por SKU e estável (mesmo ref); alérgenos moram no RecipeItem.meta."""
        recipe = Recipe.objects.create(ref="massa-tradicao", name="Nome antigo", output_sku="MASSA-TRADICAO",
                                       batch_size=Decimal("1"), meta={"output_unit": "kg", "prep_time_min": 30})
        RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA-T55", quantity=Decimal("0.9"), unit="kg",
                                  meta={"allergens": ["gluten"], "density_g_per_ml": 0.6})
        RecipeItem.objects.create(recipe=recipe, input_sku="MALTE", quantity=Decimal("0.02"), unit="kg")

        published = recipe_book.publish_version(draft)

        assert published.pk == recipe.pk
        assert published.name == "Massa Tradição"
        assert published.meta == {"output_unit": "kg", "prep_time_min": 30, "version_ref": "massa-tradicao@1"}
        items = {item.input_sku: item for item in published.items.all()}
        assert set(items) == {"FARINHA-T55", "AGUA-FILTRADA", "SAL"}
        assert items["FARINHA-T55"].meta == {"allergens": ["gluten"], "density_g_per_ml": 0.6}
        assert items["FARINHA-T55"].quantity == Decimal("1000")
        assert Recipe.objects.count() == 1

    def test_publish_deactivates_another_sheet_for_the_same_sku(self, entry, draft):
        other = Recipe.objects.create(ref="massa-tradicao-antiga", name="Antiga", output_sku="MASSA-TRADICAO",
                                      batch_size=Decimal("1"), meta={"output_unit": "kg"})
        recipe_book.publish_version(draft)
        other.refresh_from_db()
        assert other.is_active is False
        assert Recipe.objects.get(ref="massa-tradicao").is_active is True

    def test_publishing_a_second_version_supersedes_the_first(self, entry, draft):
        recipe_book.publish_version(draft)
        second = recipe_book.create_version(entry, formula=flour_formula(water=750), yield_quantity="1.7",
                                            yield_unit="kg", label="75% de hidratação")
        recipe = recipe_book.publish_version(second)

        draft.refresh_from_db()
        entry.refresh_from_db()
        assert draft.status == RecipeVersion.Status.SUPERSEDED
        assert second.status == RecipeVersion.Status.PUBLISHED
        assert entry.current_version == second
        assert recipe.meta["version_ref"] == "massa-tradicao@2"
        assert recipe.items.get(input_sku="AGUA-FILTRADA").quantity == Decimal("750")

    def test_publish_with_parts_consumes_the_parts_not_their_flour(self, entry, published_levain):
        """A defesa contra a dupla contagem: LEVAIN entra pronto e a farinha dele sai da base."""
        draft = recipe_book.create_version(
            entry,
            formula=flour_formula(parts=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20}]),
            yield_quantity="1.7", yield_unit="kg",
        )
        recipe = recipe_book.publish_version(draft)
        items = {item.input_sku: item.quantity for item in recipe.items.all()}
        assert items == {
            "FARINHA-T55": Decimal("800"),
            "AGUA-FILTRADA": Decimal("500"),
            "SAL": Decimal("20"),
            "LEVAIN": Decimal("400"),
        }

    def test_old_dough_becomes_an_optional_line_with_the_cap(self, entry):
        draft = recipe_book.create_version(
            entry, formula=flour_formula(parts=[{"kind": "old_dough", "cap_pct": 20}]),
            yield_quantity="1.7", yield_unit="kg",
        )
        recipe = recipe_book.publish_version(draft)
        old_dough = recipe.items.get(input_sku="MASSA-TRADICAO")
        assert old_dough.is_optional is True
        assert old_dough.meta == {"role": "old_dough", "cap_pct": "20"}
        assert old_dough.unit == "kg"
        assert old_dough.quantity == Decimal("0.344")
        # Fora do consumo: o BOM escalado da fornada não vê a massa velha.
        assert {i.input_sku for i in recipe.items.filter(is_optional=False)} == {"FARINHA-T55", "AGUA-FILTRADA", "SAL"}

    def test_refuses_entry_without_sku(self):
        knowledge = recipe_book.create_entry(ref="ideia-de-pao", name="Ideia de pão")
        draft = recipe_book.create_version(knowledge, formula=flour_formula(), yield_quantity=1, yield_unit="kg")
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.publish_version(draft)
        assert exc.value.code == "ENTRY_WITHOUT_SKU"

    def test_refuses_item_without_sku(self, entry):
        formula = flour_formula()
        formula["items"][2] = {"sku": "", "name": "sal grosso", "role": "salt", "quantity": 20, "unit": "g"}
        draft = recipe_book.create_version(entry, formula=formula, yield_quantity=1, yield_unit="kg")
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.publish_version(draft)
        assert exc.value.code == "ITEM_WITHOUT_SKU"
        assert exc.value.data["field"] == "items[2].sku"

    def test_refuses_a_version_that_is_not_a_draft(self, entry, draft):
        recipe_book.publish_version(draft)
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.publish_version(draft)
        assert exc.value.code == "VERSION_NOT_DRAFT"

    def test_refuses_part_without_formula(self, entry):
        draft = recipe_book.create_version(
            entry, formula=flour_formula(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20}]),
            yield_quantity=1, yield_unit="kg",
        )
        with pytest.raises(RecipeBookError) as exc:
            recipe_book.publish_version(draft)
        assert exc.value.code == "PART_WITHOUT_FORMULA"
        assert exc.value.data["field"] == "parts[0]"
        assert Recipe.objects.filter(ref="massa-tradicao").exists() is False

    def test_the_mass_invariant_of_the_sheet_still_speaks(self, entry):
        """10 kg de massa não saem de 1,72 kg de ingredientes; a ficha recusa e nada é gravado."""
        draft = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=10, yield_unit="kg")
        with pytest.raises(ValidationError):
            recipe_book.publish_version(draft)
        draft.refresh_from_db()
        assert draft.status == RecipeVersion.Status.DRAFT
        assert Recipe.objects.filter(ref="massa-tradicao").exists() is False


# ── Partes ───────────────────────────────────────────────────────────────────


class TestPartFormulas:
    def test_by_entry_ref_then_by_output_sku(self, published_levain):
        by_ref = recipe_book.part_formulas_for({"parts": [{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment"}]})
        by_sku = recipe_book.part_formulas_for({"parts": [{"sku": "LEVAIN", "kind": "preferment"}]})
        assert by_ref == {"LEVAIN": LEVAIN_FORMULA}
        assert by_sku == {"LEVAIN": LEVAIN_FORMULA}
        assert recipe_book.part_formulas_for({"parts": [{"sku": "POOLISH", "kind": "preferment"}, {"kind": "old_dough", "cap_pct": 10}]}) == {}


# ── Diff ─────────────────────────────────────────────────────────────────────


class TestDiff:
    def test_versions_are_compared_on_the_same_basis(self, entry):
        first = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
        informed = flour_formula(water=750)
        for item in informed["items"]:
            item["quantity"] = item["quantity"] * 3  # escrita em 3 kg de farinha
        informed.update(basis_g=None, standardized=False)
        second = recipe_book.create_version(entry, formula=informed, yield_quantity="5.3", yield_unit="kg")

        diff = recipe_book.diff_versions(first, second)
        assert diff.basis == "flour_1000"
        assert diff.a_ref == "massa-tradicao@1"
        rows = {row.sku: row for row in diff.rows}
        assert rows["AGUA-FILTRADA"].a_grams == Decimal("700")
        assert rows["AGUA-FILTRADA"].b_grams == Decimal("750")
        assert rows["AGUA-FILTRADA"].delta_grams == Decimal("50")
        assert rows["AGUA-FILTRADA"].delta_pct == Decimal("5")
        assert rows["FARINHA-T55"].delta_grams == Decimal("0")
        metrics = {metric.code: metric for metric in diff.metrics}
        assert metrics["hydration_pct"].delta == Decimal("5")
        assert metrics["salt_pct"].delta == Decimal("0")
        assert metrics["yield"].a == Decimal("1.700")
        assert metrics["yield"].delta == Decimal("3.6")
        assert metrics["yield"].unit == "kg"

    def test_ingredient_only_on_one_side_shows_up_with_none(self, entry):
        first = recipe_book.create_version(entry, formula=flour_formula(), yield_quantity=1, yield_unit="kg")
        with_malt = flour_formula()
        with_malt["items"].append({"sku": "MALTE", "name": "Malte", "role": "sugar", "quantity": 10, "unit": "g"})
        second = recipe_book.create_version(entry, formula=with_malt, yield_quantity=1, yield_unit="kg")
        rows = {row.sku: row for row in recipe_book.diff_versions(first, second).rows}
        assert rows["MALTE"].a_grams is None
        assert rows["MALTE"].b_grams == Decimal("10")
        assert rows["MALTE"].delta_grams is None


# ── Bootstrap ────────────────────────────────────────────────────────────────


def _sheet(ref, name, output_sku, batch, items, *, unit="kg"):
    recipe = Recipe.objects.create(ref=ref, name=name, output_sku=output_sku, batch_size=Decimal(batch),
                                   meta={"output_unit": unit})
    for order, (sku, quantity) in enumerate(items):
        RecipeItem.objects.create(recipe=recipe, input_sku=sku, quantity=Decimal(quantity), unit="kg", sort_order=order)
    return recipe


@pytest.fixture
def seeded_sheets():
    """As fichas do seed: levain 1:1:1, pasta autolisada 1000/700 e a Tradição que as consome."""
    levain = _sheet("creme-levain", "Levain", "LEVAIN", "5", [("FERMENTO-NAT", "1.7"), ("FARINHA-T65", "1.7"), ("AGUA-FILTRADA", "1.7")])
    pasta = _sheet("massa-pasta-autolizada", "Pasta Autolizada", "PASTA-AUTOLIZADA", "8.4", [("FARINHA-T65", "5"), ("AGUA-FILTRADA", "3.5")])
    tradicao = _sheet("massa-tradicao", "Massa Tradição", "MASSA-TRADICAO", "10",
                      [("PASTA-AUTOLIZADA", "8.4"), ("LEVAIN", "1.5"), ("SAL", "0.1")])
    return levain, pasta, tradicao


class TestBootstrap:
    def test_dissolves_the_parts_into_the_base(self, seeded_sheets):
        _, _, tradicao = seeded_sheets
        entry = recipe_book.bootstrap_entry_from_recipe(tradicao)

        assert entry.ref == "massa-tradicao"
        assert entry.kind == "bread"
        assert entry.output_sku == "MASSA-TRADICAO"
        version = entry.current_version
        assert version.number == 1
        assert version.status == RecipeVersion.Status.PUBLISHED
        assert version.published_at is not None
        assert version.source == {"kind": "ficha", "recipe_ref": "massa-tradicao"}
        assert version.yield_quantity == Decimal("10")
        assert version.yield_unit == "kg"
        assert version.origin["items"][0] == {"sku": "PASTA-AUTOLIZADA", "quantity": "8.400", "unit": "kg"}

        formula = version.formula
        assert formula["anchor"] == {"kind": "flour"}
        assert formula["basis_g"] is None
        assert formula["standardized"] is False
        items = {item["sku"]: item for item in formula["items"]}
        # A parte é a sua composição, proporcional aos insumos (a perda da ficha
        # dela é do forno, não da fórmula): 8,4 kg de uma pasta 5000/3500 levam
        # 4941,176 g de farinha; 1,5 kg de um levain 1:1:1 levam 500 g.
        assert items["FARINHA-T65"]["quantity"] == "5441.176"
        assert items["FARINHA-T65"]["role"] == "flour"
        assert items["FARINHA-T65"]["unit"] == "g"
        assert items["AGUA-FILTRADA"]["quantity"] == "3958.824"
        assert items["FERMENTO-NAT"]["quantity"] == "500"
        # A cultura (fermento natural) não é fermento biológico: fica fora da
        # métrica de fermento e da faixa de 0,5 a 3%.
        assert items["FERMENTO-NAT"]["role"] == "other"
        assert items["SAL"]["quantity"] == "100"

        parts = {part["sku"]: part for part in formula["parts"]}
        assert parts["LEVAIN"]["entry_ref"] == "creme-levain"
        assert parts["LEVAIN"]["kind"] == "preferment"
        assert parts["LEVAIN"]["quantity"] == "1500"
        assert parts["LEVAIN"]["flour_pct"] == "9.189"
        assert parts["PASTA-AUTOLIZADA"]["kind"] == "autolyse"
        assert parts["PASTA-AUTOLIZADA"]["quantity"] == "8400"
        assert parts["PASTA-AUTOLIZADA"]["flour_pct"] == "90.811"

        # As partes viraram entry antes, para o entry_ref existir.
        assert RecipeEntry.objects.filter(ref__in=["creme-levain", "massa-pasta-autolizada"]).count() == 2

    def test_the_base_derives_the_same_sheet_back(self, seeded_sheets):
        """Ida e volta: a base dissolvida, analisada com as partes, dá o BOM da ficha original."""
        _, _, tradicao = seeded_sheets
        entry = recipe_book.bootstrap_entry_from_recipe(tradicao)
        formula = entry.current_version.formula
        bom = {line["sku"]: line for line in recipe_book.derive_bom(formula, recipe_book.part_formulas_for(formula))}
        assert set(bom) == {"LEVAIN", "PASTA-AUTOLIZADA", "SAL"}
        assert bom["LEVAIN"]["quantity"] == Decimal("1500")
        assert bom["PASTA-AUTOLIZADA"]["quantity"] == Decimal("8400")
        assert bom["SAL"]["quantity"] == Decimal("100")

    def test_is_idempotent_and_does_not_touch_the_sheet(self, seeded_sheets):
        _, _, tradicao = seeded_sheets
        first = recipe_book.bootstrap_entry_from_recipe(tradicao)
        second = recipe_book.bootstrap_entry_from_recipe(tradicao)
        assert first.pk == second.pk
        assert RecipeEntry.objects.count() == 3
        assert RecipeVersion.objects.count() == 3
        tradicao.refresh_from_db()
        assert "version_ref" not in tradicao.meta
        assert tradicao.items.count() == 3

    def test_without_a_declared_output_unit_it_does_not_guess(self):
        pieces = Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CT", batch_size=Decimal("48"))
        RecipeItem.objects.create(recipe=pieces, input_sku="MASSA-CROISSANT", quantity=Decimal("8.5"), unit="kg")
        assert recipe_book.bootstrap_entry_from_recipe(pieces) is None
        assert RecipeEntry.objects.count() == 0

    def test_kind_by_name(self):
        croissant = _sheet("massa-croissant", "Massa Croissant", "MASSA-CROISSANT", "9", [("FARINHA-T55", "5"), ("MANTEIGA-FR", "4")])
        assert recipe_book.bootstrap_entry_from_recipe(croissant).kind == "viennoiserie"
        cream = _sheet("creme-confeiteiro", "Creme de Confeiteiro", "CREME-CONF", "2", [("LEITE", "1.5"), ("ACUCAR", "0.5")])
        assert recipe_book.bootstrap_entry_from_recipe(cream).kind == "cream"

    def test_the_command_orders_by_dependency_and_honors_dry_run(self, seeded_sheets):
        out = StringIO()
        call_command("bootstrap_recipe_book", "--dry-run", stdout=out)
        assert "3 criadas" in out.getvalue()
        assert RecipeEntry.objects.count() == 0

        out = StringIO()
        call_command("bootstrap_recipe_book", stdout=out)
        lines = [line for line in out.getvalue().splitlines() if line.startswith("  +")]
        assert [line.split()[1].rstrip(":") for line in lines] == ["creme-levain", "massa-pasta-autolizada", "massa-tradicao"]
        assert RecipeEntry.objects.count() == 3

        out = StringIO()
        call_command("bootstrap_recipe_book", stdout=out)
        assert "0 criadas, 3 puladas" in out.getvalue()


# ── Snapshot da fornada ──────────────────────────────────────────────────────


class TestWorkOrderSnapshot:
    def test_plan_freezes_the_version_ref(self, entry, draft):
        recipe = recipe_book.publish_version(draft)
        work_order = craft.plan(recipe, 1)
        snapshot = work_order.meta["_recipe_snapshot"]
        assert snapshot["version_ref"] == "massa-tradicao@1"
        assert {item["input_sku"] for item in snapshot["items"]} == {"FARINHA-T55", "AGUA-FILTRADA", "SAL"}

    def test_a_sheet_without_a_version_carries_an_empty_stamp(self):
        recipe = Recipe.objects.create(ref="pao-simples", name="Pão simples", output_sku="PAO", batch_size=Decimal("1"))
        work_order = craft.plan(recipe, 1)
        assert work_order.meta["_recipe_snapshot"]["version_ref"] == ""
