"""Tabelão: falha no meio nunca grava meia planilha; leitura não faz N+1."""

from unittest.mock import patch

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext

from shopman.backstage.services import purchase

pytestmark = pytest.mark.django_db


def materials(count):
    Material = apps.get_model("buyman", "Material")
    return [Material.objects.create(sku=f"GRID-{i}", name=f"Insumo {i}", unit="kg") for i in range(count)]


def test_costs_roll_back_if_second_write_fails():
    rows = materials(2)
    Supplier = apps.get_model("buyman", "Supplier")
    supplier = Supplier.objects.create(ref="GRID-SUP", name="Fornecedor")
    original = purchase._upsert_supplier_cost
    calls = 0

    def write(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("falha de escrita")
        return original(**kwargs)

    with patch.object(purchase, "_upsert_supplier_cost", side_effect=write), pytest.raises(RuntimeError):
        purchase.upsert_costs(
            {"supplierRef": supplier.ref, "costs": [{"materialSku": row.sku, "costInput": "12,50"} for row in rows]}
        )
    assert not apps.get_model("buyman", "SupplierMaterialCost").objects.exists()


def test_minimums_roll_back_if_write_fails():
    rows = materials(2)
    Material = apps.get_model("buyman", "Material")
    original = Material.objects.__class__.bulk_update

    def write_then_fail(manager, *args, **kwargs):
        original(manager, *args, **kwargs)
        raise RuntimeError("falha depois de escrever")

    with patch.object(Material.objects.__class__, "bulk_update", write_then_fail), pytest.raises(RuntimeError):
        purchase.set_min_stock({"minimums": [{"materialSku": row.sku, "minStock": "2,5"} for row in rows]})
    assert all(not row.metadata for row in Material.objects.all())


def test_cost_validation_queries_do_not_grow():
    rows = materials(12)
    Supplier = apps.get_model("buyman", "Supplier")
    supplier = Supplier.objects.create(ref="GRID-SUP", name="Fornecedor")
    Conversion = apps.get_model("buyman", "MaterialConversion")
    conversions = {
        row.sku: Conversion.objects.create(material=row, supplier=supplier, label="Saco", to_base_factor=2).pk
        for row in rows
    }
    counts = []
    for size in (1, 12):
        with (
            patch.object(purchase, "_upsert_supplier_cost"),
            patch.object(purchase, "build_purchase"),
            CaptureQueriesContext(connection) as queries,
        ):
            purchase.upsert_costs(
                {
                    "supplierRef": supplier.ref,
                    "costs": [
                        {"materialSku": row.sku, "costInput": "12,50", "conversionId": conversions[row.sku]}
                        for row in rows[:size]
                    ],
                }
            )
        counts.append(len(queries))
    print(f"COST_VALIDATION_QUERIES 1={counts[0]} 12={counts[1]}")
    assert counts[0] == counts[1]


def test_minimum_queries_do_not_grow():
    rows = materials(12)
    counts = []
    for size in (1, 12):
        with patch.object(purchase, "build_purchase"), CaptureQueriesContext(connection) as queries:
            purchase.set_min_stock({"minimums": [{"materialSku": row.sku, "minStock": "2,5"} for row in rows[:size]]})
        counts.append(len(queries))
    print(f"MINIMUM_QUERIES 1={counts[0]} 12={counts[1]}")
    assert counts[0] == counts[1]


@pytest.mark.parametrize("kind", ["cost", "minimum"])
def test_batch_api_reports_server_timing(kind):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory, force_authenticate

    from shopman.backstage.api.purchase import PurchaseCostBatchView, PurchaseMinStockView

    rows = materials(12)
    supplier = apps.get_model("buyman", "Supplier").objects.create(ref="GRID-SUP", name="Fornecedor")
    user = get_user_model().objects.create_superuser(username="grid-timing", password="test")
    view = PurchaseCostBatchView if kind == "cost" else PurchaseMinStockView
    counts = []
    for size in (1, 12):
        payload = (
            {
                "supplierRef": supplier.ref,
                "costs": [{"materialSku": row.sku, "costInput": "12,50"} for row in rows[:size]],
            }
            if kind == "cost"
            else {"minimums": [{"materialSku": row.sku, "minStock": "2,5"} for row in rows[:size]]}
        )
        request = APIRequestFactory().post("/grid-timing/", payload, format="json")
        force_authenticate(request, user=user)
        response = view.as_view()(request)
        assert response.status_code == 200
        assert "projection;dur=" in response["Server-Timing"]
        counts.append(response._watchman_query_count)
        print(f"API_TIMING {kind} lines={size} queries={response._watchman_query_count} {response['Server-Timing']}")
    if kind == "minimum":
        assert counts[0] == counts[1]
