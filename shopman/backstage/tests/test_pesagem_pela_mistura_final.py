"""A pesagem do dia usa a BOM imediata congelada na ficha publicada."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.services import recipe_book

from shopman.backstage.projections.production import build_production_weighing

pytestmark = pytest.mark.django_db

LEVAIN_FORMULA = {
    "anchor": {"kind": "flour"},
    "ingredients": [
        {"ref": "levain-flour", "sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": {"kind": "fixed", "minimum": 500, "target": 500, "maximum": 500, "unit": "g"}, "composition": "additional"},
        {"ref": "levain-water", "sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": {"kind": "fixed", "minimum": 500, "target": 500, "maximum": 500, "unit": "g"}, "composition": "additional"},
    ],
}


def _formula():
    return {
        "anchor": {"kind": "flour"},
        "basis_g": 1000,
        "standardized": True,
        "ingredients": [
            {"ref": "dough-flour", "sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour", "quantity": {"kind": "fixed", "minimum": 1000, "target": 1000, "maximum": 1000, "unit": "g"}, "composition": "additional"},
            {"ref": "dough-water", "sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": {"kind": "fixed", "minimum": 700, "target": 700, "maximum": 700, "unit": "g"}, "composition": "additional"},
            {"ref": "dough-salt", "sku": "SAL-REFINADO", "name": "Sal", "role": "salt", "quantity": {"kind": "fixed", "minimum": 20, "target": 20, "maximum": 20, "unit": "g"}, "composition": "additional"},
            {"ref": "dough-levain", "sku": "LEVAIN-MF", "name": "Levain", "role": "other", "recipe_version_ref": "levain-mf@1", "composition": "included", "quantity": {"kind": "ratio", "minimum": 20, "target": 20, "maximum": 20, "basis": {"kind": "flour"}}},
        ],
    }


def _publicar_levain():
    levain = recipe_book.create_entry(ref="levain-mf", name="Levain", kind="bread", output_sku="LEVAIN-MF")
    version = recipe_book.create_version(levain, formula=LEVAIN_FORMULA, yield_quantity=1000, yield_unit="g")
    recipe_book.publish_version(version)


def _publicar_massa():
    entry = recipe_book.create_entry(ref="massa-mf", name="Massa MF", kind="bread", output_sku="MASSA-MF")
    formula = _formula()
    version = recipe_book.create_version(entry, formula=formula, yield_quantity="1720", yield_unit="g")
    recipe = recipe_book.publish_version(version)
    return recipe, formula


def _ticket(recipe):
    pesagem = build_production_weighing(selected_date=date.today())
    return next(t for t in pesagem.tickets if t.recipe_ref == recipe.ref)


def test_a_pesagem_usa_a_bom_unificada_da_versao_publicada():
    _publicar_levain()
    recipe, _ = _publicar_massa()
    craft.plan(recipe, Decimal("1720"), date=date.today())

    ticket = _ticket(recipe)
    pesos = {ing.sku: Decimal(ing.theoretical_g) for ing in ticket.ingredients}
    assert pesos == {
        "FARINHA-T55": Decimal("900"),
        "AGUA-FILTRADA": Decimal("600"),
        "SAL-REFINADO": Decimal("20"),
        "LEVAIN-MF": Decimal("200"),
    }
    assert next(i for i in ticket.ingredients if i.sku == "LEVAIN-MF").is_subrecipe
    assert not hasattr(ticket, "old_dough")
    assert ticket.output_quantity_display == "1720 g"
    # O ingrediente com receita continua com o ticket dele, na quantidade que a massa pede.
    pesagem = build_production_weighing(selected_date=date.today())
    levain = next(t for t in pesagem.tickets if t.recipe_ref == "levain-mf")
    assert {i.sku: Decimal(i.theoretical_g) for i in levain.ingredients} == {
        "FARINHA-T55": Decimal("100"),
        "AGUA-FILTRADA": Decimal("100"),
    }
