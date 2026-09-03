"""Projections do inventário de receitas: formatação, tons e composição da lente.

A conta é do Craftsman e tem teste lá; aqui se prova o que a superfície lê:
"850 g" e "1,2 kg", "85%" e "85,5%", o tom de cada métrica (calmo por padrão,
``warning`` fora da faixa, ``muted`` quando não se aplica), a mistura final e
o BOM com as partes, os avisos, a hidratação no cartão só com âncora de
farinha, o rascunho da captura casado com os insumos e a régua de acesso.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.projections import recipe_book as projections
from shopman.backstage.projections.recipe_book import (
    build_capture_draft,
    build_formula_lens,
    build_ingredient_options,
    build_recipe_book,
    build_recipe_compare,
    build_recipe_entry,
    build_recipe_reference,
    resolve_recipe_book_access,
    wire_formula,
)
from shopman.backstage.services.exceptions import RecipeEntryNotFound
from shopman.backstage.services.recipe_capture import CapturedItem, CapturedRecipe
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db


def flour_formula(*, water=700, salt=20, parts=None, extra=()):
    return {
        "anchor": {"kind": "flour"},
        "basis_g": None,
        "standardized": False,
        "items": [
            {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 1000, "unit": "g"},
            {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": water, "unit": "g"},
            {"sku": "SAL", "name": "Sal", "role": "salt", "quantity": salt, "unit": "g"},
            *extra,
        ],
        "parts": parts or [],
    }


@pytest.fixture
def published_levain():
    levain = craftsman.create_entry(ref="creme-levain", name="Levain", kind="bread", output_sku="LEVAIN")
    version = craftsman.create_version(
        levain,
        formula={
            "anchor": {"kind": "flour"},
            "items": [
                {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 500, "unit": "g"},
                {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 500, "unit": "g"},
            ],
            "parts": [],
        },
        yield_quantity=1000, yield_unit="g",
    )
    craftsman.publish_version(version)
    return levain


# ── Formatação ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("value", "expected"), [
    (None, ""),
    (Decimal("85"), "85%"),
    (Decimal("85.5"), "85,5%"),
    (Decimal("72.34"), "72,3%"),
    (Decimal("2.25"), "2,3%"),
    (Decimal("0"), "0%"),
])
def test_pct_display(value, expected):
    assert projections._pct_display(value) == expected


@pytest.mark.parametrize(("grams", "expected"), [
    (None, ""),
    (Decimal("850"), "850 g"),
    (Decimal("6.667"), "6,667 g"),
    (Decimal("1000"), "1 kg"),
    (Decimal("1200"), "1,2 kg"),
    (Decimal("1720"), "1,72 kg"),
])
def test_grams_display(grams, expected):
    assert projections._grams_display(grams) == expected


def test_quantity_stays_in_the_bakers_unit():
    assert projections._quantity_display(Decimal("3"), "un") == "3 un"
    assert projections._quantity_display(Decimal("0.700"), "kg") == "0,7 kg"
    assert projections._quantity_display(None, "g") == ""


def test_wire_formula_makes_basis_numeric():
    assert wire_formula({"basis_g": "1000", "items": []})["basis_g"] == 1000
    assert wire_formula({"basis_g": "1250.5"})["basis_g"] == 1250.5
    assert wire_formula({"basis_g": None})["basis_g"] is None
    assert wire_formula({})["basis_g"] is None
    assert wire_formula("x") == {}


# ── Lente ────────────────────────────────────────────────────────────────────


def test_bakery_lens_items_metrics_and_tones(published_levain):
    lens = build_formula_lens(
        flour_formula(parts=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20}]),
        "bread",
    )
    assert lens.is_bakery is True
    assert lens.anchor_kind == "flour"
    assert lens.anchor_label == "Farinhas totais"
    assert lens.basis_display == ""
    assert lens.standardized is False
    assert lens.anchor_total_display == "1 kg"
    assert lens.total_mass_display == "1,72 kg"

    flour, water, salt = lens.items
    assert (flour.pct_display, flour.is_anchor, flour.matched, flour.role_label) == ("100%", True, True, "Farinha")
    assert (water.quantity_display, water.quantity_g, water.pct_display, water.is_anchor) == ("700 g", "700", "70%", False)
    assert salt.pct_display == "2%"

    assert [(item.sku, item.quantity_display) for item in lens.final_mix] == [
        ("FARINHA-T55", "800 g"), ("AGUA-FILTRADA", "500 g"), ("SAL", "20 g"),
    ]
    assert [(item.sku, item.quantity_display, item.role_label) for item in lens.bom] == [
        ("FARINHA-T55", "800 g", "Farinha"), ("AGUA-FILTRADA", "500 g", "Líquido"),
        ("SAL", "20 g", "Sal"), ("LEVAIN", "400 g", "Pré-fermento"),
    ]
    (part,) = lens.parts
    assert part.kind_label == "Pré-fermento"
    assert part.flour_pct_display == "20%"
    assert part.quantity_display == "400 g"
    assert part.has_formula is True
    assert part.entry_ref == "creme-levain"

    tones = {metric.code: metric.tone for metric in lens.metrics}
    assert tones == {
        "hydration_pct": "ok", "salt_pct": "ok", "yeast_pct": "muted", "prefermented_flour_pct": "ok",
        "fat_pct": "muted", "sugar_pct": "muted", "egg_pct": "muted",
    }
    hydration = next(metric for metric in lens.metrics if metric.code == "hydration_pct")
    assert (hydration.value_display, hydration.low_display, hydration.high_display, hydration.max_display) == ("70%", "60%", "85%", "")
    assert "Rústico" in hydration.note
    assert lens.warnings == ()


def test_out_of_range_is_a_calm_warning_never_a_block():
    lens = build_formula_lens(flour_formula(water=950, salt=30), "bread")
    tones = {metric.code: metric.tone for metric in lens.metrics}
    assert tones["hydration_pct"] == "warning"
    assert tones["salt_pct"] == "warning"
    codes = [warning.code for warning in lens.warnings]
    assert "REFERENCE_OUT_OF_RANGE" in codes
    assert "REFERENCE_ABOVE_MAX" in codes
    assert all(warning.tone == "warning" for warning in lens.warnings)


def test_analysis_warnings_and_their_tone():
    lens = build_formula_lens(
        flour_formula(
            parts=[{"sku": "POOLISH", "kind": "preferment", "flour_pct": 30}],
            extra=(
                {"sku": "LEITE", "name": "Leite", "role": "liquid", "quantity": 100, "unit": "ml"},
                {"sku": "OVOS", "name": "Ovos", "role": "egg", "quantity": 2, "unit": "un"},
            ),
        ),
        "bread",
    )
    warnings = {warning.code: warning for warning in lens.warnings}
    assert warnings["PART_WITHOUT_FORMULA"].tone == "warning"
    assert warnings["LIQUID_DENSITY_ASSUMED"].tone == "muted"
    assert warnings["COUNT_WITHOUT_GRAMS_PER_UNIT"].tone == "warning"
    (part,) = lens.parts
    assert part.has_formula is False
    assert part.flour_pct_display == "30%"
    eggs = next(item for item in lens.items if item.sku == "OVOS")
    assert (eggs.quantity_display, eggs.quantity_g, eggs.pct_display) == ("2 un", "", "")


def test_non_flour_anchor_mutes_the_bakery_metrics():
    cream = {
        "anchor": {"kind": "total"},
        "items": [
            {"sku": "LEITE", "name": "Leite", "role": "dairy", "quantity": 1, "unit": "kg"},
            {"sku": "ACUCAR", "name": "Açúcar", "role": "sugar", "quantity": 250, "unit": "g"},
        ],
        "parts": [],
    }
    lens = build_formula_lens(cream, "cream")
    assert lens.is_bakery is False
    assert lens.anchor_label == "Massa total"
    assert lens.anchor_total_display == "1,25 kg"
    assert [item.pct_display for item in lens.items] == ["80%", "20%"]
    assert all(not item.is_anchor for item in lens.items)
    assert {metric.tone for metric in lens.metrics} == {"muted"}
    assert all(metric.value_display == "" for metric in lens.metrics)


def test_ingredient_anchor_names_the_ingredient():
    ganache = {
        "anchor": {"kind": "ingredient", "sku": "CHOCOLATE"},
        "items": [
            {"sku": "CHOCOLATE", "name": "Chocolate 70%", "role": "inclusion", "quantity": 200, "unit": "g"},
            {"sku": "CREME", "name": "Creme de leite", "role": "dairy", "quantity": 200, "unit": "g"},
        ],
        "parts": [],
    }
    lens = build_formula_lens(ganache, "filling")
    assert lens.anchor_label == "Um ingrediente (Chocolate 70%)"
    assert [item.is_anchor for item in lens.items] == [True, False]
    assert [item.pct_display for item in lens.items] == ["100%", "100%"]


def test_old_dough_shows_its_cap_and_stays_out_of_the_consumption():
    lens = build_formula_lens(flour_formula(parts=[{"kind": "old_dough", "cap_pct": 20}]), "bread")
    (part,) = lens.parts
    assert part.kind_label == "Massa velha"
    assert part.cap_pct_display == "20%"
    assert part.has_formula is False
    old_dough = lens.bom[-1]
    assert old_dough.role_label == "Massa velha"
    assert old_dough.matched is False


def test_lens_survives_a_row_being_typed():
    formula = flour_formula(extra=({"sku": "", "name": "", "role": "other", "quantity": 0, "unit": "g"},))
    lens = build_formula_lens(formula, "bread")
    assert len(lens.items) == 4
    assert lens.items[-1].quantity_display == "0 g"
    assert build_formula_lens({}, "bread").items == ()
    assert build_formula_lens("nada", "bread").is_bakery is False


# ── Inventário e receita ─────────────────────────────────────────────────────


def test_card_hydration_only_with_a_flour_anchor():
    bread = craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO")
    craftsman.publish_version(craftsman.create_version(bread, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg"))
    cream = craftsman.create_entry(ref="creme-confeiteiro", name="Creme de Confeiteiro", kind="cream", output_sku="CREME-CONF")
    craftsman.publish_version(craftsman.create_version(
        cream,
        formula={
            "anchor": {"kind": "total"},
            "items": [{"sku": "LEITE", "name": "Leite", "role": "dairy", "quantity": 1, "unit": "kg"}],
            "parts": [],
        },
        yield_quantity=1, yield_unit="kg",
    ))
    craftsman.create_version(cream, formula={
        "anchor": {"kind": "total"},
        "items": [{"sku": "LEITE", "name": "Leite", "role": "dairy", "quantity": 2, "unit": "kg"}],
        "parts": [],
    }, yield_quantity=2, yield_unit="kg")
    Material.objects.create(sku="CREME-CONF", name="Creme de confeiteiro pronto", unit="kg")

    book = build_recipe_book()
    cards = {card.ref: card for card in book.entries}
    assert book.count == 2
    assert cards["massa-tradicao"].hydration_display == "70%"
    assert cards["massa-tradicao"].anchor_kind == "flour"
    assert cards["massa-tradicao"].has_ficha is True
    assert cards["massa-tradicao"].output_name == ""
    assert cards["creme-confeiteiro"].hydration_display == ""
    assert cards["creme-confeiteiro"].anchor_kind == "total"
    assert cards["creme-confeiteiro"].output_name == "Creme de confeiteiro pronto"
    assert (cards["creme-confeiteiro"].version_count, cards["creme-confeiteiro"].draft_count) == (2, 1)
    assert cards["creme-confeiteiro"].updated_at_display.count("/") == 2


def test_entry_detail_orders_versions_newest_first_and_names_the_sheet():
    entry = craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO")
    craftsman.publish_version(craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg"))
    craftsman.create_version(entry, formula=flour_formula(water=750), yield_quantity="1.7", yield_unit="kg", label="mais água")

    detail = build_recipe_entry("massa-tradicao")
    assert detail.ficha_ref == "massa-tradicao"
    assert detail.current_version_number == 1
    assert [version.number for version in detail.versions] == [2, 1]
    assert detail.versions[0].status_label == "Rascunho"
    assert detail.versions[0].label == "mais água"
    assert detail.versions[0].published_at_display == ""
    assert detail.versions[1].status_label == "Publicada"
    assert detail.versions[1].published_at_display != ""
    assert detail.versions[1].source_label == "Manual"
    assert detail.versions[1].formula["items"][0]["sku"] == "FARINHA-T55"

    with pytest.raises(RecipeEntryNotFound):
        build_recipe_entry("nao-existe")


def test_a_bootstrapped_sheet_reads_as_a_ficha_version():
    recipe = Recipe.objects.create(ref="massa-yudane", name="Yudane", output_sku="YUDANE", batch_size=Decimal("1.9"),
                                   meta={"output_unit": "kg"})
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA-T55", quantity=Decimal("1"), unit="kg", sort_order=0)
    RecipeItem.objects.create(recipe=recipe, input_sku="AGUA-FILTRADA", quantity=Decimal("1"), unit="kg", sort_order=1)
    craftsman.bootstrap_entry_from_recipe(recipe)

    detail = build_recipe_entry("massa-yudane")
    (version,) = detail.versions
    assert version.source_kind == "ficha"
    assert version.source_label == "Ficha técnica"
    assert version.yield_display == "1,9 kg"
    assert version.lens.is_bakery is True
    hydration = next(metric for metric in version.lens.metrics if metric.code == "hydration_pct")
    assert hydration.value_display == "100%"


# ── Comparação e referência ──────────────────────────────────────────────────


def test_compare_tones_and_deltas():
    entry = craftsman.create_entry(ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO")
    craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
    with_malt = flour_formula(water=750, extra=({"sku": "MALTE", "name": "Malte", "role": "sugar", "quantity": 10, "unit": "g"},))
    craftsman.create_version(entry, formula=with_malt, yield_quantity="1.7", yield_unit="kg")

    compare = build_recipe_compare("massa-tradicao@1", "massa-tradicao@2")
    rows = {row.sku: row for row in compare.rows}
    assert rows["FARINHA-T55"].tone == "muted"
    assert rows["FARINHA-T55"].delta_display == "0 g"
    assert rows["AGUA-FILTRADA"].tone == "ok"
    assert rows["AGUA-FILTRADA"].delta_display == "+50 g"
    assert rows["MALTE"].tone == "warning"
    assert (rows["MALTE"].a_display, rows["MALTE"].b_display, rows["MALTE"].delta_display) == ("", "10 g", "")
    metrics = {metric.label: metric for metric in compare.metrics}
    assert metrics["Rendimento"].tone == "muted"
    assert metrics["Hidratação"].delta_display == "+5%"
    assert metrics["Sal"].tone == "muted"


def test_reference_for_kind():
    bread = build_recipe_reference("bread")
    assert bread.kind_label == "Pão"
    codes = [entry.code for entry in bread.ranges]
    assert codes[:4] == ["hydration_pct", "salt_pct", "yeast_pct", "prefermented_flour_pct"]
    assert "part_flour_pct:old_dough" in codes
    other = build_recipe_reference("")
    assert other.kind == "other"
    assert [entry.code for entry in other.ranges] == ["salt_pct", "yeast_pct"]


# ── Insumos e captura ────────────────────────────────────────────────────────


def test_ingredient_options_prefer_the_part_over_a_material_with_the_same_sku(published_levain):
    Material.objects.create(sku="LEVAIN", name="Levain (insumo)", unit="kg")
    Material.objects.create(sku="FARINHA-T55", name="Farinha de trigo T55", unit="kg")
    options = build_ingredient_options("")
    levain = [option for option in options if option.sku == "LEVAIN"]
    assert len(levain) == 1
    assert levain[0].is_part is True
    assert levain[0].name == "Levain"
    assert [option.sku for option in options] == ["LEVAIN", "FARINHA-T55"]


def test_capture_draft_matches_ingredients_and_builds_a_flour_formula(published_levain):
    Material.objects.create(sku="FARINHA-T65", name="Farinha de trigo T65", unit="kg")
    Material.objects.create(sku="AGUA-FILTRADA", name="Água filtrada", unit="l")
    Material.objects.create(sku="SAL", name="Sal", unit="kg")
    captured = CapturedRecipe(
        name="Pão de campanha", kind="bread", language="fr", yield_quantity=Decimal("2"), yield_unit="un",
        items=(
            CapturedItem(name="Farinha de trigo T65", original_text="Farine T65 1 kg", quantity=Decimal("1"), unit="kg", role="flour"),
            CapturedItem(name="Água", original_text="Eau 700 g", quantity=Decimal("700"), unit="g", role="other"),
            CapturedItem(name="Levain", original_text="Levain 200 g", quantity=Decimal("200"), unit="g", role="other"),
            CapturedItem(name="Pimenta rosa", original_text="Baies roses", quantity=None, unit="g", role="other", note="q.b."),
        ),
        steps=("Sovar.",), notes="", raw_text="{}",
    )
    draft = build_capture_draft(captured)
    assert draft.yield_quantity == "2"
    flour, water, levain, pepper = draft.items
    assert (flour.sku, flour.role, flour.quantity, flour.unit) == ("FARINHA-T65", "flour", "1", "kg")
    assert flour.match_confidence.endswith("%")
    assert flour.candidates[0].sku == "FARINHA-T65"
    assert (water.sku, water.role) == ("AGUA-FILTRADA", "liquid")
    assert (levain.sku, levain.role) == ("LEVAIN", "other")
    assert any(candidate.is_part and candidate.entry_ref == "creme-levain" for candidate in levain.candidates)
    assert (pepper.sku, pepper.quantity, pepper.match_confidence) == ("", "", "")

    assert draft.formula["anchor"] == {"kind": "flour"}
    assert draft.formula["standardized"] is False
    assert [(line["sku"], line["quantity"], line["unit"]) for line in draft.formula["items"]] == [
        ("FARINHA-T65", "1000", "g"), ("AGUA-FILTRADA", "700", "g"), ("LEVAIN", "200", "g"),
    ]


def test_capture_draft_without_flour_anchors_on_the_total():
    captured = CapturedRecipe(
        name="Ganache", kind="filling", language="pt", yield_quantity=None, yield_unit="g",
        items=(CapturedItem(name="Chocolate", original_text="Chocolate 200 g", quantity=Decimal("200"), unit="g", role="inclusion"),),
        steps=(), notes="", raw_text="{}",
    )
    draft = build_capture_draft(captured)
    assert draft.yield_quantity == ""
    assert draft.formula["anchor"] == {"kind": "total"}


# ── Acesso ───────────────────────────────────────────────────────────────────


def test_access_rule():
    from shopman.shop.models import Shop

    viewer = grant_production_operator(User.objects.create_user("viewer", password="pw", is_staff=True))
    editor = grant_production_operator(User.objects.create_user("editor", password="pw", is_staff=True))
    editor.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shop), codename="manage_production",
    ))
    editor = User.objects.get(pk=editor.pk)
    sheet_reader = User.objects.create_user("sheet-reader", password="pw", is_staff=True)
    sheet_reader.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Recipe), codename="view_recipe",
    ))
    sheet_reader = User.objects.get(pk=sheet_reader.pk)
    bare = User.objects.create_user("bare", password="pw", is_staff=True)
    superuser = User.objects.create_superuser("root", "root@test.com", "pw")

    assert (resolve_recipe_book_access(viewer).can_view, resolve_recipe_book_access(viewer).can_edit) == (True, False)
    assert (resolve_recipe_book_access(editor).can_view, resolve_recipe_book_access(editor).can_edit) == (True, True)
    assert (resolve_recipe_book_access(sheet_reader).can_view, resolve_recipe_book_access(sheet_reader).can_edit) == (True, False)
    assert (resolve_recipe_book_access(bare).can_view, resolve_recipe_book_access(bare).can_edit) == (False, False)
    assert resolve_recipe_book_access(superuser).can_edit is True
    assert resolve_recipe_book_access(AnonymousUser()).can_view is False
    assert resolve_recipe_book_access(viewer).capture_available is False


def test_a_cream_with_a_flour_anchor_is_not_a_bakery_lens():
    """Creme com muita farinha continua creme: sem métricas de padaria, mesmo com âncora de farinha."""
    formula = {
        "anchor": {"kind": "flour"},
        "items": [
            {"sku": "FARINHA-T55", "name": "Farinha", "role": "flour", "quantity": 300, "unit": "g"},
            {"sku": "LEITE", "name": "Leite", "role": "liquid", "quantity": 1000, "unit": "g"},
            {"sku": "ACUCAR", "name": "Açúcar", "role": "sugar", "quantity": 250, "unit": "g"},
        ],
        "parts": [],
    }
    assert projections.build_formula_lens(formula, "bread").is_bakery is True
    lens = projections.build_formula_lens(formula, "cream")
    assert lens.is_bakery is False
    assert lens.anchor_kind == "flour"
    assert lens.items[0].pct_display == "100%"
