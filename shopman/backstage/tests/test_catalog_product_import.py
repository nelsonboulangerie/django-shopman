"""Import CSV de produto (pt-BR): previa sem gravar e aplicacao por linha (fatia C3)."""

from uuid import uuid4

import pytest
from shopman.offerman.models import Product

from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import CatalogError
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
plain_staff = fixtures.plain_staff
shop = fixtures.shop
pytestmark = pytest.mark.django_db

IMPORT_URL = "/api/v1/backstage/catalog/product/import/"

CSV = (
    "sku;name;base_price_q;unit;availability_policy;is_published;is_sellable;shelf_life_days\n"
    "IMPORTADO;Pão importado;7,50;un;planned_ok;sim;sim;\n"
    "PAO;Pão novo;6,00;un;planned_ok;1;1;\n"
)


def test_preview_validates_and_does_not_write(catalog):
    result = catalog_service.preview_product_import({"csv": CSV}, actor_id=1)
    assert result["dry_run"] is True
    assert result["rows"] == 2
    assert result["errors"] == []
    assert result["totals"]["new"] >= 1
    assert result["totals"]["update"] >= 1
    actions = {change["sku"]: change["action"] for change in result["changes"]}
    assert actions["IMPORTADO"] == "new"
    assert actions["PAO"] == "update"
    # Nada foi gravado.
    assert not Product.objects.filter(sku="IMPORTADO").exists()
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].base_price_q == 500


def test_preview_reports_error_per_row(catalog):
    result = catalog_service.preview_product_import(
        {"csv": CSV.replace("7,50", "abc")}, actor_id=1
    )
    assert result["errors"], result
    assert result["errors"][0]["row"] == 1
    assert not Product.objects.filter(sku="IMPORTADO").exists()


def test_import_requires_the_sku_column(catalog):
    with pytest.raises(CatalogError, match="coluna sku"):
        catalog_service.preview_product_import({"csv": "name;price\nPão;5"}, actor_id=1)


def test_preview_endpoint_returns_changes(client, operator, catalog):
    client.force_login(operator)
    response = client.post(
        IMPORT_URL, {"csv": CSV, "preview": True}, content_type="application/json"
    )
    assert response.status_code == 200, response.json()
    preview = response.json()["preview"]
    assert preview["dry_run"] is True
    assert preview["errors"] == []
    assert {change["sku"] for change in preview["changes"]} == {"IMPORTADO", "PAO"}


def test_apply_import_upserts_by_sku(client, operator, catalog):
    client.force_login(operator)
    body = {"csv": CSV, "base_revision": "import-1", "expected_actor_id": operator.pk}
    response = client.post(
        IMPORT_URL,
        body,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert response.status_code == 200, response.json()
    assert response.json()["outcome"] == "applied"

    created = Product.objects.get(sku="IMPORTADO")
    assert created.name == "Pão importado"
    assert created.base_price_q == 750  # "7,50" em centavos
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Pão novo"
    assert catalog["pao"].base_price_q == 600


def test_import_apply_requires_intention(client, operator, catalog):
    client.force_login(operator)
    assert client.post(IMPORT_URL, {"csv": CSV}, content_type="application/json").status_code == 400


def test_import_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.post(IMPORT_URL, {"csv": CSV}, content_type="application/json").status_code == 403
