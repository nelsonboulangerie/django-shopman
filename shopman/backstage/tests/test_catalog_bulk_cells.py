"""Lote de células numa ida: recibo linha a linha (onda 1, fatia C, backend)."""

from uuid import uuid4

import pytest
from shopman.offerman.models import ListingItem

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
plain_staff = fixtures.plain_staff
shop = fixtures.shop
pytestmark = pytest.mark.django_db

CELLS_URL = "/api/v1/backstage/catalog/cells/"
MATRIX_URL = fixtures.MATRIX_URL


def _cell(client, sku, surface):
    matrix = client.get(MATRIX_URL).json()["matrix"]
    row = next(r for r in matrix["rows"] if r["sku"] == sku)
    return next(c for c in row["cells"] if c["surface_ref"] == surface)


def _post(client, body, key=None):
    return client.post(
        CELLS_URL,
        body,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def test_bulk_cells_applies_many_in_one_request(client, operator, catalog):
    client.force_login(operator)
    web_pao = _cell(client, "PAO", "web")
    web_bolo = _cell(client, "BOLO", "web")
    body = {
        "base_revision": "batch-1",
        "expected_actor_id": operator.pk,
        "cells": [
            {
                "sku": "PAO",
                "surface_ref": "web",
                "price_q": 999,
                "base_revisions": web_pao["action"]["payload_schema"]["base_revisions"],
            },
            {
                "sku": "BOLO",
                "surface_ref": "web",
                "is_sellable": False,
                "base_revisions": web_bolo["action"]["payload_schema"]["base_revisions"],
            },
        ],
    }
    response = _post(client, body)
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["outcome"] == "applied"
    assert {item["sku"] for item in payload["applied"]} == {"PAO", "BOLO"}
    assert payload["conflicts"] == []
    assert payload["errors"] == []

    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 999
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").is_sellable is False


def test_bulk_cells_reports_conflict_per_line_and_keeps_the_rest(client, operator, catalog):
    client.force_login(operator)
    web_pao = _cell(client, "PAO", "web")
    body = {
        "base_revision": "batch-2",
        "expected_actor_id": operator.pk,
        "cells": [
            {
                "sku": "PAO",
                "surface_ref": "web",
                "price_q": 777,
                "base_revisions": web_pao["action"]["payload_schema"]["base_revisions"],
            },
            {
                "sku": "BOLO",
                "surface_ref": "web",
                "price_q": 1234,
                "base_revisions": {"price_q": "stale"},
            },
        ],
    }
    response = _post(client, body)
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert [item["sku"] for item in payload["applied"]] == ["PAO"]
    assert [item["sku"] for item in payload["conflicts"]] == ["BOLO"]
    assert payload["conflicts"][0]["conflicting_fields"] == ["price_q"]
    # A linha boa mudou; a em conflito ficou como estava.
    assert ListingItem.objects.get(listing__ref="web", product__sku="PAO").price_q == 777
    assert ListingItem.objects.get(listing__ref="web", product__sku="BOLO").price_q == 4800


def test_bulk_cells_requires_intention(client, operator, catalog):
    client.force_login(operator)
    assert client.post(CELLS_URL, {"cells": [{"sku": "PAO", "surface_ref": "web", "price_q": 1}]},
        content_type="application/json").status_code == 400


def test_bulk_cells_replays_the_same_intention(client, operator, catalog):
    client.force_login(operator)
    web_pao = _cell(client, "PAO", "web")
    body = {
        "base_revision": "batch-3",
        "expected_actor_id": operator.pk,
        "cells": [{"sku": "PAO", "surface_ref": "web", "price_q": 555,
            "base_revisions": web_pao["action"]["payload_schema"]["base_revisions"]}],
    }
    key = str(uuid4())
    first = _post(client, body, key)
    second = _post(client, body, key)
    assert first.status_code == second.status_code == 200
    assert ListingItem.objects.filter(listing__ref="web", product__sku="PAO", price_q=555).count() == 1
    receipt = client.get(CELLS_URL, {"idempotency_key": key})
    assert receipt.status_code == 200
    assert receipt.json()["outcome"] == "applied"


def test_bulk_cells_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.post(CELLS_URL, {"cells": []}, content_type="application/json").status_code == 403
