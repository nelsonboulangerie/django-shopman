"""``import_recipe_versions``: versão nova por receita, levain antes da massa, pasta só quando fecha exata.

Números sintéticos: os da planilha do dono nunca entram no repositório.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeItem, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

pytestmark = pytest.mark.django_db

LABEL = "Fórmula de teste"
SOURCE = "Planilha de teste, aba X"


@pytest.fixture
def house(db):
    for sku, name, unit in [
        ("FARINHA-NOVARA-T55", "Farinha de trigo T65", "kg"),
        ("FARINHA-INTEGRAL-ORGANICA", "Farinha de trigo integral", "kg"),
        ("AGUA-FILTRADA", "Água filtrada", "l"),
        ("SAL-REFINADO", "Sal", "kg"),
        ("LEVAIN-LIQUIDO", "Fermento natural (levain)", "kg"),
        ("MALTE-EXTRATO", "Malte", "kg"),
    ]:
        Material.objects.create(sku=sku, name=name, unit=unit)

    def ficha(ref, name, output_sku, batch, items):
        recipe = Recipe.objects.create(ref=ref, name=name, output_sku=output_sku, batch_size=Decimal(batch),
                                       meta={"output_unit": "g"})
        for order, (sku, qty) in enumerate(items):
            RecipeItem.objects.create(recipe=recipe, input_sku=sku, quantity=Decimal(qty), unit="g", sort_order=order)
        return recipe

    levain = ficha("creme-levain", "Levain", "LEVAIN", "3000",
                   [("LEVAIN-LIQUIDO", "1000"), ("FARINHA-NOVARA-T55", "1000"), ("AGUA-FILTRADA", "1000")])
    pasta = ficha("massa-pasta-autolizada", "Pasta Autolizada", "PASTA-AUTOLIZADA", "1700",
                  [("FARINHA-NOVARA-T55", "1000"), ("AGUA-FILTRADA", "700")])
    tradicao = ficha("massa-tradicao", "Massa Tradição", "MASSA-TRADICAO", "2000",
                     [("PASTA-AUTOLIZADA", "1700"), ("LEVAIN", "300"), ("SAL-REFINADO", "20"), ("MALTE-EXTRATO", "5")])
    for recipe in (levain, pasta, tradicao):
        craftsman.bootstrap_entry_from_recipe(recipe)


def spec(tmp_path, *, tradicao_water="1.5"):
    data = {
        "source_text": SOURCE,
        "label": LABEL,
        "recipes": [
            {   # a massa vem antes no arquivo: o comando reordena pela dependência
                "entry_ref": "massa-tradicao",
                "title": "MASSA",
                "lines": [
                    {"name": "Farinha X", "quantity": "2", "unit": "kg", "sku": "FARINHA-NOVARA-T55"},
                    {"name": "Água", "quantity": tradicao_water, "unit": "kg", "sku": "AGUA-FILTRADA"},
                    {"name": "Sal", "quantity": "0.04", "unit": "kg", "sku": "SAL-REFINADO"},
                    {"name": "LEVAIN", "quantity": "0.3", "unit": "kg",
                     "part": {"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment"}},
                ],
                "total": {"quantity": str(Decimal("2.34") + Decimal(tradicao_water)), "unit": "kg"},
                "autolyse": {"sku": "PASTA-AUTOLIZADA", "entry_ref": "massa-pasta-autolizada"},
                "notes": "linha de custo sem ingrediente na planilha",
            },
            {
                "entry_ref": "creme-levain",
                "title": "LEVAIN",
                "lines": [
                    {"name": "Farinha X", "quantity": "0.4", "unit": "kg", "sku": "FARINHA-NOVARA-T55"},
                    {"name": "Farinha Y", "quantity": "0.2", "unit": "kg", "sku": "FARINHA-INTEGRAL-ORGANICA"},
                    {"name": "Água", "quantity": "0.6", "unit": "kg", "sku": "AGUA-FILTRADA"},
                    {"name": "Levain", "quantity": "0.6", "unit": "kg", "sku": "LEVAIN-LIQUIDO"},
                ],
                "total": {"quantity": "1.8", "unit": "kg"},
            },
        ],
    }
    path = tmp_path / "receitas.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def run(*args):
    out = StringIO()
    call_command("import_recipe_versions", *args, stdout=out)
    return out.getvalue()


def bom(ref):
    return {i.input_sku: i.quantity for i in Recipe.objects.get(ref=ref).items.all()}


def test_without_apply_only_shows(house, tmp_path):
    out = run(spec(tmp_path))
    assert "nada gravado" in out
    assert out.index("creme-levain") < out.index("massa-tradicao")
    assert RecipeVersion.objects.filter(label=LABEL).count() == 0


def test_apply_creates_drafts_without_publishing(house, tmp_path):
    run(spec(tmp_path), "--apply")
    drafts = RecipeVersion.objects.filter(label=LABEL)
    assert {v.entry.ref: v.status for v in drafts} == {"creme-levain": "draft", "massa-tradicao": "draft"}
    levain = drafts.get(entry__ref="creme-levain")
    assert levain.source == {"kind": "import", "text": SOURCE}
    assert levain.steps == []
    assert levain.yield_unit == "g" and levain.yield_quantity == Decimal("1800")
    assert levain.origin["lines"][0] == {"name": "Farinha X", "quantity": "0.4", "unit": "kg"}
    assert bom("creme-levain")["FARINHA-NOVARA-T55"] == Decimal("1000")  # ficha intacta


def test_publish_goes_levain_first_and_supersedes(house, tmp_path):
    run(spec(tmp_path), "--apply", "--publish")

    for ref in ("creme-levain", "massa-tradicao"):
        entry = RecipeEntry.objects.get(ref=ref)
        assert entry.current_version.label == LABEL
        assert entry.current_version.status == RecipeVersion.Status.PUBLISHED
        assert entry.versions.get(number=1).status == RecipeVersion.Status.SUPERSEDED

    assert set(bom("creme-levain")) == {"FARINHA-NOVARA-T55", "FARINHA-INTEGRAL-ORGANICA", "AGUA-FILTRADA", "LEVAIN-LIQUIDO"}
    # Toda a farinha da mistura final passa pela pasta (2000 g → 3400 g de pasta, 1400 g de água);
    # sobram 100 g de água; o levain entra como item; o malte saiu.
    tradicao = bom("massa-tradicao")
    assert tradicao == {
        "PASTA-AUTOLIZADA": Decimal("3400"), "LEVAIN": Decimal("300"),
        "AGUA-FILTRADA": Decimal("0.1"), "SAL-REFINADO": Decimal("0.04"),
    }
    assert Recipe.objects.get(ref="massa-tradicao").batch_size == Decimal("3840")
    # O que o levain carrega entra na base da massa.
    items = {i["sku"]: Decimal(i["quantity"]) for i in RecipeEntry.objects.get(ref="massa-tradicao").current_version.formula["items"]}
    assert items["FARINHA-NOVARA-T55"] == Decimal("2066.667")  # 2000 + 300 × 400/1800, em três casas


def test_rerun_is_idempotent(house, tmp_path):
    path = spec(tmp_path)
    run(path, "--apply", "--publish")
    out = run(path, "--apply", "--publish")
    assert out.count("já publicada") == 2
    assert RecipeVersion.objects.filter(label=LABEL).count() == 2


def test_apply_then_publish_reuses_the_drafts(house, tmp_path):
    path = spec(tmp_path)
    run(path, "--apply")
    run(path, "--apply", "--publish")
    assert RecipeVersion.objects.filter(label=LABEL).count() == 2
    assert RecipeEntry.objects.get(ref="massa-tradicao").current_version.label == LABEL


def test_paste_that_does_not_fit_keeps_the_dough_in_draft(house, tmp_path):
    out = run(spec(tmp_path, tradicao_water="0.5"), "--apply", "--publish")
    assert "fica em RASCUNHO" in out
    tradicao = RecipeEntry.objects.get(ref="massa-tradicao")
    assert tradicao.current_version.number == 1
    assert tradicao.versions.get(label=LABEL).status == RecipeVersion.Status.DRAFT
    assert RecipeEntry.objects.get(ref="creme-levain").current_version.label == LABEL


def test_publish_requires_apply(house, tmp_path):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        run(spec(tmp_path), "--publish")
