"""A matemática pura da fórmula: porcentagem do padeiro, partes e mistura final.

Sem banco: ``contrib/formula/percentages.py`` recebe a fórmula (§3 do plano) e
responde só com ``Decimal``. O exemplo que atravessa a suíte é a Tradição do
handoff: 1000 g de farinha, 70% de água, 2% de sal, pasta autolisada
(1000/600) com 60% da farinha e levain 50/50 com 20%.
"""

from decimal import Decimal

import pytest
from shopman.craftsman.contrib.formula.percentages import (
    REFERENCE_RANGES,
    analyze,
    check_references,
    classify_ingredient,
    derive_bom,
    item_grams,
    looks_like_flour,
    scale,
    standardize,
    validate_formula,
)
from shopman.craftsman.exceptions import RecipeBookError

LEVAIN = {
    "anchor": {"kind": "flour"},
    "items": [
        {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 500, "unit": "g"},
        {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 500, "unit": "g"},
    ],
}
PASTA = {
    "anchor": {"kind": "flour"},
    "items": [
        {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 1000, "unit": "g"},
        {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 600, "unit": "g"},
    ],
}
PART_FORMULAS = {"LEVAIN": LEVAIN, "PASTA-AUTOLIZADA": PASTA}


def tradicao(parts=None, **overrides):
    """A base da Tradição em 1000 g de farinha; as partes vêm de fora."""
    formula = {
        "anchor": {"kind": "flour"},
        "basis_g": 1000,
        "standardized": True,
        "items": [
            {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 1000, "unit": "g"},
            {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 700, "unit": "g"},
            {"sku": "SAL", "name": "Sal", "role": "salt", "quantity": 20, "unit": "g"},
        ],
        "parts": parts or [],
    }
    formula.update(overrides)
    return formula


def by_sku(rows):
    return {row.sku: row for row in rows}


# ── Papel do ingrediente ─────────────────────────────────────────────────────


class TestClassifyIngredient:
    @pytest.mark.parametrize(
        ("name", "sku", "role"),
        [
            ("Farinha de trigo", "", "flour"),
            ("Farinha de castanha", "", "flour"),
            ("Trigo integral", "", "flour"),
            ("Flour", "", "flour"),
            ("Farine T65", "", "flour"),
            ("強力粉", "", "flour"),
            ("ライ麦", "", "flour"),
            ("", "FARINHA-T55", "flour"),
            ("", "CENTEIO", "flour"),
            ("", "FARINHA-INT", "flour"),
            ("Fubá", "", "flour"),
            ("Água filtrada", "", "liquid"),
            ("", "AGUA-FILTRADA", "liquid"),
            ("Water", "", "liquid"),
            ("Eau", "", "liquid"),
            ("水", "", "liquid"),
            ("Leite integral", "LEITE", "liquid"),
            ("牛乳", "", "liquid"),
            ("Creme de leite", "", "dairy"),
            ("Nata", "", "dairy"),
            ("Queijo minas", "", "dairy"),
            ("Fromage", "", "dairy"),
            ("Sal", "SAL", "salt"),
            ("Flor de sal", "", "salt"),
            ("塩", "", "salt"),
            ("Salsa", "", "other"),
            ("Fermento biológico", "FERMENTO-BIO", "yeast"),
            ("Levure fraîche", "", "yeast"),
            ("Yeast", "", "yeast"),
            ("イースト", "", "yeast"),
            ("Manteiga", "MANTEIGA-FR", "fat"),
            ("Beurre", "", "fat"),
            ("Azeite", "AZEITE", "fat"),
            ("Óleo", "", "fat"),
            ("バター", "", "fat"),
            ("Açúcar", "ACUCAR", "sugar"),
            ("Mel", "", "sugar"),
            ("Malte", "MALTE", "sugar"),
            ("砂糖", "", "sugar"),
            ("Ovos", "OVOS", "egg"),
            ("Œufs", "", "egg"),
            ("卵", "", "egg"),
            ("Gotas de chocolate", "", "inclusion"),
            ("Uva passa", "", "inclusion"),
            ("Azeitona preta", "", "inclusion"),
            ("Gergelim", "", "inclusion"),
            ("Sementes de girassol", "", "inclusion"),
            ("Canela", "", "other"),
        ],
    )
    def test_role_by_name_and_sku_in_four_languages(self, name, sku, role):
        assert classify_ingredient(name, sku) == role

    def test_case_and_accents_do_not_matter(self):
        assert classify_ingredient("FARINHA DE TRIGO") == "flour"
        assert classify_ingredient("AÇÚCAR") == "sugar"

    def test_looks_like_flour_is_the_same_question(self):
        assert looks_like_flour("Farinha T55")
        assert looks_like_flour("", "CENTEIO")
        assert not looks_like_flour("Leite integral", "LEITE")


