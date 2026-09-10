"""Generate the recipe book contract mirror consumed by the production-nuxt surface.

The contract's single source of truth is the projection dataclasses in
``shopman.backstage.projections.recipe_book`` (RECIPE-INVENTORY-PLAN §7). The
Produção app imports (and narrows) the generated TypeScript module instead of
re-declaring the shapes by hand, and a drift test
(``test_recipe_book_schema_export``) regenerates the file in-memory and
compares it to disk. Run::

    python manage.py export_recipe_book_schema

after touching the projection dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shopman.backstage.contracts import render_contract_module, run_contract_export
from shopman.backstage.projections.recipe_book import (
    CaptureItemProjection,
    FormulaItemProjection,
    FormulaLensProjection,
    FormulaMetricProjection,
    FormulaPartProjection,
    FormulaWarningProjection,
    IngredientOptionProjection,
    KindOptionProjection,
    RecipeBookAccessProjection,
    RecipeBookListProjection,
    RecipeCaptureDraftProjection,
    RecipeCompareMetricProjection,
    RecipeCompareProjection,
    RecipeCompareRowProjection,
    RecipeEntryCardProjection,
    RecipeEntryDetailProjection,
    RecipeReferenceProjection,
    RecipeVersionProjection,
    ReferenceRangeProjection,
)

#: Generated artifact, relative to the repository root (``BASE_DIR``).
OUTPUT_RELATIVE_PATH = Path("surfaces/production-nuxt/app/generated/recipeBookContract.ts")

#: Every dataclass exported to the surface, dependencies first.
CONTRACT_DATACLASSES = (
    RecipeEntryCardProjection,
    KindOptionProjection,
    RecipeBookListProjection,
    RecipeBookAccessProjection,
    FormulaItemProjection,
    FormulaPartProjection,
    FormulaMetricProjection,
    FormulaWarningProjection,
    FormulaLensProjection,
    RecipeVersionProjection,
    RecipeEntryDetailProjection,
    RecipeCompareRowProjection,
    RecipeCompareMetricProjection,
    RecipeCompareProjection,
    ReferenceRangeProjection,
    RecipeReferenceProjection,
    IngredientOptionProjection,
    CaptureItemProjection,
    RecipeCaptureDraftProjection,
)


def output_path() -> Path:
    return Path(settings.BASE_DIR) / OUTPUT_RELATIVE_PATH


def render_recipe_book_contract_ts() -> str:
    """Render the generated TypeScript contract mirror (deterministic)."""
    return render_contract_module(
        source="shopman/backstage/projections/recipe_book.py",
        command="export_recipe_book_schema",
        dataclasses=CONTRACT_DATACLASSES,
    )


class Command(BaseCommand):
    help = "Generate the recipe book contract mirror (TypeScript) from the projections."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if the generated file is stale (do not write).",
        )

    def handle(self, *args, **options) -> None:
        run_contract_export(
            self,
            relative_path=OUTPUT_RELATIVE_PATH,
            rendered=render_recipe_book_contract_ts(),
            check=bool(options.get("check")),
        )
