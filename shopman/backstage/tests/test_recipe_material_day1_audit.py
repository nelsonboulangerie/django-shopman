from __future__ import annotations

import json

import pytest
from django.core.management import CommandError, call_command

from shopman.backstage.data_readiness.operational import (
    OperationalAuditError,
    OperationalSnapshot,
    audit_operational_day1,
    database_operational_snapshot,
    read_sku_scope,
)


def _snapshot(*, products=None, recipes=None, materials=None, versions=None):
    return OperationalSnapshot(
        products=products or {},
        recipes=recipes or {},
        materials=materials or {},
        versions=versions or {},
    )


def _product(**overrides):
    product = {"name": "Pão", "is_published": True, "is_sellable": True}
    product.update(overrides)
    return product


def _recipe(*items, **overrides):
    recipe = {
        "ref": "pao-v1",
        "batch_size": "1.000",
        "steps_count": 2,
        "items": [
            {
                "input_sku": sku,
                "quantity": "0.100",
                "unit": "g",
                "usable_factor": "1.0000",
                "is_optional": False,
            }
            for sku in items
        ],
    }
    recipe.update(overrides)
    return recipe


def _material(**overrides):
    material = {
        "name": "Farinha",
        "unit": "g",
        "is_active": True,
        "supplier_known": True,
        "preferred_cost": True,
        "conversion_count": 1,
        "approximate_conversion_count": 0,
    }
    material.update(overrides)
    return material


def _version(**overrides):
    version = {
        "version_ref": "pao-v1@1",
        "published": True,
        "published_at": "2026-09-29T10:00:00Z",
        "source_present": True,
        "origin_present": True,
        "created_by_present": True,
    }
    version.update(overrides)
    return version


def test_scope_is_explicit_deduplicated_and_supports_comments(tmp_path):
    scope_file = tmp_path / "scope.txt"
    scope_file.write_text("pao\n# não entra\nmel # comentário\n", encoding="utf-8")

    assert read_sku_scope(["PAO", " brioche "], scope_file) == ["PAO", "BRIOCHE", "MEL"]
    with pytest.raises(OperationalAuditError, match="ao menos um SKU"):
        read_sku_scope([])


def test_complete_recipe_tree_separates_production_procurement_cost_and_traceability():
    snapshot = _snapshot(
        products={"PAO": _product()},
        recipes={"PAO": _recipe("MASSA"), "MASSA": _recipe("FARINHA")},
        # MASSA also exists as a Material, but an active recipe takes precedence
        # because the Craftsman contract treats it as a sub-product.
        materials={"MASSA": _material(), "FARINHA": _material()},
        versions={"PAO": _version(), "MASSA": _version(version_ref="massa@1")},
    )

    report = audit_operational_day1(["PAO"], snapshot)
    output = report["outputs"][0]

    assert output["production_ready"] is True
    assert output["traceability_ready"] is True
    assert output["procurement_ready"] is True
    assert output["cost_ready"] is True
    assert output["leaf_materials"] == ["FARINHA"]
    assert output["findings"] == []
    assert report["mode"] == "read_only_dry_run"


def test_missing_recipe_blocks_only_production_and_never_mutates_snapshot():
    products = {"PAO": _product()}
    snapshot = _snapshot(products=products)

    report = audit_operational_day1(["PAO"], snapshot)

    assert report["outputs"][0]["production_ready"] is False
    assert report["outputs"][0]["findings"][0]["code"] == "missing_active_recipe"
    assert products["PAO"]["is_published"] is True


def test_unknown_supplier_and_cost_are_explicit_decisions_not_fake_defaults():
    snapshot = _snapshot(
        products={"PAO": _product()},
        recipes={"PAO": _recipe("FARINHA")},
        materials={
            "FARINHA": _material(
                supplier_known=False,
                preferred_cost=False,
                conversion_count=0,
            )
        },
        versions={"PAO": _version(source_present=False)},
    )

    output = audit_operational_day1(["PAO"], snapshot)["outputs"][0]
    codes = {finding["code"] for finding in output["findings"]}

    assert output["production_ready"] is True
    assert output["traceability_ready"] is False
    assert output["procurement_ready"] is False
    assert output["cost_ready"] is False
    assert {
        "incomplete_recipe_provenance",
        "supplier_unknown",
        "preferred_cost_unknown",
        "no_declared_purchase_conversion",
    } <= codes


