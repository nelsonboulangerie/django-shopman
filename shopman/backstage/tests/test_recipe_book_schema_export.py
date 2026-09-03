"""Drift guard for the generated recipe book contract mirror.

The Produção surface (production-nuxt) imports the recipe book projection
shapes from a generated TypeScript module whose single source of truth is
``shopman.backstage.projections.recipe_book``. If a dataclass changes without
regenerating, this test fails with the fix command, so the hand-written mirror
the surface started with cannot creep back via staleness.
"""

from __future__ import annotations

from shopman.backstage.management.commands.export_recipe_book_schema import (
    CONTRACT_DATACLASSES,
    output_path,
    render_recipe_book_contract_ts,
)


def test_generated_recipe_book_contract_is_not_stale() -> None:
    path = output_path()
    assert path.exists(), (
        f"{path} missing — run: python manage.py export_recipe_book_schema"
    )
    assert path.read_text(encoding="utf-8") == render_recipe_book_contract_ts(), (
        "Recipe book contract mirror is stale — run: python manage.py export_recipe_book_schema"
    )


def test_render_is_deterministic() -> None:
    assert render_recipe_book_contract_ts() == render_recipe_book_contract_ts()


def test_render_reflects_contract_source() -> None:
    from dataclasses import fields

    from shopman.backstage.projections.recipe_book import FormulaLensProjection

    rendered = render_recipe_book_contract_ts()
    assert "export interface FormulaLensProjection {" in rendered
    for field in fields(FormulaLensProjection):
        assert f"  {field.name}:" in rendered


def test_every_projection_of_the_plan_is_exported() -> None:
    """§7 lists nineteen shapes; the surface narrows every one of them."""
    names = {dc.__name__ for dc in CONTRACT_DATACLASSES}
    assert names == {
        "RecipeEntryCardProjection",
        "KindOptionProjection",
        "RecipeBookListProjection",
        "RecipeBookAccessProjection",
        "FormulaItemProjection",
        "FormulaPartProjection",
        "FormulaMetricProjection",
        "FormulaWarningProjection",
        "FormulaLensProjection",
        "RecipeVersionProjection",
        "RecipeEntryDetailProjection",
        "RecipeCompareRowProjection",
        "RecipeCompareMetricProjection",
        "RecipeCompareProjection",
        "ReferenceRangeProjection",
        "RecipeReferenceProjection",
        "IngredientOptionProjection",
        "CaptureItemProjection",
        "RecipeCaptureDraftProjection",
    }
