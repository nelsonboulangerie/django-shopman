"""A matemática pura da fórmula unificada e da mistura final.

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
    reference_for,
    resolve_execution,
    scale,
    standardize,
    validate_formula,
)
from shopman.craftsman.exceptions import RecipeBookError

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
            ("", "FARINHA-ANACONDA-PREMIUM", "flour"),
            ("", "FARINHA-CENTEIO-INTEGRAL-ORGANICA", "flour"),
            ("", "FARINHA-INTEGRAL-ORGANICA", "flour"),
            ("Fubá", "", "flour"),
            ("Água filtrada", "", "liquid"),
            ("", "AGUA-FILTRADA", "liquid"),
            ("Water", "", "liquid"),
            ("Eau", "", "liquid"),
            ("水", "", "liquid"),
            ("Leite integral", "LEITE-INTEGRAL-A", "liquid"),
            ("牛乳", "", "liquid"),
            ("Creme de leite", "", "dairy"),
            ("Nata", "", "dairy"),
            ("Queijo minas", "", "dairy"),
            ("Fromage", "", "dairy"),
            ("Sal", "SAL-REFINADO", "salt"),
            ("Flor de sal", "", "salt"),
            ("塩", "", "salt"),
            ("Salsa", "", "other"),
            ("Fermento biológico", "FERMENTO-BIOLOGICO-FRESCO", "yeast"),
            ("Levure fraîche", "", "yeast"),
            ("Yeast", "", "yeast"),
            ("イースト", "", "yeast"),
            ("Manteiga", "MANTEIGA-PRESIDENT-SEM-SAL", "fat"),
            ("Beurre", "", "fat"),
            ("Azeite", "AZEITE-EXTRAVIRGEM", "fat"),
            ("Óleo", "", "fat"),
            ("バター", "", "fat"),
            ("Açúcar", "ACUCAR-CRISTAL", "sugar"),
            ("Mel", "", "sugar"),
            ("Malte", "MALTE-EXTRATO", "sugar"),
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
        assert looks_like_flour("", "FARINHA-CENTEIO-INTEGRAL-ORGANICA")
        assert not looks_like_flour("Leite integral", "LEITE-INTEGRAL-A")

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


# ── Fórmula unificada ────────────────────────────────────────────────────────


def fixed(value, unit="g", *, minimum=None, maximum=None):
    return {
        "kind": "fixed", "minimum": value if minimum is None else minimum,
        "target": value, "maximum": value if maximum is None else maximum, "unit": unit,
    }


def ratio(value, *, minimum=None, maximum=None, basis=None):
    return {
        "kind": "ratio", "minimum": value if minimum is None else minimum,
        "target": value, "maximum": value if maximum is None else maximum,
        "basis": basis or {"kind": "flour"},
    }


def ingredient(sku, name, role, quantity, **extra):
    ref = extra.pop("ref", sku.lower())
    return {"ref": ref, "sku": sku, "name": name, "role": role, "composition": "additional", "quantity": quantity, **extra}


LEVAIN = {
    "anchor": {"kind": "flour"},
    "ingredients": [
        ingredient("FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", fixed(500)),
        ingredient("AGUA-FILTRADA", "Água", "liquid", fixed(500)),
    ],
}
PASTA = {
    "anchor": {"kind": "flour"},
    "ingredients": [
        ingredient("FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", fixed(1000)),
        ingredient("AGUA-FILTRADA", "Água", "liquid", fixed(600)),
    ],
}
INGREDIENT_FORMULAS = {"levain@4": LEVAIN, "autolyse@2": PASTA}


def tradicao(extra=None, **overrides):
    formula = {
        "anchor": {"kind": "flour"}, "basis_g": 1000, "standardized": True,
        "ingredients": [
            ingredient("FARINHA-ANACONDA-PREMIUM", "Farinha T55", "flour", fixed(1000)),
            ingredient("AGUA-FILTRADA", "Água", "liquid", fixed(700)),
            ingredient("SAL-REFINADO", "Sal", "salt", fixed(20)),
            *(extra or []),
        ],
    }
    formula.update(overrides)
    return formula


def included(sku, name, version, quantity):
    return ingredient(sku, name, "other", quantity, recipe_version_ref=version, composition="included")


def by_sku(rows):
    return {row.sku: row for row in rows}


class TestAnalyze:
    def test_hydration_is_liquid_over_flour(self):
        analysis = analyze(tradicao())
        assert analysis.anchor_kind == "flour"
        assert analysis.anchor_total_g == Decimal("1000")
        assert analysis.total_mass_g == Decimal("1720")
        assert analysis.hydration_pct == Decimal("70")
        assert analysis.salt_pct == Decimal("2")
        assert by_sku(analysis.ingredients)["AGUA-FILTRADA"].pct == Decimal("70")

    def test_included_recipe_redistributes_the_global_formula(self):
        formula = tradicao([included("LEVAIN", "Levain", "levain@4", ratio(20))])
        analysis = analyze(formula, INGREDIENT_FORMULAS)
        bom = {line["sku"]: line for line in analysis.bom}
        assert bom["LEVAIN"]["quantity"] == Decimal("200")
        assert bom["FARINHA-ANACONDA-PREMIUM"]["quantity"] == Decimal("900")
        assert bom["AGUA-FILTRADA"]["quantity"] == Decimal("600")
        assert analysis.total_mass_g == Decimal("1720")

    def test_two_included_recipes_share_the_same_global_components(self):
        formula = tradicao([
            included("LEVAIN", "Levain", "levain@4", ratio(20)),
            included("PASTA-AUTOLIZADA", "Autólise", "autolyse@2", ratio(60)),
        ])
        analysis = analyze(formula, INGREDIENT_FORMULAS)
        final_mix = by_sku(analysis.final_mix)
        assert final_mix["FARINHA-ANACONDA-PREMIUM"].grams == Decimal("525")
        assert final_mix["AGUA-FILTRADA"].grams == Decimal("375")
        assert final_mix["SAL-REFINADO"].grams == Decimal("20")
        assert sum(line["quantity"] for line in analysis.bom) == Decimal("1720")

    def test_additional_recipe_increases_total_without_deducting_base(self):
        cream = ingredient("CREME", "Creme", "dairy", fixed(300),
                           recipe_version_ref="levain@4", composition="additional")
        analysis = analyze(tradicao([cream]), INGREDIENT_FORMULAS)
        bom = {line["sku"]: line for line in analysis.bom}
        assert bom["CREME"]["quantity"] == Decimal("300")
        assert bom["FARINHA-ANACONDA-PREMIUM"]["quantity"] == Decimal("1000")
        assert analysis.total_mass_g == Decimal("2020")

    def test_missing_frozen_version_is_explicit(self):
        formula = tradicao([included("LEVAIN", "Levain", "levain@99", ratio(20))])
        analysis = analyze(formula)
        assert [warning.code for warning in analysis.warnings] == ["INGREDIENT_RECIPE_NOT_FOUND"]
        assert by_sku(analysis.final_mix)["FARINHA-ANACONDA-PREMIUM"].grams == Decimal("1000")

    def test_included_composition_bigger_than_formula_is_flagged(self):
        huge = included("PASTA", "Pasta", "autolyse@2", fixed(3000))
        analysis = analyze(tradicao([huge]), INGREDIENT_FORMULAS)
        assert "INCLUDED_COMPOSITION_EXCEEDS_FORMULA" in [warning.code for warning in analysis.warnings]

    def test_actual_quantity_reacts_and_marks_authorized_deviation(self):
        formula = tradicao([included("LEVAIN", "Levain", "levain@4", ratio(20))])
        analysis = resolve_execution(formula, {"levain": 18}, INGREDIENT_FORMULAS)
        bom = {line["sku"]: line for line in analysis.bom}
        assert bom["LEVAIN"]["quantity"] == Decimal("180")
        assert bom["FARINHA-ANACONDA-PREMIUM"]["quantity"] == Decimal("910")
        assert bom["AGUA-FILTRADA"]["quantity"] == Decimal("610")
        assert analysis.deviations[0].within_bounds is False

    def test_maximum_uses_available_amount_below_target(self):
        old = included("MASSA-VELHA", "Massa velha", "tradicao@3",
                       ratio(20, minimum=0, maximum=20, basis={"kind": "total"}))
        analysis = resolve_execution(tradicao([old]), {"massa-velha": 12}, {"tradicao@3": tradicao()})
        assert analysis.deviations[0].within_bounds is True
        assert next(line for line in analysis.bom if line["sku"] == "MASSA-VELHA")["quantity"] == Decimal("206.4")

    def test_count_without_grams_per_unit_stays_out_with_warning(self):
        formula = tradicao([ingredient("OVOS", "Ovos", "egg", fixed(3, "un"))])
        analysis = analyze(formula)
        assert [warning.code for warning in analysis.warnings] == ["COUNT_WITHOUT_GRAMS_PER_UNIT"]
        assert by_sku(analysis.ingredients)["OVOS"].grams is None
        formula["ingredients"][-1]["grams_per_unit"] = 55
        assert analyze(formula).egg_pct == Decimal("16.5")

    def test_liquid_volume_without_density_assumes_water(self):
        formula = tradicao()
        formula["ingredients"][1] = ingredient("AGUA-FILTRADA", "Água", "liquid", fixed("0.7", "L"))
        analysis = analyze(formula)
        assert analysis.hydration_pct == Decimal("70")
        assert [warning.code for warning in analysis.warnings] == ["LIQUID_DENSITY_ASSUMED"]
        assert by_sku(analysis.final_mix)["AGUA-FILTRADA"].unit == "L"

    def test_without_flour_anchor_is_total_mass(self):
        ganache = {
            "anchor": {"kind": "total"},
            "ingredients": [
                ingredient("CHOCOLATE", "Chocolate", "inclusion", fixed(600)),
                ingredient("CREME", "Creme de leite", "dairy", fixed(400)),
            ],
        }
        analysis = analyze(ganache)
        assert analysis.anchor_total_g == Decimal("1000")
        assert by_sku(analysis.ingredients)["CHOCOLATE"].pct == Decimal("60")
        assert analysis.hydration_pct is None

    def test_derive_bom_matches_analysis(self):
        formula = tradicao([included("LEVAIN", "Levain", "levain@4", ratio(20))])
        assert derive_bom(formula, INGREDIENT_FORMULAS) == list(analyze(formula, INGREDIENT_FORMULAS).bom)


def bassinage(first=650, second=50, extra=None):
    formula = tradicao(extra)
    formula["ingredients"][1] = ingredient("AGUA-FILTRADA", "Água da massa", "liquid", fixed(first), ref="water-mix")
    formula["ingredients"].append(ingredient("AGUA-FILTRADA", "Água da bassinage", "liquid", fixed(second), ref="water-bassinage"))
    return formula


class TestOMesmoInsumoEmDuasLinhas:
    def test_each_line_keeps_its_own_grams(self):
        analysis = analyze(bassinage())
        assert [row.grams for row in analysis.final_mix if row.sku == "AGUA-FILTRADA"] == [Decimal("650"), Decimal("50")]
        assert [line["quantity"] for line in analysis.bom if line["sku"] == "AGUA-FILTRADA"] == [Decimal("650"), Decimal("50")]

    def test_included_recipe_takes_water_from_first_line(self):
        formula = bassinage(extra=[included("LEVAIN", "Levain", "levain@4", ratio(20))])
        analysis = analyze(formula, INGREDIENT_FORMULAS)
        assert [row.grams for row in analysis.final_mix if row.sku == "AGUA-FILTRADA"] == [Decimal("550"), Decimal("50")]

    def test_what_first_line_lacks_comes_from_next(self):
        formula = bassinage(first=50, second=650, extra=[included("LEVAIN", "Levain", "levain@4", ratio(20))])
        analysis = analyze(formula, INGREDIENT_FORMULAS)
        assert [row.grams for row in analysis.final_mix if row.sku == "AGUA-FILTRADA"] == [Decimal("0"), Decimal("600")]

    def test_each_line_comes_back_in_its_unit(self):
        formula = bassinage()
        formula["ingredients"][1]["quantity"] = fixed("0.65", "kg")
        rows = [(row.quantity, row.unit) for row in analyze(formula).final_mix if row.sku == "AGUA-FILTRADA"]
        assert rows == [(Decimal("0.65"), "kg"), (Decimal("50"), "g")]


class TestStandardize:
    def test_standardize_to_one_thousand_grams_of_flour(self):
        informed = tradicao(basis_g=None, standardized=False)
        for item in informed["ingredients"]:
            for key in ("minimum", "target", "maximum"):
                item["quantity"][key] = Decimal(item["quantity"][key]) * 5
        standard = standardize(informed)
        quantities = {item["sku"]: item["quantity"]["target"] for item in standard["ingredients"]}
        assert quantities == {"FARINHA-ANACONDA-PREMIUM": "1000", "AGUA-FILTRADA": "700", "SAL-REFINADO": "20"}
        assert standard["basis_g"] == "1000"
        assert standard["standardized"] is True
        assert informed["ingredients"][0]["quantity"]["target"] == Decimal("5000")

    def test_standardize_without_flour_refuses(self):
        formula = {"anchor": {"kind": "flour"}, "ingredients": [
            ingredient("AGUA", "Água", "liquid", fixed(1, "L"))]}
        with pytest.raises(RecipeBookError) as exc:
            standardize(formula)
        assert exc.value.code == "ANCHOR_EMPTY"

    def test_scale_changes_fixed_interval_and_keeps_ratio(self):
        levain = included("LEVAIN", "Levain", "levain@4", ratio(20, minimum=15, maximum=25))
        scaled = scale(tradicao([levain]), "2.5")
        assert scaled["ingredients"][0]["quantity"]["target"] == "2500"
        assert scaled["ingredients"][-1]["quantity"] == levain["quantity"]
        assert scaled["standardized"] is False
        assert scaled["basis_g"] is None


class TestReferences:
    def test_the_tradition_is_inside_the_book(self):
        assert check_references(analyze(tradicao()), "bread") == []

    def test_out_of_range_and_above_max_are_told_calmly(self):
        formula = tradicao()
        formula["ingredients"][1]["quantity"] = fixed(900)
        formula["ingredients"][2]["quantity"] = fixed(30)
        warnings = {warning.metric: warning for warning in check_references(analyze(formula), "bread")}
        assert warnings["hydration_pct"].code == "REFERENCE_OUT_OF_RANGE"
        assert warnings["hydration_pct"].high == REFERENCE_RANGES["hydration_pct"]["bread"]["high"]
        assert warnings["salt_pct"].code == "REFERENCE_ABOVE_MAX"

    def test_absent_ingredient_is_not_warning(self):
        analysis = analyze(tradicao())
        assert analysis.yeast_pct == Decimal("0")
        assert [warning.metric for warning in check_references(analysis, "bread")] == []

    def test_references_only_speak_with_flour_anchor(self):
        formula = tradicao()
        formula["anchor"] = {"kind": "total"}
        assert check_references(analyze(formula), "bread") == []

    def test_cookie_does_not_inherit_bread_ranges(self):
        formula = {"anchor": {"kind": "flour"}, "ingredients": [
            ingredient("FARINHA", "Farinha T45", "flour", fixed(500)),
            ingredient("MANTEIGA", "Manteiga", "fat", fixed(250)),
            ingredient("ACUCAR", "Açúcar", "sugar", fixed(200)),
            ingredient("OVOS", "Ovos", "egg", fixed(50)),
        ]}
        analysis = analyze(formula)
        assert reference_for("hydration_pct", "cookie") is None
        assert reference_for("salt_pct", "cookie") is None
        assert check_references(analysis, "cookie") == []


class TestValidateFormula:
    def test_good_formula_passes(self):
        validate_formula(tradicao([included("LEVAIN", "Levain", "levain@4", ratio(20))]))

    @pytest.mark.parametrize(("mutate", "field"), [
        (lambda f: f.pop("anchor"), "anchor"),
        (lambda f: f["anchor"].update(kind="mass"), "anchor.kind"),
        (lambda f: f.update(anchor={"kind": "ingredient"}), "anchor.sku"),
        (lambda f: f["ingredients"][0].update(role="cereal"), "ingredients[0].role"),
        (lambda f: f["ingredients"][1]["quantity"].update(target=0), "ingredients[1].quantity.target"),
        (lambda f: f["ingredients"][2]["quantity"].update(unit="saco"), "ingredients[2].quantity.unit"),
        (lambda f: f["ingredients"][0]["quantity"].update(minimum=1100), "ingredients[0].quantity.minimum"),
        (lambda f: f["ingredients"][0].update(composition="included"), "ingredients[0].composition"),
        (lambda f: f["ingredients"][1].update(ref="farinha-anaconda-premium"), "ingredients[1].ref"),
        (lambda f: f["ingredients"][0]["quantity"].update(
            kind="ratio", basis={"kind": "cereal"}), "ingredients[0].quantity.basis"),
    ])
    def test_offending_field_is_named(self, mutate, field):
        formula = tradicao()
        mutate(formula)
        with pytest.raises(RecipeBookError) as exc:
            validate_formula(formula)
        assert exc.value.code == "FORMULA_INVALID"
        assert exc.value.data["field"] == field

    def test_liter_spelling_is_accepted(self):
        formula = tradicao()
        formula["ingredients"][1]["quantity"] = fixed("0.7", "l")
        validate_formula(formula)


class TestOQualificadorNaoRoubaOPapel:
    """"Manteiga sem sal" é gordura, e "chocolate ao leite" é inclusão (não líquido).

    A curadoria dos insumos trocou `MANTEIGA-FR` por `MANTEIGA-PRESIDENT-SEM-SAL`
    em 24/09/2026, e a manteiga de 16 fichas passou a ser classificada como SAL —
    porque o classificador lia o último token e não sabia ler negação. O papel
    alimenta a lente de padaria, então o erro não era cosmético: ele entrava no
    percentual do padeiro.
    """

    @pytest.mark.parametrize(
        "nome,sku,papel",
        [
            ("Manteiga President sem sal", "MANTEIGA-PRESIDENT-SEM-SAL", "fat"),
            ("Manteiga extra sem sal", "MANTEIGA-EXTRA-SEM-SAL", "fat"),
            ("Beurre sans sel", "", "fat"),
            ("Unsalted butter", "", "fat"),
            # A negação não pode engolir o que ela não nega.
            ("Manteiga President com sal", "MANTEIGA-PRESIDENT-COM-SAL", "fat"),
            ("Sal refinado", "SAL-REFINADO", "salt"),
            ("Sal grosso", "SAL-GROSSO", "salt"),
            # O qualificador que vem depois não rouba o papel do substantivo.
            ("Gotas de chocolate ao leite", "CHOCOLATE-GOTAS-AOLEITE", "inclusion"),
            ("Farinha de centeio integral", "FARINHA-CENTEIO-INTEGRAL-ORGANICA", "flour"),
            # E a palavra curta não casa dentro de outra: `sal` em `salsinha`.
            ("Salsinha desidratada", "SALSINHA-DESIDRATADA", "other"),
        ],
    )
    def test_o_qualificador_nao_troca_o_papel(self, nome, sku, papel):
        assert classify_ingredient(nome, sku) == papel
