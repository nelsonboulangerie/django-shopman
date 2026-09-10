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


def test_a_piece_reaches_the_screen_as_the_sheet_declares_it():
    """A baguete é 280 g de Massa Tradição — e a tela mostra isso, não uma fórmula.

    Antes do WP-FICHA-DE-PRODUTO-E-PROMESSA §A a peça exibia a composição da
    massa como se fosse dela, com "farinha pré-fermentada 100%" e avisos de
    padaria que eram artefato da dissolução, não fato da peça.
    """
    _sheet("creme-levain", "Levain", "LEVAIN", "5", [("FERMENTO-NAT", "1.7"), ("FARINHA-T65", "1.7"), ("AGUA-FILTRADA", "1.7")])
    _sheet("massa-pasta-autolizada", "Pasta Autolizada", "PASTA-AUTOLIZADA", "8.4", [("FARINHA-T65", "5"), ("AGUA-FILTRADA", "3.5")])
    _sheet("massa-tradicao", "Massa Tradição", "MASSA-TRADICAO", "10",
           [("PASTA-AUTOLIZADA", "8.4"), ("LEVAIN", "1.5"), ("SAL", "0.1")])
    _sheet("baguete", "Baguette de Tradition", "BF", "1", [("MASSA-TRADICAO", "0.280")], unit="un")

    call_command("bootstrap_recipe_book", stdout=StringIO())

    detail = build_recipe_entry("baguete")
    (version,) = detail.versions
    assert version.yield_quantity == "1"
    assert version.yield_unit == "un"
    assert version.lens.is_bakery is False
    assert version.lens.anchor_kind == "total"
    assert version.lens.parts == ()
    assert version.lens.warnings == ()
    assert [(item.sku, item.quantity_g) for item in version.lens.items] == [("MASSA-TRADICAO", "280")]
    assert [item.sku for item in version.lens.bom] == ["MASSA-TRADICAO"]
    assert all(metric.value_display == "" for metric in version.lens.metrics)

    # O cartão do inventário também para de anunciar hidratação de peça.
    cards = {card.ref: card for card in build_recipe_book().entries}
    assert cards["baguete"].hydration_display == ""
    assert cards["baguete"].anchor_kind == "total"
    # E a fórmula continua com a lente: ali a parte é fração de verdade.
    assert cards["massa-tradicao"].anchor_kind == "flour"
    assert cards["massa-tradicao"].hydration_display != ""


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

    # Sobre o dado REAL: nenhuma peça do seed acusa lente de padaria, e a
    # fórmula continua acusando (WP-FICHA-DE-PRODUTO-E-PROMESSA §A). O detalhe
    # de uma peça está no teste rápido acima; aqui vale a varredura.
    pecas = [
        recipe.ref for recipe in eligible
        if recipe._declared_output_unit() == "un"
    ]
    assert "baguete" in pecas
    for ref in pecas:
        (versao,) = build_recipe_entry(ref).versions
        assert versao.yield_quantity == "1", f"{ref} não rende uma unidade"
        assert versao.lens.is_bakery is False, f"{ref} acusa lente de padaria"
        assert versao.lens.parts == (), f"{ref} ganhou parte fabricada"
        assert versao.lens.warnings == (), f"{ref}: {versao.lens.warnings}"
    massa = build_recipe_entry("massa-tradicao")
    assert massa.versions[0].lens.is_bakery is True
