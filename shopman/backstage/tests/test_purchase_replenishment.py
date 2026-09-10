"""Reposição do Compras: política configurável no Admin e prazo real do fornecedor."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps

from shopman.backstage.projections.purchase import (
    _lead_time_map,
    _purchase_policy,
    _suggested_qty,
    build_purchase,
)
from shopman.shop.purchase_policy import PurchasePolicy

POLICY_DEFAULTS = PurchasePolicy().to_dict()


@pytest.fixture
def material(db):
    Material = apps.get_model("buyman", "Material")
    return Material.objects.create(sku="CAFE-500", name="Cafe torrado 500g", unit="un", shelf_life_days=90)


@pytest.fixture
def supplier(db):
    Supplier = apps.get_model("buyman", "Supplier")
    return Supplier.objects.create(
        ref="tamura",
        name="Tamura",
        document="84.290.690/0002-28",
        metadata={"purchase": {"lead_time_days": 6}},
    )


@pytest.mark.django_db
def test_policy_defaults_and_admin_override():
    assert _purchase_policy() == POLICY_DEFAULTS

    Shop = apps.get_model("shop", "Shop")
    shop = Shop.load() or Shop.objects.create(name="Loja Teste")
    shop.defaults = dict(shop.defaults or {}, purchase={"review_period_days": 5, "safety_days": 0})
    shop.save()

    policy = _purchase_policy()
    assert policy["review_period_days"] == 5
    assert policy["safety_days"] == 0
    assert policy["consumption_window_days"] == POLICY_DEFAULTS["consumption_window_days"]


@pytest.mark.django_db
def test_lead_time_falls_back_to_preferred_supplier_declared_days(material, supplier):
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
    SupplierMaterialCost.objects.create(material=material, supplier=supplier, cost_q=1000, is_preferred=True)

    lead = _lead_time_map([material.sku], policy=dict(POLICY_DEFAULTS))

    assert lead[material.sku] == Decimal("6")


@pytest.mark.django_db
def test_lead_time_floor_without_history_or_declared(material):
    lead = _lead_time_map([material.sku], policy=dict(POLICY_DEFAULTS))

    assert lead[material.sku] == Decimal(POLICY_DEFAULTS["min_lead_time_days"])


def test_suggested_qty_covers_cycle_and_respects_shelf_life():
    # Ciclo de 10 dias a 4/dia pede 40; estoque 12 → repor 28.
    assert _suggested_qty(
        stock_on_hand=Decimal("12"),
        daily_use=Decimal("4"),
        min_stock=Decimal("0"),
        replenish_at=Decimal("10"),
        shelf_life_days=90,
    ) == Decimal("28")
    # Validade curta é teto: 5 dias × 4/dia = 20 consumíveis; estoque 12 → no máximo 8.
    assert _suggested_qty(
        stock_on_hand=Decimal("12"),
        daily_use=Decimal("4"),
        min_stock=Decimal("0"),
        replenish_at=Decimal("10"),
        shelf_life_days=5,
    ) == Decimal("8")
    # Estoque acima do alvo: nada a repor.
    assert _suggested_qty(
        stock_on_hand=Decimal("60"),
        daily_use=Decimal("4"),
        min_stock=Decimal("0"),
        replenish_at=Decimal("10"),
        shelf_life_days=90,
    ) == Decimal("0")


@pytest.mark.django_db
def test_projection_exposes_replenishment_fields(material, supplier):
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
    SupplierMaterialCost.objects.create(material=material, supplier=supplier, cost_q=1000, is_preferred=True)

    projected = next(item for item in build_purchase().materials if item.sku == material.sku)

    assert projected.leadTimeDays == 6
    expected_threshold = 6 + POLICY_DEFAULTS["review_period_days"] + POLICY_DEFAULTS["safety_days"]
    assert projected.replenishAtDays == expected_threshold
    assert projected.suggestedQty == 0
