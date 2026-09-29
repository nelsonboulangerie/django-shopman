"""GTIN de insumo: rascunho seguro, aceite humano e propagação do rótulo."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product

from shopman.shop.services import attributes
from shopman.shop.services import material_enrichment as me
from shopman.shop.services import product_enrichment as pe

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(db):
    return User.objects.create_user("gestor-insumo", password="pw", is_staff=True)


def _draft(material: Material) -> None:
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("gtin", "7898708850309", pe.SOURCE_NFE, source_ref="4126")
    suggestion.add("name", "FARINHA T55 1KG", pe.SOURCE_COSMOS)
    suggestion.add("brand", "MOINHO", pe.SOURCE_COSMOS)
    suggestion.add("ncm", "11010010", pe.SOURCE_NFE)
    suggestion.add("allergens", ["glúten"], pe.SOURCE_OFF)
    material.metadata = me.merge_into_metadata(material.metadata, suggestion)
    material.save()


def test_suggestion_stays_pending_and_does_not_change_material(manager):
    material = Material.objects.create(
        sku="FARINHA", name="Farinha cadastrada", unit="kg", metadata={"brand": "Manual"}
    )

    _draft(material)
    material.refresh_from_db()

    assert material.name == "Farinha cadastrada"
    assert material.metadata["brand"] == "Manual"
    assert "gtin" not in material.metadata
    assert set(me.pending_fields(material)) == {"gtin", "name", "brand", "ncm", "allergens"}


def test_accept_is_field_by_field_and_requires_replace(manager):
    material = Material.objects.create(
        sku="FARINHA", name="Farinha cadastrada", unit="kg", metadata={"brand": "Manual"}
    )
    _draft(material)

    result = me.accept_fields(material, ["gtin", "brand", "ncm"], user=manager)
    material.refresh_from_db()

    assert result.applied == ["gtin", "ncm"]
    assert result.conflicts == {"brand": "Manual"}
    assert material.metadata["gtin"] == "7898708850309"
    assert material.metadata["ncm"] == "11010010"
    assert material.metadata["brand"] == "Manual"
    accepted = material.metadata["enrichment"]["accepted"]["gtin"]
    assert accepted["source"] == "nfe"
    assert accepted["source_ref"] == "4126"
    assert accepted["accepted_by"] == "gestor-insumo"


def test_accepting_allergen_recalculates_product_without_rewriting_recipe(manager):
    material = Material.objects.create(
        sku="FARINHA", name="Farinha", unit="kg", metadata={"diet": "vegan"}
    )
    product = Product.objects.create(sku="PAO", name="Pão", base_price_q=1000)
    recipe = Recipe.objects.create(
        ref="pao-v1", name="Pão", output_sku=product.sku, batch_size=Decimal("1"), is_active=True
    )
    item = RecipeItem.objects.create(
        recipe=recipe,
        input_sku=material.sku,
        quantity=Decimal("1"),
        unit="kg",
        meta={"diet": "vegan", "allergens": []},
    )
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("allergens", ["glúten"], pe.SOURCE_OFF)
    material.metadata = me.merge_into_metadata(material.metadata, suggestion)
    material.save()

    result = me.accept_fields(material, ["allergens"], user=manager)

    product.refresh_from_db()
    item.refresh_from_db()
    assert result.recalculated_products == ["PAO"]
    assert attributes.get(product, "alergenos") == ["glúten"]
    assert item.meta == {"diet": "vegan", "allergens": []}


def test_accepting_allergen_does_not_relax_missing_diet_gate(manager):
    material = Material.objects.create(sku="MISTERIO", name="Mistério", unit="kg")
    product = Product.objects.create(sku="PAO-M", name="Pão", base_price_q=1000)
    recipe = Recipe.objects.create(
        ref="pao-m-v1", name="Pão", output_sku=product.sku, batch_size=Decimal("1"), is_active=True
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku=material.sku,
        quantity=Decimal("1"),
        unit="kg",
        meta={},
    )
    suggestion = pe.EnrichmentSuggestion(gtin="7898708850309")
    suggestion.add("allergens", ["leite"], pe.SOURCE_OFF)
    material.metadata = me.merge_into_metadata(material.metadata, suggestion)
    material.save()

    result = me.accept_fields(material, ["allergens"], user=manager)

    product.refresh_from_db()
    assert result.recalculated_products == []
    assert attributes.get(product, "alergenos") is None


def test_nfe_stages_material_fields_without_accepting_them():
    material = Material.objects.create(sku="MANTEIGA", name="Manteiga", unit="un")

    changed = me.suggest_from_invoice(
        material,
        gtin="7898708850309",
        ncm="04051000",
        cest="1702100",
        unit="UN",
        access_key="4126",
    )

    material.refresh_from_db()
    assert changed is True
    assert "gtin" not in material.metadata
    pending = me.pending_fields(material)
    assert pending["gtin"]["source"] == "nfe"
    assert pending["ncm"]["source_ref"] == "4126"
    assert pending["fiscal_unit"]["value"] == "UN"


def test_purchase_invoice_stages_insumo_even_without_sellable_product():
    from shopman.backstage.services.purchase import _suggest_catalog_from_invoice

    material = Material.objects.create(sku="CACAU", name="Cacau", unit="kg")
    line = SimpleNamespace(
        material=material,
        sku=material.sku,
        invoice_ean="7898708850309",
        invoice_package_ean="",
        invoice_ncm="18050000",
        invoice_cest="",
        invoice_unit="KG",
        invoice_icms_cst="",
        invoice_icms_csosn="",
        invoice_st_value_q=0,
    )

    _suggest_catalog_from_invoice(lines=[line], invoice_key="4126")

    material.refresh_from_db()
    assert me.pending_fields(material)["gtin"]["source"] == "nfe"
    assert "gtin" not in material.metadata


def test_coverage_names_recipe_one_material_away():
    declared = Material.objects.create(
        sku="FARINHA", name="Farinha", unit="kg", metadata={"diet": "vegan", "allergens": ["glúten"]}
    )
    missing = Material.objects.create(sku="MISTERIO", name="Mistério", unit="kg")
    recipe = Recipe.objects.create(
        ref="pao-v1", name="Pão", output_sku="PAO", batch_size=Decimal("2"), is_active=True
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku=declared.sku, quantity=Decimal("1"), unit="kg", meta={}
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku=missing.sku, quantity=Decimal("1"), unit="kg", meta={}
    )

    report = me.coverage_report()

    assert (report.declared_materials, report.recipe_materials) == (1, 2)
    assert report.derivable_recipes == 0
    assert [(row.ref, row.missing_materials) for row in report.one_missing] == [
        ("pao-v1", ("MISTERIO",))
    ]
