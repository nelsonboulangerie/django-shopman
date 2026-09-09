from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.protocols.demand import DailyDemand


@pytest.fixture
def recipe(db):
    recipe = Recipe.objects.create(
        ref="pao-frances-v1",
        name="Pao Frances",
        output_sku="PAO-FRANCES",
        batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku="FARINHA",
        quantity=Decimal("5"),
        unit="kg",
    )
    return recipe


class FridayFactorProvider:
    def factors_for(self, *, date, output_sku, recipe, base_basis):
        return [
            {
                "ref": "weekday.friday",
                "kind": "multiplier",
                "value": "1.5",
                "reason": "sexta",
                "source": "test",
                "version": "1",
            }
        ]


def test_formula_suggest_builds_basis_without_formula_plan(recipe, settings):
    from shopman.craftsman.contrib.formula import suggest

    target = date.today() + timedelta(days=1)
    settings.CRAFTSMAN = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        "FORMULA_FACTOR_PROVIDERS": [
            "shopman.craftsman.tests.test_formula.FridayFactorProvider",
        ],
        "FORMULA_ROUNDING_MULTIPLE": "5",
    }
    history = [
        DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("20"), wasted=Decimal("0")),
        DailyDemand(date=date.today() - timedelta(days=14), sold=Decimal("20"), wasted=Decimal("0")),
    ]
    with (
        patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
            return_value=history,
        ),
        patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
            return_value=Decimal("0"),
        ),
    ):
        lines = suggest(target)

    assert len(lines) == 1
    assert lines[0].basis["recipe_ref"] == "pao-frances-v1"
    assert lines[0].basis["factors"][0]["ref"] == "weekday.friday"
    assert lines[0].basis["material_availability"]["status"] == "unknown"
    assert "FormulaPlan" not in {model.__name__ for model in Recipe._meta.apps.get_models()}


def test_accept_suggestion_routes_explicit_basis_through_canonical_facade(recipe):
    from shopman.craftsman.contrib.formula import accept_suggestion

    target = date.today() + timedelta(days=1)
    expected_order = craft.plan(recipe, 10, date=target, actor="test:setup")
    with patch(
        "shopman.shop.adapters.production.CanonicalProductionCommands.plan",
        return_value=(recipe.output_sku, expected_order.ref, Decimal("10"), "created"),
    ) as plan:
        order = accept_suggestion(
            recipe_ref=recipe.ref,
            target_date=target,
            actor="test:formula",
            basis={
                "recipe_ref": recipe.ref,
                "rounded_quantity": "10",
                "material_availability": {
                    "all_available": True,
                    "shortages": [],
                },
            },
            idempotency_key="formula-test",
        )

    assert order == expected_order
    call = plan.call_args.kwargs
    assert call["source_ref"] == "formula:suggestion"
    assert call["idempotency_key"] == "formula:formula-test"
    assert call["create_new"] is True
    assert call["planning_meta"]["formula_basis"]["recipe_ref"] == recipe.ref
    assert call["planning_meta"]["formula_basis"]["accepted_quantity"] == "10"
