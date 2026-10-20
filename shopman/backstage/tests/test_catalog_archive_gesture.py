"""Gesto de arquivar produto: permissão, recibo, auditoria e lote constante."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Product

from shopman.backstage.services.catalog import set_products_active

URL = "/api/v1/backstage/catalog/products/archive/"


@pytest.fixture
def operator(db):
    user = User.objects.create_user("gestora-catalogo", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_catalog",
    )
    user.user_permissions.add(permission)
    return user


def _product(index: int, *, active: bool = True) -> Product:
    return Product.objects.create(
        sku=f"ARQ-{index:03}",
        name=f"Produto {index}",
        base_price_q=1000 + index,
        is_active=active,
        is_published=True,
        is_sellable=True,
    )


def _post(client, operator, rows, active, key):
    client.force_login(operator)
    return client.post(
        URL,
        data={
            "products": rows,
            "is_active": active,
            "base_revision": "catalog-archive-v1",
            "expected_actor_id": operator.pk,
        },
        content_type="application/json",
        headers={"Idempotency-Key": key},
    )


@pytest.mark.django_db
def test_requires_manage_catalog(client):
    staff = User.objects.create_user("sem-catalogo", password="pw", is_staff=True)
    product = _product(1)
    response = _post(client, staff, [{"sku": product.sku, "base_is_active": True}], False, "archive-denied")
    assert response.status_code == 403
    product.refresh_from_db()
    assert product.is_active is True


@pytest.mark.django_db
def test_single_archive_confirmation_receipt_audit_and_undo(client, operator):
    product = _product(1)
    archived = _post(
        client,
        operator,
        [{"sku": product.sku, "base_is_active": True}],
        False,
        "archive-single",
    )

    assert archived.status_code == 200
    receipt = archived.json()
    assert receipt["applied"] == [{
        "index": 0,
        "sku": product.sku,
        "name": product.name,
        "before_is_active": True,
        "is_active": False,
        "changed": True,
    }]
    assert receipt["server_now"]
    assert receipt["undo_until"]
    product.refresh_from_db()
    assert product.is_active is False
    assert product.is_published is True
    assert product.is_sellable is True
    history = product.history.latest()
    assert history.history_user == operator
    assert history.history_change_reason == "catalog.archive:gestora-catalogo"
    assert LogEntry.objects.filter(user=operator, object_id=str(product.pk)).exists()

    replay = _post(
        client,
        operator,
        [{"sku": product.sku, "base_is_active": True}],
        False,
        "archive-single",
    )
    assert replay.json() == receipt
    assert product.history.count() == 2

    restored = _post(
        client,
        operator,
        [{"sku": product.sku, "base_is_active": False}],
        True,
        "archive-undo-single",
    )
    assert restored.status_code == 200
    product.refresh_from_db()
    assert product.is_active is True
    assert product.is_published is True
    assert product.is_sellable is True
    assert product.history.latest().history_change_reason == "catalog.unarchive:gestora-catalogo"


@pytest.mark.django_db
def test_bulk_is_one_transaction_with_row_receipts_and_constant_queries(operator):
    small = [_product(index) for index in range(1, 3)]
    large = [_product(index) for index in range(10, 20)]

    def measure(products):
        rows = [{"sku": product.sku, "base_is_active": True} for product in products]
        with patch("shopman.offerman.signals.product_updated.send"):
            with CaptureQueriesContext(connection) as queries:
                receipt = set_products_active(rows, is_active=False, actor=operator)
        return receipt, len(queries)

    small_receipt, small_queries = measure(small)
    large_receipt, large_queries = measure(large)

    assert len(small_receipt["applied"]) == 2
    assert len(large_receipt["applied"]) == 10
    assert small_receipt["conflicts"] == small_receipt["errors"] == []
    assert large_receipt["conflicts"] == large_receipt["errors"] == []
    assert small_queries == large_queries
    # 6 com ContentType aquecido; a primeira auditoria pode acrescentar 1 consulta.
    assert small_queries <= 7


@pytest.mark.django_db
def test_bulk_reports_conflict_and_missing_row_without_losing_applied(operator):
    current = _product(1)
    changed_elsewhere = _product(2, active=False)
    receipt = set_products_active(
        [
            {"sku": current.sku, "base_is_active": True},
            {"sku": changed_elsewhere.sku, "base_is_active": True},
            {"sku": "NAO-EXISTE", "base_is_active": True},
        ],
        is_active=False,
        actor=operator,
    )

    assert [row["sku"] for row in receipt["applied"]] == [current.sku]
    assert [row["sku"] for row in receipt["conflicts"]] == [changed_elsewhere.sku]
    assert [row["sku"] for row in receipt["errors"]] == ["NAO-EXISTE"]
