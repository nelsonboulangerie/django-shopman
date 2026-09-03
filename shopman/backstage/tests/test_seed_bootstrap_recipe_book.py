"""O seed liga o inventário de receitas às fichas que ele mesmo semeia.

``_seed_recipes`` grava as fichas e, logo depois, chama ``bootstrap_recipe_book``:
cada ficha ativa com unidade de saída declarada vira uma entry com a versão 1
publicada. Aqui se prova o gancho de dois jeitos: sobre fichas criadas na hora,
com a mesma cara das do seed (rápido), e sobre o seed inteiro (a corda entre o
comando e o dado real).
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeItem, RecipeVersion

from shopman.backstage.projections.recipe_book import build_recipe_book, build_recipe_entry

pytestmark = pytest.mark.django_db


def _sheet(ref, name, output_sku, batch, items, *, unit="kg", steps=()):
    recipe = Recipe.objects.create(
        ref=ref, name=name, output_sku=output_sku, batch_size=Decimal(batch),
        steps=list(steps), meta={"output_unit": unit},
    )
    for order, (sku, quantity) in enumerate(items):
        RecipeItem.objects.create(recipe=recipe, input_sku=sku, quantity=Decimal(quantity), unit="kg", sort_order=order)
    return recipe


def test_bootstrap_over_sheets_shaped_like_the_seed():
    _sheet("creme-levain", "Levain", "LEVAIN", "5", [("FERMENTO-NAT", "1.7"), ("FARINHA-T65", "1.7"), ("AGUA-FILTRADA", "1.7")])
    _sheet("massa-pasta-autolizada", "Pasta Autolizada", "PASTA-AUTOLIZADA", "8.4", [("FARINHA-T65", "5"), ("AGUA-FILTRADA", "3.5")])
    _sheet(
        "massa-tradicao", "Massa Tradição", "MASSA-TRADICAO", "10",
        [("PASTA-AUTOLIZADA", "8.4"), ("LEVAIN", "1.5"), ("SAL", "0.1")],
        steps=("Pesagem", "Mistura", "Fermentação"),
    )

    out = StringIO()
    call_command("bootstrap_recipe_book", stdout=out)
    assert "3 criadas, 0 puladas" in out.getvalue()
    assert RecipeEntry.objects.count() == 3
    assert RecipeVersion.objects.filter(status=RecipeVersion.Status.PUBLISHED).count() == 3

    book = build_recipe_book()
    cards = {card.ref: card for card in book.entries}
    assert set(cards) == {"creme-levain", "massa-pasta-autolizada", "massa-tradicao"}
    assert all(card.has_ficha and card.current_version_number == 1 for card in cards.values())
    assert cards["massa-tradicao"].anchor_kind == "flour"
    assert cards["massa-tradicao"].hydration_display != ""

    detail = build_recipe_entry("massa-tradicao")
    (version,) = detail.versions
    assert version.source_kind == "ficha"
    assert version.steps == ("Pesagem", "Mistura", "Fermentação")
    assert {part.entry_ref for part in version.lens.parts} == {"creme-levain", "massa-pasta-autolizada"}
    assert all(part.has_formula for part in version.lens.parts)
    assert {item.sku for item in version.lens.bom} == {"PASTA-AUTOLIZADA", "LEVAIN", "SAL"}

    # Idempotente: rodar de novo não duplica nem toca a ficha.
    call_command("bootstrap_recipe_book", stdout=StringIO())
    assert RecipeEntry.objects.count() == 3
    assert "version_ref" not in Recipe.objects.get(ref="massa-tradicao").meta


def test_the_seed_bootstraps_every_eligible_sheet(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Recipe-Book-2026!")
    out = StringIO()
    call_command("seed", stdout=out)
    assert "Inventário de receitas:" in out.getvalue()

    eligible = [
        recipe for recipe in Recipe.objects.filter(is_active=True)
        if recipe._declared_output_unit() in RecipeVersion.YieldUnit.values
    ]
    assert eligible, "o seed precisa semear fichas com unidade de saída declarada"
    missing = sorted(recipe.ref for recipe in eligible if not RecipeEntry.objects.filter(ref=recipe.ref).exists())
    assert not missing, f"fichas do seed sem entry no inventário: {missing}"
    assert RecipeEntry.objects.filter(current_version__isnull=True).count() == 0

    book = build_recipe_book()
    assert book.count == RecipeEntry.objects.count()
    assert all(card.has_ficha for card in book.entries)