# ── Física do item ───────────────────────────────────────────────────────────


class TestItemGrams:
    def test_mass_converts_by_definition(self):
        assert item_grams({"quantity": "1.5", "unit": "kg"}) == Decimal("1500")
        assert item_grams({"quantity": 200, "unit": "g"}) == Decimal("200")

    def test_volume_needs_density_unless_it_is_a_liquid(self):
        assert item_grams({"quantity": 1, "unit": "L", "density_g_per_ml": "0.91"}) == Decimal("910")
        assert item_grams({"quantity": 1, "unit": "L", "role": "liquid"}) == Decimal("1000")
        assert item_grams({"quantity": 1, "unit": "L", "role": "fat"}) is None

    def test_count_only_enters_with_grams_per_unit(self):
        assert item_grams({"quantity": 3, "unit": "un", "grams_per_unit": 55}) == Decimal("165")
        assert item_grams({"quantity": 3, "unit": "un"}) is None


# ── Análise ──────────────────────────────────────────────────────────────────


class TestAnalyze:
    def test_hydration_is_liquid_over_flour(self):
        analysis = analyze(tradicao())
        assert analysis.anchor_kind == "flour"
        assert analysis.anchor_total_g == Decimal("1000")
        assert analysis.total_mass_g == Decimal("1720")
        assert analysis.hydration_pct == Decimal("70")
        assert analysis.salt_pct == Decimal("2")
        assert by_sku(analysis.items)["AGUA-FILTRADA"].pct == Decimal("70")

    def test_levain_at_twenty_percent_is_four_hundred_grams(self):
        """Levain 50/50 com 20% da farinha: 200 g de farinha ÷ 0,5 = 400 g de levain."""
        analysis = analyze(
            tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20}]),
            PART_FORMULAS,
        )
        levain = analysis.parts[0]
        assert levain.quantity_g == Decimal("400")
        assert levain.flour_g == Decimal("200")
        assert levain.flour_pct == Decimal("20")
        assert analysis.prefermented_flour_pct == Decimal("20")

    def test_a_quantity_that_says_the_same_as_the_percentage_wins_exactly(self):
        """flour_pct tem 3 casas; a quantidade declarada é a mesma declaração com mais casas."""
        same = analyze(
            tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20, "quantity": "400.02", "unit": "g"}]),
            PART_FORMULAS,
        )
        assert same.parts[0].quantity_g == Decimal("400.02")

        edited = analyze(
            tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20, "quantity": 500, "unit": "g"}]),
            PART_FORMULAS,
        )
        assert edited.parts[0].quantity_g == Decimal("400")

    def test_final_mix_and_bom_of_the_tradition(self):
        """Base − partes = o que falta pôr na masseira; BOM = mistura final + partes prontas."""
        analysis = analyze(
            tradicao(parts=[
                {"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20},
                {"sku": "PASTA-AUTOLIZADA", "kind": "autolyse", "flour_pct": 60},
            ]),
            PART_FORMULAS,
        )
        pasta = analysis.parts[1]
        assert pasta.quantity_g == Decimal("960")  # 600 g de farinha + 360 g de água

        final_mix = by_sku(analysis.final_mix)
        assert final_mix["FARINHA-T55"].grams == Decimal("200")  # 1000 − 200 − 600
        assert final_mix["AGUA-FILTRADA"].grams == Decimal("140")  # 700 − 200 − 360
        assert final_mix["SAL"].grams == Decimal("20")

        bom = {line["sku"]: line for line in analysis.bom}
        assert bom["FARINHA-T55"]["quantity"] == Decimal("200")
        assert bom["AGUA-FILTRADA"]["quantity"] == Decimal("140")
        assert bom["LEVAIN"]["quantity"] == Decimal("400")
        assert bom["PASTA-AUTOLIZADA"]["quantity"] == Decimal("960")
        # A farinha não sai duas vezes: o BOM pesa o mesmo que a base.
        assert sum(line["quantity"] for line in analysis.bom) == Decimal("1720")
        # Autólise não é fermentação: só o levain conta como farinha pré-fermentada.
        assert analysis.prefermented_flour_pct == Decimal("20")
        assert analysis.warnings == ()

    def test_old_dough_shrinks_everything_by_one_minus_cap(self):
        analysis = analyze(
            tradicao(parts=[
                {"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20},
                {"kind": "old_dough", "cap_pct": 20},
            ]),
            PART_FORMULAS,
        )
        assert analysis.old_dough_cap_pct == Decimal("20")
        nominal = by_sku(analysis.final_mix)
        at_cap = by_sku(analysis.final_mix_at_cap)
        assert nominal["FARINHA-T55"].grams == Decimal("800")
        assert at_cap["FARINHA-T55"].grams == Decimal("640")
        assert at_cap["AGUA-FILTRADA"].grams == Decimal("400")  # 500 × 0,8
        assert at_cap["SAL"].grams == Decimal("16")

        old_dough = [line for line in analysis.bom if line["meta"].get("role") == "old_dough"]
        assert len(old_dough) == 1
        assert old_dough[0]["is_optional"] is True
        assert old_dough[0]["meta"]["cap_pct"] == "20"
        assert old_dough[0]["quantity"] == Decimal("344")  # 20% da massa total (1720 g)
        # Fora do consumo: os não opcionais continuam somando a base inteira.
        assert sum(line["quantity"] for line in analysis.bom if not line["is_optional"]) == Decimal("1720")

    def test_part_without_formula_stays_in_the_base(self):
        analysis = analyze(tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20}]))
        assert [w.code for w in analysis.warnings] == ["PART_WITHOUT_FORMULA"]
        assert analysis.parts[0].has_formula is False
        assert by_sku(analysis.final_mix)["FARINHA-T55"].grams == Decimal("1000")
        assert "LEVAIN" not in {line["sku"] for line in analysis.bom}

    def test_part_bigger_than_the_base_is_flagged_and_zeroed(self):
        analysis = analyze(
            tradicao(parts=[{"sku": "PASTA-AUTOLIZADA", "kind": "autolyse", "quantity": 2000, "unit": "g"}]),
            {"PASTA-AUTOLIZADA": {**PASTA, "items": [
                *PASTA["items"],
                {"sku": "MEL", "name": "Mel", "role": "sugar", "quantity": 10, "unit": "g"},
            ]}},
        )
        codes = [w.code for w in analysis.warnings]
        assert "PART_EXCEEDS_BASE" in codes
        assert by_sku(analysis.final_mix)["FARINHA-T55"].grams == Decimal("0")
        assert "FARINHA-T55" not in {line["sku"] for line in analysis.bom}

    def test_count_without_grams_per_unit_stays_out_with_a_warning(self):
        formula = tradicao()
        formula["items"].append({"sku": "OVOS", "name": "Ovos", "role": "egg", "quantity": 3, "unit": "un"})
        analysis = analyze(formula)
        assert [w.code for w in analysis.warnings] == ["COUNT_WITHOUT_GRAMS_PER_UNIT"]
        assert by_sku(analysis.items)["OVOS"].grams is None
        assert analysis.total_mass_g == Decimal("1720")
        assert analysis.egg_pct == Decimal("0")

        formula["items"][-1]["grams_per_unit"] = 55
        analysis = analyze(formula)
        assert analysis.warnings == ()
        assert analysis.egg_pct == Decimal("16.5")

    def test_liquid_volume_without_density_assumes_water(self):
        formula = tradicao()
        formula["items"][1] = {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": "0.7", "unit": "L"}
        analysis = analyze(formula)
        assert analysis.hydration_pct == Decimal("70")
        assert [w.code for w in analysis.warnings] == ["LIQUID_DENSITY_ASSUMED"]
        # A mistura final volta na unidade em que o item foi escrito.
        assert by_sku(analysis.final_mix)["AGUA-FILTRADA"].unit == "L"
        assert by_sku(analysis.final_mix)["AGUA-FILTRADA"].quantity == Decimal("0.7")

    def test_without_flour_the_anchor_is_the_total_mass(self):
        ganache = {
            "anchor": {"kind": "total"},
            "items": [
                {"sku": "CHOCOLATE", "name": "Chocolate", "quantity": 600, "unit": "g"},
                {"sku": "CREME", "name": "Creme de leite", "quantity": 400, "unit": "g"},
            ],
        }
        analysis = analyze(ganache)
        assert analysis.anchor_total_g == Decimal("1000")
        assert by_sku(analysis.items)["CHOCOLATE"].pct == Decimal("60")
        assert by_sku(analysis.items)["CHOCOLATE"].role == "inclusion"
        assert analysis.hydration_pct is None
        assert analysis.salt_pct is None

    def test_derive_bom_is_the_bom_of_the_analysis(self):
        formula = tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20}])
        assert derive_bom(formula, PART_FORMULAS) == list(analyze(formula, PART_FORMULAS).bom)


