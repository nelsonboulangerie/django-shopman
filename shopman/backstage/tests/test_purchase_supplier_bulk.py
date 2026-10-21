"""Lote atômico, recibo revisado e custo fixo do arquivamento de fornecedores."""

import json
from uuid import uuid4

import pytest
from django.contrib.admin.models import LogEntry
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.buyman.models import Supplier

from shopman.backstage.tests import test_api_purchase_catalog as fixtures

purchase_operator = fixtures.purchase_operator

pytestmark = pytest.mark.django_db
URL = "/api/v1/backstage/purchase/suppliers/batch/"


def send(client, payload, key=None):
    return client.post(
        URL, json.dumps(payload), content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4())
    )


def rows(suppliers):
    return [{"ref": row.ref, "revision": row.updated_at.isoformat()} for row in suppliers]


def test_archive_undo_audited_and_replayed(client, purchase_operator):
    client.force_login(purchase_operator)
    suppliers = [Supplier.objects.create(ref=f"s{i}", name=f"Fornecedor {i}") for i in range(3)]
    payload = {"rows": rows(suppliers), "isActive": False}
    key = str(uuid4())
    response = send(client, payload, key)
    assert response.status_code == 200, response.content
    assert "projection;dur=" in response["Server-Timing"]
    assert Supplier.objects.filter(is_active=True).count() == 0
    assert LogEntry.objects.filter(user=purchase_operator).count() == 3
    assert send(client, payload, key).json() == response.json()
    undone = send(client, {"undo": response.json()["resource"]["undo"]})
    assert undone.status_code == 200, undone.content
    assert Supplier.objects.filter(is_active=True).count() == 3
    assert LogEntry.objects.filter(user=purchase_operator).count() == 6
    assert send(client, {"undo": response.json()["resource"]["undo"]}).status_code == 409


def test_stale_or_missing_member_changes_nothing(client, purchase_operator):
    client.force_login(purchase_operator)
    a = Supplier.objects.create(ref="a", name="A")
    b = Supplier.objects.create(ref="b", name="B")
    selected = rows([a, b])
    b.name = "Outro nome"
    b.save()
    response = send(client, {"rows": selected, "isActive": False})
    assert response.status_code == 409
    assert Supplier.objects.filter(is_active=True).count() == 2
    assert LogEntry.objects.count() == 0


def test_bulk_query_count_fixed(client, purchase_operator):
    client.force_login(purchase_operator)
    small = [Supplier.objects.create(ref=f"small{i}", name="Fornecedor") for i in range(2)]
    # Aquece caches de permissão/content type antes da medição.
    client.get("/api/v1/backstage/purchase/")
    with CaptureQueriesContext(connection) as before:
        first = send(client, {"rows": rows(small), "isActive": False})
    large = [Supplier.objects.create(ref=f"large{i}", name="Fornecedor") for i in range(40)]
    with CaptureQueriesContext(connection) as after:
        second = send(client, {"rows": rows(large), "isActive": False})
    assert first.status_code == second.status_code == 200
    assert len(after) <= len(before), (len(before), len(after))
    print("BULK_PERF", len(before), first["Server-Timing"], len(after), second["Server-Timing"])


def test_unauthorized_and_invalid_selection(client, purchase_operator):
    assert send(client, {"rows": [], "isActive": False}).status_code == 403
    client.force_login(purchase_operator)
    assert send(client, {"rows": [], "isActive": False}).status_code == 400
    assert send(client, {"rows": [{"ref": "a"}], "isActive": False}).status_code == 400
    assert send(client, {"undo": "alterado"}).status_code == 409


def test_undo_refuses_expired_or_foreign_receipt(client, purchase_operator, monkeypatch):
    from django.core import signing

    from shopman.backstage.services.purchase_supplier_bulk import SALT

    client.force_login(purchase_operator)
    a = Supplier.objects.create(ref="a", name="A")
    response = send(client, {"rows": rows([a]), "isActive": False})
    token = response.json()["resource"]["undo"]
    receipt = signing.loads(token, salt=SALT)
    receipt["actor"] += 1
    assert send(client, {"undo": signing.dumps(receipt, salt=SALT)}).status_code == 409
    monkeypatch.setattr(signing.time, "time", lambda: 9999999999)
    assert send(client, {"undo": token}).status_code == 409
    a.refresh_from_db()
    assert a.is_active is False


def test_previous_individual_requests_cost_more_than_batch(client, purchase_operator):
    client.force_login(purchase_operator)
    suppliers = [Supplier.objects.create(ref=f"baseline{i}", name="Fornecedor") for i in range(10)]
    client.get("/api/v1/backstage/purchase/")
    from shopman.shop.observability import capture_catalog_timing, catalog_stage

    with (
        capture_catalog_timing() as baseline_timing,
        catalog_stage("projection"),
        CaptureQueriesContext(connection) as before,
    ):
        for supplier in suppliers:
            response = client.post(
                f"/api/v1/backstage/purchase/suppliers/{supplier.ref}/",
                json.dumps({"isActive": False}),
                content_type="application/json",
            )
            assert response.status_code == 200
    for supplier in suppliers:
        supplier.refresh_from_db()
    with CaptureQueriesContext(connection) as after:
        response = send(client, {"rows": rows(suppliers), "isActive": True})
    assert response.status_code == 200
    assert len(after) < len(before)
    print("BEFORE_AFTER", len(before), baseline_timing.server_timing(), len(after), response["Server-Timing"])


def test_audit_failure_rolls_back_entire_batch(client, purchase_operator, monkeypatch):
    client.force_login(purchase_operator)
    suppliers = [Supplier.objects.create(ref=f"atomic{i}", name="Fornecedor") for i in range(2)]

    def refuse_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(LogEntry.objects, "bulk_create", refuse_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        send(client, {"rows": rows(suppliers), "isActive": False})
    assert Supplier.objects.filter(is_active=True).count() == 2
    assert LogEntry.objects.count() == 0


def test_non_object_body_refused_without_writing(client, purchase_operator):
    client.force_login(purchase_operator)
    response = send(client, ["x"])
    assert response.status_code == 400
    assert response.json()["field"] == "rows"
    assert response.json()["errors"]["rows"]
    assert Supplier.objects.count() == LogEntry.objects.count() == 0