def test_cycle_and_unresolved_required_input_block_production():
    cycle = _snapshot(
        products={"A": _product()},
        recipes={"A": _recipe("B"), "B": _recipe("A")},
        versions={"A": _version(), "B": _version()},
    )
    unresolved = _snapshot(
        products={"A": _product()},
        recipes={"A": _recipe("DESCONHECIDO")},
        versions={"A": _version()},
    )

    cycle_output = audit_operational_day1(["A"], cycle)["outputs"][0]
    unresolved_output = audit_operational_day1(["A"], unresolved)["outputs"][0]

    assert cycle_output["production_ready"] is False
    assert any(finding["code"] == "recipe_cycle" for finding in cycle_output["findings"])
    assert unresolved_output["production_ready"] is False
    assert any(finding["code"] == "unresolved_recipe_input" for finding in unresolved_output["findings"])


def test_command_refuses_to_overwrite_report(tmp_path, monkeypatch):
    output = tmp_path / "readiness.json"
    snapshot = _snapshot(products={"PAO": _product()})
    monkeypatch.setattr(
        "shopman.backstage.management.commands.audit_recipe_material_day1.database_operational_snapshot",
        lambda: snapshot,
    )

    call_command("audit_recipe_material_day1", "--sku", "PAO", "--output", output)
    assert json.loads(output.read_text())["scope"] == ["PAO"]
    with pytest.raises(CommandError, match="já existe"):
        call_command("audit_recipe_material_day1", "--sku", "PAO", "--output", output)


@pytest.mark.django_db
def test_database_snapshot_reads_models_without_mutating_them():
    from django.utils import timezone
    from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
    from shopman.craftsman.models import Recipe, RecipeEntry, RecipeItem, RecipeVersion
    from shopman.offerman.models import Product

    product = Product.objects.create(sku="PAO", name="Pão", base_price_q=1000)
    material = Material.objects.create(
        sku="FARINHA",
        name="Farinha",
        unit="g",
        metadata={"supplier": "moinho"},
    )
    supplier = Supplier.objects.create(ref="moinho", name="Moinho")
    conversion = MaterialConversion.objects.create(
        material=material,
        supplier=supplier,
        label="saco",
        to_base_factor="25000",
    )
    SupplierMaterialCost.objects.create(
        material=material,
        supplier=supplier,
        conversion=conversion,
        cost_q=18000,
        is_preferred=True,
    )
    recipe = Recipe.objects.create(
        ref="pao-v1",
        name="Pão",
        output_sku="PAO",
        batch_size="1000",
        steps=["Misturar", "Assar"],
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity="600", unit="g")
    entry = RecipeEntry.objects.create(ref="pao-v1", name="Pão", output_sku="PAO")
    version = RecipeVersion.objects.create(
        entry=entry,
        number=1,
        status=RecipeVersion.Status.PUBLISHED,
        source={"kind": "ficha"},
        origin={"sheet": "canonica"},
        created_by="operacao",
        published_at=timezone.now(),
    )
    entry.current_version = version
    entry.save(update_fields=["current_version"])

    snapshot = database_operational_snapshot()

    assert snapshot.products["PAO"]["is_sellable"] is True
    assert snapshot.recipes["PAO"]["items"][0]["input_sku"] == "FARINHA"
    assert snapshot.materials["FARINHA"]["preferred_cost"] is True
    assert snapshot.materials["FARINHA"]["conversion_count"] == 1
    assert snapshot.versions["PAO"]["source_present"] is True
    assert Product.objects.get(pk=product.pk).base_price_q == 1000