# ── Padronizar e escalar ─────────────────────────────────────────────────────


class TestStandardize:
    def test_standardize_to_one_thousand_grams_of_flour(self):
        informed = tradicao(basis_g=None, standardized=False)
        for item in informed["items"]:
            item["quantity"] = Decimal(item["quantity"]) * 5
        informed["parts"] = [{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20, "quantity": 2000, "unit": "g"}]

        standard = standardize(informed)
        quantities = {item["sku"]: item["quantity"] for item in standard["items"]}
        assert quantities == {"FARINHA-T55": "1000", "AGUA-FILTRADA": "700", "SAL": "20"}
        assert standard["basis_g"] == "1000"
        assert standard["standardized"] is True
        assert standard["parts"][0]["quantity"] == "400"
        assert standard["parts"][0]["flour_pct"] == 20
        # A informada não foi tocada.
        assert informed["items"][0]["quantity"] == Decimal("5000")

    def test_standardize_without_flour_refuses(self):
        with pytest.raises(RecipeBookError) as exc:
            standardize({"anchor": {"kind": "flour"}, "items": [{"sku": "AGUA", "name": "Água", "quantity": 1, "unit": "L"}]})
        assert exc.value.code == "ANCHOR_EMPTY"

    def test_scale_keeps_percentages_and_drops_the_basis(self):
        scaled = scale(tradicao(), "2.5")
        assert {item["sku"]: item["quantity"] for item in scaled["items"]} == {
            "FARINHA-T55": "2500", "AGUA-FILTRADA": "1750", "SAL": "50",
        }
        assert scaled["standardized"] is False
        assert scaled["basis_g"] is None


