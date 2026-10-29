"""Projections do inventário de receitas: formatação, tons e composição da lente.

A conta é do Craftsman e tem teste lá; aqui se prova o que a superfície lê:
"850 g" e "1,2 kg", "85%" e "85,5%", o tom de cada métrica (calmo por padrão,
``warning`` fora da faixa, ``muted`` quando não se aplica), a mistura final e
o BOM com as preps, os avisos, a hidratação no cartão só com âncora de
farinha, o rascunho da captura casado com os insumos e a régua de acesso.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.services import recipe_book as craftsman
from shopman.stockman.models import Batch
from shopman.stockman.services.movements import StockMovements

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


def _fixed(ref, sku, name, role, quantity, unit="g"):
    return {
        "ref": ref,
        "sku": sku,
        "name": name,
        "role": role,
        "quantity": {"kind": "fixed", "minimum": quantity, "target": quantity, "maximum": quantity, "unit": unit},
        "composition": "additional",
    }


def flour_formula(*, water=700, salt=20, preps=None, extra=()):
    extras = [
        _fixed(
            f"ingredient-extra-{index}",
            item.get("sku", ""),
            item.get("name", ""),
            item.get("role", "other"),
            item.get("quantity", 0),
            item.get("unit", "g"),
        )
        for index, item in enumerate(extra, start=1)
    ]
    recipe_ingredients = [
        {
            "ref": f"ingredient-recipe-{index}",
            "sku": item.get("sku", ""),
            "name": item.get("name") or item.get("sku") or "Ingrediente",
            "role": "other",
            "recipe_version_ref": f"{item['entry_ref']}@1" if item.get("entry_ref") else "",
            "composition": "included",
            "quantity": {
                "kind": "ratio",
                "minimum": item.get("flour_pct"),
                "target": item.get("flour_pct"),
                "maximum": item.get("flour_pct"),
                "basis": {"kind": "flour"},
            },
        }
        for index, item in enumerate(preps or [], start=1)
        if item.get("entry_ref")
    ]
    return {
        "anchor": {"kind": "flour"},
        "basis_g": None,
        "standardized": False,
        "ingredients": [
            _fixed("ingredient-flour", "FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", 1000),
            _fixed("ingredient-water", "AGUA-FILTRADA", "Água", "liquid", water),
            _fixed("ingredient-salt", "SAL-REFINADO", "Sal", "salt", salt),
            *extras,
            *recipe_ingredients,
        ],
    }


@pytest.fixture
def published_levain():
    levain = craftsman.create_entry(ref="creme-levain", name="Levain", kind="bread", output_sku="LEVAIN")
    version = craftsman.create_version(
        levain,
        formula={
            "anchor": {"kind": "flour"},
            "ingredients": [
                _fixed("ingredient-flour", "FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", 500),
                _fixed("ingredient-water", "AGUA-FILTRADA", "Água", "liquid", 500),
            ],
        },
        yield_quantity=1000,
        yield_unit="g",
    )
    craftsman.publish_version(version)
    return levain


# ── Formatação ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (Decimal("85"), "85%"),
        (Decimal("85.5"), "85,5%"),
        (Decimal("72.34"), "72,3%"),
        (Decimal("2.25"), "2,3%"),
        (Decimal("0"), "0%"),
    ],
)
def test_pct_display(value, expected):
    assert projections._pct_display(value) == expected


@pytest.mark.parametrize(
    ("grams", "expected"),
    [
        (None, ""),
        (Decimal("850"), "850 g"),
        (Decimal("6.667"), "6,667 g"),
        (Decimal("1000"), "1 kg"),
        (Decimal("1200"), "1,2 kg"),
        (Decimal("1720"), "1,72 kg"),
    ],
)
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
        flour_formula(preps=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20}]),
        "bread",
    )
    assert lens.is_bakery is True
    assert lens.anchor_kind == "flour"
    assert lens.anchor_label == "Farinhas totais"
    assert lens.basis_display == ""
    assert lens.standardized is False
    assert lens.anchor_total_display == "1 kg"
    assert lens.total_mass_display == "1,72 kg"

    flour, water, salt, levain = lens.ingredients
    assert (flour.pct_display, flour.is_anchor, flour.matched, flour.role_label) == ("100%", True, True, "Farinha")
    assert (water.quantity_display, water.quantity_g, water.pct_display, water.is_anchor) == (
        "700 g",
        "700",
        "70%",
        False,
    )
    assert salt.pct_display == "2%"

    assert [(item.sku, item.quantity_display) for item in lens.final_mix] == [
        ("FARINHA-ANACONDA-PREMIUM", "900 g"),
        ("AGUA-FILTRADA", "600 g"),
        ("SAL-REFINADO", "20 g"),
    ]
    assert [(item.sku, item.quantity_display, item.role_label) for item in lens.bom] == [
        ("FARINHA-ANACONDA-PREMIUM", "900 g", "Farinha"),
        ("AGUA-FILTRADA", "600 g", "Líquido"),
        ("SAL-REFINADO", "20 g", "Sal"),
        ("LEVAIN", "200 g", "Outro"),
    ]
    assert levain.recipe_version_ref == "creme-levain@1"
    assert levain.ref == "ingredient-recipe-1"
    assert levain.composition_label == "Inclusa"
    assert levain.quantity_display == "200 g"
    assert levain.quantity_rule_display == "Exata: 20% das farinhas"

    tones = {metric.code: metric.tone for metric in lens.metrics}
    assert tones == {
        "hydration_pct": "ok",
        "salt_pct": "ok",
        "yeast_pct": "muted",
        "fat_pct": "muted",
        "sugar_pct": "muted",
        "egg_pct": "muted",
    }
    hydration = next(metric for metric in lens.metrics if metric.code == "hydration_pct")
    assert (hydration.value_display, hydration.low_display, hydration.high_display, hydration.max_display) == (
        "70%",
        "60%",
        "85%",
        "",
    )
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


def test_lens_explains_a_maximum_ratio_against_the_whole_formula(published_levain):
    formula = flour_formula(
        preps=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 15}],
    )
    formula["ingredients"][-1]["quantity"] = {
        "kind": "ratio",
        "minimum": None,
        "target": 15,
        "maximum": 20,
        "basis": {"kind": "total"},
    }

    levain = build_formula_lens(formula, "bread").ingredients[-1]

    assert levain.ref == "ingredient-recipe-1"
    assert levain.quantity_rule_display == "Máxima: até 20% da fórmula"


def test_analysis_warnings_and_their_tone():
    lens = build_formula_lens(
        flour_formula(
            preps=[{"sku": "POOLISH", "entry_ref": "poolish-inexistente", "kind": "preferment", "flour_pct": 30}],
            extra=(
                {"sku": "LEITE-INTEGRAL-A", "name": "Leite", "role": "liquid", "quantity": 100, "unit": "ml"},
                {"sku": "OVOS", "name": "Ovos", "role": "egg", "quantity": 2, "unit": "un"},
            ),
        ),
        "bread",
    )
    warnings = {warning.code: warning for warning in lens.warnings}
    assert warnings["INGREDIENT_RECIPE_NOT_FOUND"].tone == "warning"
    assert warnings["LIQUID_DENSITY_ASSUMED"].tone == "muted"
    assert warnings["COUNT_WITHOUT_GRAMS_PER_UNIT"].tone == "warning"
    eggs = next(item for item in lens.ingredients if item.sku == "OVOS")
    assert (eggs.quantity_display, eggs.quantity_g, eggs.pct_display) == ("2 un", "", "")


def test_non_flour_anchor_mutes_the_bakery_metrics():
    cream = {
        "anchor": {"kind": "total"},
        "ingredients": [
            _fixed("ingredient-milk", "LEITE-INTEGRAL-A", "Leite", "dairy", 1, "kg"),
            _fixed("ingredient-sugar", "ACUCAR-CRISTAL", "Açúcar", "sugar", 250),
        ],
    }
    lens = build_formula_lens(cream, "cream")
    assert lens.is_bakery is False
    assert lens.anchor_label == "Massa total"
    assert lens.anchor_total_display == "1,25 kg"
    assert [item.pct_display for item in lens.ingredients] == ["80%", "20%"]
    assert all(not item.is_anchor for item in lens.ingredients)
    assert {metric.tone for metric in lens.metrics} == {"muted"}
    assert all(metric.value_display == "" for metric in lens.metrics)


def test_ingredient_anchor_names_the_ingredient():
    ganache = {
        "anchor": {"kind": "ingredient", "sku": "CHOCOLATE"},
        "ingredients": [
            _fixed("ingredient-chocolate", "CHOCOLATE", "Chocolate 70%", "inclusion", 200),
            _fixed("ingredient-cream", "CREME", "Creme de leite", "dairy", 200),
        ],
    }
    lens = build_formula_lens(ganache, "filling")
    assert lens.anchor_label == "Um ingrediente (Chocolate 70%)"
    assert [item.is_anchor for item in lens.ingredients] == [True, False]
    assert [item.pct_display for item in lens.ingredients] == ["100%", "100%"]


def test_lens_survives_a_row_being_typed():
    formula = flour_formula(extra=({"sku": "", "name": "", "role": "other", "quantity": 0, "unit": "g"},))
    lens = build_formula_lens(formula, "bread")
    assert len(lens.ingredients) == 4
    assert lens.ingredients[-1].quantity_display == "0 g"
    assert build_formula_lens({}, "bread").ingredients == ()
    assert build_formula_lens("nada", "bread").is_bakery is False


# ── Inventário e receita ─────────────────────────────────────────────────────


def test_card_hydration_only_with_a_flour_anchor():
    bread = craftsman.create_entry(
        ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO"
    )
    craftsman.publish_version(
        craftsman.create_version(bread, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
    )
    cream = craftsman.create_entry(
        ref="creme-confeiteiro", name="Creme de Confeiteiro", kind="cream", output_sku="CREME-CONF"
    )
    craftsman.publish_version(
        craftsman.create_version(
            cream,
            formula={
                "anchor": {"kind": "total"},
                "ingredients": [_fixed("ingredient-milk", "LEITE-INTEGRAL-A", "Leite", "dairy", 1, "kg")],
            },
            yield_quantity=1,
            yield_unit="kg",
        )
    )
    craftsman.create_version(
        cream,
        formula={
            "anchor": {"kind": "total"},
            "ingredients": [_fixed("ingredient-milk", "LEITE-INTEGRAL-A", "Leite", "dairy", 2, "kg")],
        },
        yield_quantity=2,
        yield_unit="kg",
    )
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
    entry = craftsman.create_entry(
        ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO"
    )
    craftsman.publish_version(
        craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
    )
    craftsman.create_version(
        entry, formula=flour_formula(water=750), yield_quantity="1.7", yield_unit="kg", label="mais água"
    )

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
    assert detail.versions[1].formula["ingredients"][0]["sku"] == "FARINHA-ANACONDA-PREMIUM"

    with pytest.raises(RecipeEntryNotFound):
        build_recipe_entry("nao-existe")


def test_entry_detail_says_whether_the_sheet_is_still_the_published_version():
    """ADR-027: a ficha editada por fora (Admin) deixa de estar em sincronia."""
    entry = craftsman.create_entry(
        ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO"
    )
    assert build_recipe_entry("massa-tradicao").execution_in_sync is False  # sem versão nem ficha

    recipe = craftsman.publish_version(
        craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg"),
    )
    assert build_recipe_entry("massa-tradicao").execution_in_sync is True

    item = recipe.items.get(input_sku="AGUA-FILTRADA")
    item.quantity = Decimal("750")
    item.save()
    assert build_recipe_entry("massa-tradicao").execution_in_sync is False


def test_a_bootstrapped_sheet_reads_as_a_ficha_version():
    recipe = Recipe.objects.create(
        ref="massa-yudane", name="Yudane", output_sku="YUDANE", batch_size=Decimal("1.9"), meta={"output_unit": "kg"}
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA-ANACONDA-PREMIUM", quantity=Decimal("1"), unit="kg", sort_order=0
    )
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
    entry = craftsman.create_entry(
        ref="massa-tradicao", name="Massa Tradição", kind="bread", output_sku="MASSA-TRADICAO"
    )
    craftsman.create_version(entry, formula=flour_formula(), yield_quantity="1.7", yield_unit="kg")
    with_malt = flour_formula(
        water=750, extra=({"sku": "MALTE-EXTRATO", "name": "Malte", "role": "sugar", "quantity": 10, "unit": "g"},)
    )
    craftsman.create_version(entry, formula=with_malt, yield_quantity="1.7", yield_unit="kg")

    compare = build_recipe_compare("massa-tradicao@1", "massa-tradicao@2")
    rows = {row.sku: row for row in compare.rows}
    assert rows["FARINHA-ANACONDA-PREMIUM"].tone == "muted"
    assert rows["FARINHA-ANACONDA-PREMIUM"].delta_display == "0 g"
    assert rows["AGUA-FILTRADA"].tone == "ok"
    assert rows["AGUA-FILTRADA"].delta_display == "+50 g"
    assert rows["MALTE-EXTRATO"].tone == "warning"
    assert (rows["MALTE-EXTRATO"].a_display, rows["MALTE-EXTRATO"].b_display, rows["MALTE-EXTRATO"].delta_display) == (
        "",
        "10 g",
        "",
    )
    metrics = {metric.label: metric for metric in compare.metrics}
    assert metrics["Rendimento"].tone == "muted"
    assert metrics["Hidratação"].delta_display == "+5%"
    assert metrics["Sal"].tone == "muted"


def test_reference_for_kind():
    bread = build_recipe_reference("bread")
    assert bread.kind_label == "Pão"
    codes = [entry.code for entry in bread.ranges]
    assert codes[:3] == ["hydration_pct", "salt_pct", "yeast_pct"]
    other = build_recipe_reference("")
    assert other.kind == "other"
    assert [entry.code for entry in other.ranges] == ["salt_pct", "yeast_pct"]


# ── Insumos e captura ────────────────────────────────────────────────────────


def test_ingredient_options_prefer_the_prep_over_a_material_with_the_same_sku(published_levain):
    Material.objects.create(sku="LEVAIN", name="Levain (insumo)", unit="kg")
    Material.objects.create(sku="FARINHA-ANACONDA-PREMIUM", name="Farinha de trigo T55", unit="kg")
    options = build_ingredient_options("")
    levain = [option for option in options if option.sku == "LEVAIN"]
    assert len(levain) == 1
    assert levain[0].has_recipe is True
    assert levain[0].name == "Levain"
    assert [option.sku for option in options] == ["LEVAIN", "FARINHA-ANACONDA-PREMIUM"]


def test_old_dough_with_stock_is_an_ordinary_ingredient_option():
    batch = Batch.objects.create(
        ref="MV-PAO-001",
        sku="MASSA-VELHA-PAO-FRANCES",
        production_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timedelta(days=1),
        metadata={
            "resource_kind": "old_dough",
            "ingredient_name": "Massa velha de Pão Francês",
            "recipe_version_ref": "pao-frances@3",
            "composition_snapshot": {"ingredients": []},
        },
    )
    StockMovements.receive(
        quantity=Decimal("850"),
        sku=batch.sku,
        batch=batch.ref,
        reason="Registrar massa velha",
    )

    option = next(option for option in build_ingredient_options("massa velha") if option.sku == batch.sku)

    assert option.name == "Massa velha de Pão Francês"
    assert option.unit == "g"
    assert option.has_recipe is True
    assert option.recipe_version_ref == "pao-frances@3"
    assert option.default_composition == "included"


def test_expired_old_dough_resource_remains_selectable_without_claiming_availability():
    batch = Batch.objects.create(
        ref="MV-PAO-EXPIRADA",
        sku="MASSA-VELHA-PAO-EXPIRADA",
        production_date=timezone.localdate() - timedelta(days=2),
        expiry_date=timezone.localdate() - timedelta(days=1),
        metadata={
            "resource_kind": "old_dough",
            "ingredient_name": "Massa velha de Pão Expirada",
            "recipe_version_ref": "pao-expirado@1",
        },
    )
    StockMovements.receive(quantity=Decimal("850"), sku=batch.sku, batch=batch.ref, reason="Registro antigo")

    assert batch.sku in {option.sku for option in build_ingredient_options("massa velha")}


def test_capture_draft_matches_ingredients_and_builds_a_flour_formula(published_levain):
    Material.objects.create(sku="FARINHA-NOVARA-T55", name="Farinha de trigo T65", unit="kg")
    Material.objects.create(sku="AGUA-FILTRADA", name="Água filtrada", unit="l")
    Material.objects.create(sku="SAL-REFINADO", name="Sal", unit="kg")
    captured = CapturedRecipe(
        name="Pão de campanha",
        kind="bread",
        language="fr",
        yield_quantity=Decimal("2"),
        yield_unit="un",
        items=(
            CapturedItem(
                name="Farinha de trigo T65",
                original_text="Farine T65 1 kg",
                quantity=Decimal("1"),
                unit="kg",
                role="flour",
            ),
            CapturedItem(name="Água", original_text="Eau 700 g", quantity=Decimal("700"), unit="g", role="other"),
            CapturedItem(name="Levain", original_text="Levain 200 g", quantity=Decimal("200"), unit="g", role="other"),
            CapturedItem(
                name="Pimenta rosa", original_text="Baies roses", quantity=None, unit="g", role="other", note="q.b."
            ),
        ),
        steps=("Sovar.",),
        notes="",
        raw_text="{}",
    )
    draft = build_capture_draft(captured)
    assert draft.yield_quantity == "2"
    flour, water, levain, pepper = draft.items
    assert (flour.sku, flour.role, flour.quantity, flour.unit) == ("FARINHA-NOVARA-T55", "flour", "1", "kg")
    assert flour.match_confidence.endswith("%")
    assert flour.candidates[0].sku == "FARINHA-NOVARA-T55"
    assert (water.sku, water.role) == ("AGUA-FILTRADA", "liquid")
    assert (levain.sku, levain.role) == ("LEVAIN", "other")
    assert any(
        candidate.has_recipe and candidate.recipe_version_ref == "creme-levain@1" for candidate in levain.candidates
    )
    assert (pepper.sku, pepper.quantity, pepper.match_confidence) == ("", "", "")

    assert draft.formula["anchor"] == {"kind": "flour"}
    assert draft.formula["standardized"] is False
    assert [
        (line["sku"], line["quantity"]["target"], line["quantity"]["unit"]) for line in draft.formula["ingredients"]
    ] == [
        ("FARINHA-NOVARA-T55", "1000", "g"),
        ("AGUA-FILTRADA", "700", "g"),
        ("LEVAIN", "200", "g"),
    ]


def test_capture_draft_without_flour_anchors_on_the_total():
    captured = CapturedRecipe(
        name="Ganache",
        kind="filling",
        language="pt",
        yield_quantity=None,
        yield_unit="g",
        items=(
            CapturedItem(
                name="Chocolate", original_text="Chocolate 200 g", quantity=Decimal("200"), unit="g", role="inclusion"
            ),
        ),
        steps=(),
        notes="",
        raw_text="{}",
    )
    draft = build_capture_draft(captured)
    assert draft.yield_quantity == ""
    assert draft.formula["anchor"] == {"kind": "total"}


# ── Acesso ───────────────────────────────────────────────────────────────────


def test_access_rule():
    from shopman.shop.models import Shop

    viewer = grant_production_operator(User.objects.create_user("viewer", password="pw", is_staff=True))
    editor = grant_production_operator(User.objects.create_user("editor", password="pw", is_staff=True))
    editor.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Shop),
            codename="manage_production",
        )
    )
    editor = User.objects.get(pk=editor.pk)
    sheet_reader = User.objects.create_user("sheet-reader", password="pw", is_staff=True)
    sheet_reader.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Recipe),
            codename="view_recipe",
        )
    )
    sheet_reader = User.objects.get(pk=sheet_reader.pk)
    bare = User.objects.create_user("bare", password="pw", is_staff=True)
    superuser = User.objects.create_superuser("root", "root@test.com", "pw")

    assert (resolve_recipe_book_access(viewer).can_view, resolve_recipe_book_access(viewer).can_edit) == (True, False)
    assert (resolve_recipe_book_access(editor).can_view, resolve_recipe_book_access(editor).can_edit) == (True, True)
    assert (resolve_recipe_book_access(sheet_reader).can_view, resolve_recipe_book_access(sheet_reader).can_edit) == (
        True,
        False,
    )
    assert (resolve_recipe_book_access(bare).can_view, resolve_recipe_book_access(bare).can_edit) == (False, False)
    assert resolve_recipe_book_access(superuser).can_edit is True
    assert resolve_recipe_book_access(AnonymousUser()).can_view is False
    assert resolve_recipe_book_access(viewer).capture_available is False


def test_a_cream_with_a_flour_anchor_is_not_a_bakery_lens():
    """Creme com muita farinha continua creme: sem métricas de padaria, mesmo com âncora de farinha."""
    formula = {
        "anchor": {"kind": "flour"},
        "ingredients": [
            _fixed("ingredient-flour", "FARINHA-ANACONDA-PREMIUM", "Farinha", "flour", 300),
            _fixed("ingredient-milk", "LEITE-INTEGRAL-A", "Leite", "liquid", 1000),
            _fixed("ingredient-sugar", "ACUCAR-CRISTAL", "Açúcar", "sugar", 250),
        ],
    }
    assert projections.build_formula_lens(formula, "bread").is_bakery is True
    lens = projections.build_formula_lens(formula, "cream")
    assert lens.is_bakery is False
    assert lens.anchor_kind == "flour"
    assert lens.ingredients[0].pct_display == "100%"


def test_sem_partes_a_mistura_final_e_a_ficha_sao_a_propria_base():
    """Três tabelas idênticas ensinam o padeiro a parar de ler: a tela pergunta antes de desenhar."""
    lens = build_formula_lens(flour_formula(), "bread")
    assert lens.final_mix_differs is False
    assert lens.bom_differs is False
    # O conteúdo continua servido: quem esconde o painel é a tela, com o motivo.
    assert [item.sku for item in lens.bom] == [item.sku for item in lens.ingredients]


def test_com_parte_pronta_as_duas_passam_a_dizer_outra_coisa(published_levain):
    lens = build_formula_lens(
        flour_formula(preps=[{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20}]),
        "bread",
    )
    assert lens.final_mix_differs is True
    assert lens.bom_differs is True
