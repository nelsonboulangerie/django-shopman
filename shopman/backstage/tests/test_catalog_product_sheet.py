"""Tabelão de produtos: leitura, lote linha a linha e duplicar vários."""

from uuid import uuid4

import pytest
from shopman.offerman.models import Product

from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
plain_staff = fixtures.plain_staff
shop = fixtures.shop
pytestmark = pytest.mark.django_db

SHEET_URL = "/api/v1/backstage/catalog/products/sheet/"
DUPLICATE_URL = "/api/v1/backstage/catalog/products/duplicate/"


def _row(client, sku):
    sheet = client.get(SHEET_URL).json()
    return next(row for row in sheet["rows"] if row["sku"] == sku)


def _post(client, url, body, key=None):
    return client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))


def _body(operator, rows):
    return {"base_revision": "sheet-1", "expected_actor_id": operator.pk, "rows": rows}


def test_sheet_revisions_are_the_same_the_product_panel_signs(client, operator, catalog):
    client.force_login(operator)
    sheet = client.get(SHEET_URL).json()
    assert {"key", "name", "requires_cest"} <= set(sheet["fiscal_profiles"][0])
    row = next(item for item in sheet["rows"] if item["sku"] == "PAO")
    panel = catalog_service.product_field_revisions(catalog_service.get_product_detail("PAO"))
    for path, revision in row["revisions"].items():
        assert panel[path] == revision, path


def test_sheet_applies_rows_and_reports_errors_per_row(client, operator, catalog):
    client.force_login(operator)
    pao, bolo = _row(client, "PAO"), _row(client, "BOLO")
    response = _post(client, SHEET_URL, _body(operator, [
        {"sku": "PAO", "patch": {"name": "Pão da casa", "base_price_q": 1234},
         "base_revisions": {"name": pao["revisions"]["name"], "base_price_q": pao["revisions"]["base_price_q"]}},
        {"sku": "BOLO", "patch": {"fiscal": {"ncm": "123"}},
         "base_revisions": {"fiscal.ncm": bolo["revisions"]["fiscal.ncm"]}},
    ]))
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert [item["sku"] for item in payload["applied"]] == ["PAO"]
    assert payload["applied"][0]["row"]["name"] == "Pão da casa"
    assert [(item["index"], item["sku"]) for item in payload["errors"]] == [(1, "BOLO")]
    product = Product.objects.get(sku="PAO")
    assert (product.name, product.base_price_q) == ("Pão da casa", 1234)
    assert not (Product.objects.get(sku="BOLO").metadata or {}).get("fiscal")


def test_sheet_conflict_names_the_field_and_keeps_the_rest(client, operator, catalog):
    client.force_login(operator)
    pao, bolo = _row(client, "PAO"), _row(client, "BOLO")
    Product.objects.filter(sku="PAO").update(name="Mudou por fora")
    response = _post(client, SHEET_URL, _body(operator, [
        {"sku": "PAO", "patch": {"name": "Meu nome"}, "base_revisions": {"name": pao["revisions"]["name"]}},
        {"sku": "BOLO", "patch": {"short_description": "Fofinho"},
         "base_revisions": {"short_description": bolo["revisions"]["short_description"]}},
    ]))
    payload = response.json()
    assert payload["conflicts"][0]["conflicting_fields"] == ["name"]
    assert [item["sku"] for item in payload["applied"]] == ["BOLO"]
    assert Product.objects.get(sku="PAO").name == "Mudou por fora"


def test_sheet_refuses_fields_outside_the_sheet(client, operator, catalog):
    client.force_login(operator)
    pao = _row(client, "PAO")
    response = _post(client, SHEET_URL, _body(operator, [
        {"sku": "PAO", "patch": {"is_published": False}, "base_revisions": pao["revisions"]},
    ]))
    assert response.status_code == 400
    assert Product.objects.get(sku="PAO").is_published is True


def test_sheet_and_duplicate_need_the_catalog_permission(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.get(SHEET_URL).status_code == 403
    response = _post(client, DUPLICATE_URL, {"base_revision": "d", "expected_actor_id": plain_staff.pk,
        "products": [{"sku": "PAO"}]})
    assert response.status_code == 403


def test_duplicate_many_creates_hidden_copies_and_reports_missing(client, operator, catalog):
    client.force_login(operator)
    response = _post(client, DUPLICATE_URL, {"base_revision": "dup-1", "expected_actor_id": operator.pk,
        "products": [{"sku": "PAO"}, {"sku": "NAO-EXISTE"}, {"sku": "BOLO"}]})
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert [(item["sku"], item["copy_sku"]) for item in payload["applied"]] == [("PAO", "PAO-COPIA"), ("BOLO", "BOLO-COPIA")]
    assert [item["sku"] for item in payload["errors"]] == ["NAO-EXISTE"]
    copy = Product.objects.get(sku="PAO-COPIA")
    assert (copy.is_published, copy.is_sellable) == (False, False)
    assert copy.name.endswith("(cópia)")
