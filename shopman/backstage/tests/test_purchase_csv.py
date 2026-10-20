"""Import/export da Base: erro por registro, revisão e escrita única atômica."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.admin.models import LogEntry
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.buyman.models import Material, Supplier
from shopman.offerman.models import Product

from shopman.backstage.tests import test_api_purchase_catalog as fixtures

purchase_operator = fixtures.purchase_operator
pytestmark = pytest.mark.django_db


def post(client, entity, body, key=None):
    return client.post(
        f"/api/v1/backstage/purchase/{entity}/csv/",
        json.dumps(body),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def preview(client, entity, text):
    response = post(client, entity, {"preview": True, "csv": text})
    assert response.status_code == 200, response.content
    return response.json()["preview"]


def apply(client, entity, text, revision, key=None):
    return post(client, entity, {"csv": text, "base_revision": revision}, key)


@pytest.mark.parametrize(
    "entity,text,Model,identifier",
    [
        ("materials", "SKU;Nome;Unidade;Mínimo\nFAR;Farinha;kg;1,5", Material, "sku"),
        ("suppliers", "Referência;Razão social;Prazo (dias)\nmoinho;Moinho;2", Supplier, "ref"),
    ],
)
def test_preview_apply_replay_and_export(client, purchase_operator, entity, text, Model, identifier):
    client.force_login(purchase_operator)
    result = preview(client, entity, text)
    assert result["errors"] == []
    assert result["totals"] == {"new": 1, "update": 0}
    assert Model.objects.count() == 0
    key = str(uuid4())
    response = apply(client, entity, text, result["base_revision"], key)
    assert response.status_code == 200, response.content
    assert Model.objects.count() == 1
    assert LogEntry.objects.count() == 1
    assert apply(client, entity, text, result["base_revision"], key).json() == response.json()
    assert LogEntry.objects.count() == 1
    table = client.get(f"/api/v1/backstage/purchase/{entity}/csv/")
    assert table.status_code == 200, table.content
    assert "projection;dur=" in table["Server-Timing"]
    assert len(table.json()["table"]["rows"]) == 1
    assert table.json()["table"]["header"][-1] == "Arquivado"
    assert table.json()["table"]["rows"][0][-1] == "Não"
    if entity == "materials":
        row = Model.objects.get()
        assert Decimal(row.metadata["purchase"]["min_stock"]) == Decimal("1.5")
        assert table.json()["table"]["rows"][0][5] == "1,500"


@pytest.mark.parametrize(
    "entity,text",
    [
        ("materials", "SKU;Nome;Unidade\nA;Farinha;kg\nB;Ruim;banana"),
        ("suppliers", "Referência;Razão social;E-mail\na;A;central@example.test\nb;B;ruim"),
    ],
)
def test_error_per_line_does_not_apply_good_rows(client, purchase_operator, entity, text):
    client.force_login(purchase_operator)
    result = preview(client, entity, text)
    assert result["errors"][0]["row"] == 3
    response = apply(client, entity, text, result["base_revision"])
    assert response.status_code == 400
    assert response.json()["outcome"] == "not_applied"
    assert Material.objects.count() == Supplier.objects.count() == LogEntry.objects.count() == 0


def test_changed_record_or_csv_refuses_apply_and_preserves_metadata(client, purchase_operator):
    client.force_login(purchase_operator)
    supplier = Supplier.objects.create(ref="a", name="Antes", metadata={"extra": {"keep": True}})
    text = "Referência;Razão social;Arquivado\na;Depois;Sim"
    result = preview(client, "suppliers", text)
    supplier.name = "Outro gestor"
    supplier.save()
    assert apply(client, "suppliers", text, result["base_revision"]).status_code == 409
    result = preview(client, "suppliers", text)
    assert apply(client, "suppliers", text.replace("Depois", "Outro CSV"), result["base_revision"]).status_code == 409
    assert apply(client, "suppliers", text, result["base_revision"]).status_code == 200
    supplier.refresh_from_db()
    assert supplier.name == "Depois"
    assert supplier.is_active is False
    assert supplier.metadata == {"extra": {"keep": True}}


def test_same_sku_units_guard_and_duplicates(client, purchase_operator):
    client.force_login(purchase_operator)
    Product.objects.create(sku="POTE", name="Pote", unit="kg", base_price_q=100)
    result = preview(client, "materials", "SKU;Nome;Unidade\nPOTE;Pote;un\nPOTE;Pote;kg")
    assert len(result["errors"]) == 2
    assert Material.objects.count() == 0


def test_import_rollback_when_audit_fails(client, purchase_operator, monkeypatch):
    client.force_login(purchase_operator)
    text = "Referência;Razão social\na;A\nb;B"
    result = preview(client, "suppliers", text)

    def refuse(*args, **kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(LogEntry.objects, "bulk_create", refuse)
    with pytest.raises(RuntimeError, match="audit failure"):
        apply(client, "suppliers", text, result["base_revision"])
    assert Supplier.objects.count() == 0


def test_permission_and_headers(client, purchase_operator):
    assert client.get("/api/v1/backstage/purchase/materials/csv/").status_code == 403
    client.force_login(purchase_operator)
    assert post(client, "materials", {"preview": True, "csv": "Nome;SKU\nA;B"}).status_code == 400
    assert client.get("/api/v1/backstage/purchase/unknown/csv/").status_code == 404
    assert apply(client, "materials", "SKU;Nome;Unidade\nA;A;kg", "forged").status_code == 409


def test_queries_do_not_grow_with_import_or_export_rows(client, purchase_operator):
    client.force_login(purchase_operator)
    counts = []
    for count, prefix in ((2, "a"), (40, "b")):
        text = "Referência;Razão social\n" + "\n".join(f"{prefix}{i};Fornecedor {i}" for i in range(count))
        with CaptureQueriesContext(connection) as preview_queries:
            result = post(client, "suppliers", {"preview": True, "csv": text})
        with CaptureQueriesContext(connection) as apply_queries:
            saved = apply(client, "suppliers", text, result.json()["preview"]["base_revision"])
        with CaptureQueriesContext(connection) as export_queries:
            exported = client.get("/api/v1/backstage/purchase/suppliers/csv/")
        assert result.status_code == saved.status_code == exported.status_code == 200, saved.content
        counts.append((len(preview_queries), len(apply_queries), len(export_queries)))
        print("CSV_PERF", count, counts[-1], result["Server-Timing"], saved["Server-Timing"], exported["Server-Timing"])
    assert all(after <= before for before, after in zip(counts[0], counts[1], strict=True))


def test_before_individual_creations_and_after_one_import(client, purchase_operator):
    from shopman.shop.observability import capture_catalog_timing, catalog_stage

    client.force_login(purchase_operator)
    with capture_catalog_timing() as baseline, catalog_stage("projection"):
        for index in range(10):
            response = client.post(
                "/api/v1/backstage/purchase/suppliers/",
                json.dumps({"ref": f"before{index}", "name": "Fornecedor"}),
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            )
            assert response.status_code == 200
    text = "Referência;Razão social\n" + "\n".join(f"after{i};Fornecedor" for i in range(10))
    result = preview(client, "suppliers", text)
    with CaptureQueriesContext(connection) as after:
        response = apply(client, "suppliers", text, result["base_revision"])
    assert response.status_code == 200, response.content
    assert len(after) < baseline.query_count
    print("CSV_BEFORE_AFTER", baseline.query_count, baseline.server_timing(), len(after), response["Server-Timing"])


@pytest.mark.parametrize("body", [["x"], "x", 1, None])
def test_non_object_body_is_a_field_error(client, purchase_operator, body):
    client.force_login(purchase_operator)
    response = post(client, "suppliers", body)
    assert response.status_code == 400
    assert response.json()["field"] == "csv"
    assert response.json()["errors"]["csv"]
    assert Supplier.objects.count() == 0