# ── Referências ──────────────────────────────────────────────────────────────


class TestReferences:
    def test_the_tradition_is_inside_the_book(self):
        analysis = analyze(
            tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20}]),
            PART_FORMULAS,
        )
        assert check_references(analysis, "bread") == []

    def test_out_of_range_and_above_max_are_told_calmly(self):
        formula = tradicao(parts=[{"sku": "LEVAIN", "kind": "preferment", "flour_pct": 35}])
        formula["items"][1]["quantity"] = 900  # 90% de hidratação
        formula["items"][2]["quantity"] = 30  # 3% de sal
        warnings = {w.metric: w for w in check_references(analyze(formula, PART_FORMULAS), "bread")}
        assert warnings["hydration_pct"].code == "REFERENCE_OUT_OF_RANGE"
        assert warnings["hydration_pct"].value == Decimal("90")
        assert warnings["hydration_pct"].high == REFERENCE_RANGES["hydration_pct"]["bread"]["high"]
        assert warnings["salt_pct"].code == "REFERENCE_ABOVE_MAX"
        assert warnings["part_flour_pct"].code == "REFERENCE_OUT_OF_RANGE"  # levain 15 a 30
        assert "fora da faixa" in warnings["hydration_pct"].message

    def test_absent_ingredient_is_not_a_warning(self):
        """Pão de levain não leva fermento; massa magra não leva açúcar."""
        analysis = analyze(tradicao())
        assert analysis.yeast_pct == Decimal("0")
        assert [w.metric for w in check_references(analysis, "bread")] == []

    def test_references_only_speak_with_the_flour_anchor(self):
        analysis = analyze({"anchor": {"kind": "total"}, "items": tradicao()["items"]})
        assert check_references(analysis, "bread") == []


# ── Schema ───────────────────────────────────────────────────────────────────


class TestValidateFormula:
    def test_a_good_formula_passes(self):
        validate_formula(tradicao(parts=[
            {"sku": "LEVAIN", "kind": "preferment", "flour_pct": 20},
            {"kind": "old_dough", "cap_pct": 20},
        ]))

    @pytest.mark.parametrize(
        ("mutate", "field"),
        [
            (lambda f: f.pop("anchor"), "anchor"),
            (lambda f: f["anchor"].update(kind="mass"), "anchor.kind"),
            (lambda f: f.update(anchor={"kind": "ingredient"}), "anchor.sku"),
            (lambda f: f["items"][0].update(role="cereal"), "items[0].role"),
            (lambda f: f["items"][1].update(quantity=0), "items[1].quantity"),
            (lambda f: f["items"][2].update(unit="saco"), "items[2].unit"),
            (lambda f: f["items"].append({"sku": "", "name": "", "quantity": 1, "unit": "g"}), "items[3].name"),
            (lambda f: f.update(parts=[{"kind": "sponge", "sku": "X"}]), "parts[0].kind"),
            (lambda f: f.update(parts=[{"kind": "preferment", "sku": "X"}]), "parts[0].flour_pct"),
            (lambda f: f.update(parts=[{"kind": "preferment", "sku": "X", "flour_pct": 120}]), "parts[0].flour_pct"),
            (lambda f: f.update(parts=[{"kind": "old_dough", "cap_pct": 100}]), "parts[0].cap_pct"),
            (lambda f: f.update(parts=[{"kind": "preferment", "sku": "X", "quantity": 1, "unit": "L"}]), "parts[0].unit"),
        ],
    )
    def test_the_field_that_offends_is_named(self, mutate, field):
        formula = tradicao()
        mutate(formula)
        with pytest.raises(RecipeBookError) as exc:
            validate_formula(formula)
        assert exc.value.code == "FORMULA_INVALID"
        assert exc.value.data["field"] == field

    def test_liter_spelling_is_accepted(self):
        formula = tradicao()
        formula["items"][1].update(unit="l", quantity="0.7")
        validate_formula(formula)
