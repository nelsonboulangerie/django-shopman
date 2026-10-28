"""A pesagem do dia é a mistura final, inclusive com massa velha no teto.

RECIPE-MODELING-BRIEF §0, item 2: a lista de pesagem lia ficha × coeficiente, e
``final_mix``/``final_mix_at_cap`` só existiam na lente do inventário.

Medido em 19/10/2026: a ficha publicada JÁ é a mistura final + as preps prontas
(``_bom_items``), então a pesagem sem massa velha bate com ``final_mix`` por
construção, e o primeiro teste trava isso. O que não chegava era a massa velha:
ela é linha opcional (fora do consumo), a pesagem a descartava, e o padeiro que
usava a sobra da véspera pesava a fórmula inteira de novo. O segundo teste trava
a variante no teto, com a mesma conta de ``final_mix_at_cap``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.contrib.formula.percentages import analyze
from shopman.craftsman.services import recipe_book

from shopman.backstage.projections.production import build_production_weighing

pytestmark = pytest.mark.django_db

LEVAIN_FORMULA = {
    "anchor": {"kind": "flour"},
    "items": [
        {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 500, "unit": "g"},
        {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 500, "unit": "g"},
    ],
    "preps": [],
}


def _formula(preps):
    return {
        "anchor": {"kind": "flour"},
        "basis_g": 1000,
        "standardized": True,
        "items": [
            {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": 1000, "unit": "g"},
            {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 700, "unit": "g"},
            {"sku": "SAL-REFINADO", "name": "Sal", "role": "salt", "quantity": 20, "unit": "g"},
        ],
        "preps": preps,
    }


def _publicar_levain():
    levain = recipe_book.create_entry(ref="levain-mf", name="Levain", kind="bread", output_sku="LEVAIN-MF")
    version = recipe_book.create_version(levain, formula=LEVAIN_FORMULA, yield_quantity=1000, yield_unit="g")
    recipe_book.publish_version(version)


def _publicar_massa(preps):
    entry = recipe_book.create_entry(ref="massa-mf", name="Massa MF", kind="bread", output_sku="MASSA-MF")
    formula = _formula(preps)
    version = recipe_book.create_version(entry, formula=formula, yield_quantity="1720", yield_unit="g")
    recipe = recipe_book.publish_version(version)
    return recipe, formula


def _ticket(recipe):
    pesagem = build_production_weighing(selected_date=date.today())
    return next(t for t in pesagem.tickets if t.recipe_ref == recipe.ref)


def _gramas(texto: str) -> Decimal:
    numero, unidade = texto.replace(".", "").replace(",", ".").split()
    return Decimal(numero) * (Decimal("1000") if unidade == "kg" else Decimal("1"))


def test_sem_massa_velha_a_pesagem_e_a_mistura_final_mais_as_partes():
    _publicar_levain()
    recipe, formula = _publicar_massa(
        [{"sku": "LEVAIN-MF", "entry_ref": "levain-mf", "kind": "preferment", "flour_pct": 20}]
    )
    craft.plan(recipe, Decimal("1720"), date=date.today())

    ticket = _ticket(recipe)
    analysis = analyze(formula, recipe_book.prep_formulas_for(formula))
    final_mix = {item.sku: item.grams for item in analysis.final_mix}

    pesos = {ing.sku: Decimal(ing.theoretical_g) for ing in ticket.ingredients}
    # A farinha do levain sai da mistura final: 1000 − 200 = 800 g, nunca 1000.
    assert pesos["FARINHA-T55"] == final_mix["FARINHA-T55"] == Decimal("800")
    assert pesos["AGUA-FILTRADA"] == final_mix["AGUA-FILTRADA"] == Decimal("500")
    assert pesos["SAL-REFINADO"] == final_mix["SAL-REFINADO"]
    # A prep pronta entra inteira, como linha de preparo.
    assert pesos["LEVAIN-MF"] == Decimal("400")
    assert next(i for i in ticket.ingredients if i.sku == "LEVAIN-MF").is_subrecipe
    assert ticket.old_dough is None
    assert ticket.output_quantity_display == "1720 g"
    # O preparo da prep continua com o ticket dele, na quantidade que a massa pede.
    pesagem = build_production_weighing(selected_date=date.today())
    levain = next(t for t in pesagem.tickets if t.recipe_ref == "levain-mf")
    assert {i.sku: Decimal(i.theoretical_g) for i in levain.ingredients} == {
        "FARINHA-T55": Decimal("200"),
        "AGUA-FILTRADA": Decimal("200"),
    }


def test_com_massa_velha_a_pesagem_traz_a_mistura_final_no_teto():
    recipe, formula = _publicar_massa([{"kind": "old_dough", "cap_pct": 20}])
    craft.plan(recipe, Decimal("1720"), date=date.today())

    ticket = _ticket(recipe)
    analysis = analyze(formula)
    at_cap = {item.sku: item.grams for item in analysis.final_mix_at_cap}

    assert ticket.old_dough is not None
    assert ticket.old_dough.cap_pct == "20"
    assert ticket.old_dough.cap_display == "20%"
    no_teto = {line.sku: Decimal(line.target_g) for line in ticket.old_dough.lines}
    # Tudo encolhe por (1 − 20%): é a mesma conta do inventário, na balança.
    assert no_teto["FARINHA-T55"] == at_cap["FARINHA-T55"] == Decimal("800")
    assert no_teto["AGUA-FILTRADA"] == at_cap["AGUA-FILTRADA"] == Decimal("560")
    assert no_teto["SAL-REFINADO"] == at_cap["SAL-REFINADO"] == Decimal("16")
    # A massa velha cobre o que saiu: 20% de 1720 g, e o peso total não muda.
    assert Decimal(ticket.old_dough.old_dough_g) == Decimal("344")
    assert _gramas(ticket.old_dough.old_dough_display) == Decimal("344")
    # A pesagem sem massa velha continua sendo a fórmula inteira.
    sem = {ing.sku: Decimal(ing.theoretical_g) for ing in ticket.ingredients}
    assert sem["FARINHA-T55"] == Decimal("1000")
    assert "MASSA-MF" not in sem


def test_massa_velha_reduz_tambem_as_preparacoes_sem_mudar_a_formula_global():
    _publicar_levain()
    recipe, _ = _publicar_massa([
        {"sku": "LEVAIN-MF", "entry_ref": "levain-mf", "kind": "preferment", "flour_pct": 20},
        {"kind": "old_dough", "cap_pct": 20},
    ])
    craft.plan(recipe, Decimal("1720"), date=date.today())

    ticket = _ticket(recipe)
    assert ticket.old_dough is not None
    no_teto = {line.sku: Decimal(line.target_g) for line in ticket.old_dough.lines}

    # A fórmula global continua 1000 g de farinha, 700 g de água e 20 g de sal.
    # A massa velha fornece 20% dela; por isso TODO o BOM novo, inclusive o
    # levain, cai para 80%. Não se recalculam nem se reescrevem os ingredientes.
    assert no_teto == {
        "FARINHA-T55": Decimal("640"),
        "AGUA-FILTRADA": Decimal("400"),
        "SAL-REFINADO": Decimal("16"),
        "LEVAIN-MF": Decimal("320"),
    }
    assert Decimal(ticket.old_dough.old_dough_g) == Decimal("344")
    assert sum(no_teto.values(), Decimal("0")) + Decimal(ticket.old_dough.old_dough_g) == Decimal("1720")


def test_teto_fora_de_zero_a_cem_nao_vira_variante():
    recipe, _ = _publicar_massa([{"kind": "old_dough", "cap_pct": 20}])
    linha = recipe.items.get(is_optional=True)
    linha.meta = {**linha.meta, "cap_pct": "100"}
    linha.save(update_fields=["meta"])
    craft.plan(recipe, Decimal("1720"), date=date.today())

    assert _ticket(recipe).old_dough is None
