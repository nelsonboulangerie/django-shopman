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
    "SKU;Produto;Preço (R$);Publicado;À venda;Coleção (informativa);Canal: Loja online\n"
    "IMPORTADO;Pão importado;7,50;Sim;Sim;;À venda\n"
    "PAO;Pão novo;6,00;Sim;Sim;Pães;À venda\n"
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
    with pytest.raises(CatalogError, match="coluna SKU"):
        catalog_service.preview_product_import({"csv": "Produto;Preço (R$)\nPão;5"}, actor_id=1)


def test_import_rejects_unknown_header_instead_of_ignoring_typo(catalog):
    with pytest.raises(CatalogError, match="colunas desconhecidas: Preco"):
        catalog_service.preview_product_import({"csv": "SKU;Produto;Preco\nPAO;Pão;5"}, actor_id=1)


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
    preview = client.post(IMPORT_URL, {"csv": CSV, "preview": True}, content_type="application/json").json()["preview"]
    body = {"csv": CSV, "base_revision": preview["base_revision"], "expected_actor_id": operator.pk}
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


def test_apply_rejects_preview_after_target_product_changes(client, operator, catalog):
    client.force_login(operator)
    preview = client.post(IMPORT_URL, {"csv": CSV, "preview": True}, content_type="application/json").json()["preview"]
    catalog["pao"].name = "Mudança concorrente"
    catalog["pao"].save(update_fields=["name", "updated_at"])
    response = client.post(
        IMPORT_URL,
        {"csv": CSV, "base_revision": preview["base_revision"], "expected_actor_id": operator.pk},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert response.status_code == 409
    assert response.json()["outcome"] == "not_applied"
    assert "mudou desde a prévia" in response.json()["detail"]
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Mudança concorrente"


def test_apply_with_row_errors_returns_not_applied_receipt(client, operator, catalog):
    client.force_login(operator)
    invalid_csv = CSV.replace("7,50", "preço inválido")
    preview = client.post(IMPORT_URL, {"csv": invalid_csv, "preview": True}, content_type="application/json").json()["preview"]
    response = client.post(
        IMPORT_URL,
        {"csv": invalid_csv, "base_revision": preview["base_revision"], "expected_actor_id": operator.pk},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert response.status_code == 422
    receipt = response.json()
    assert receipt["ok"] is False
    assert receipt["outcome"] == "not_applied"
    assert receipt["errors"]
    assert not Product.objects.filter(sku="IMPORTADO").exists()


def test_import_apply_requires_intention(client, operator, catalog):
    client.force_login(operator)
    assert client.post(IMPORT_URL, {"csv": CSV}, content_type="application/json").status_code == 400


def test_import_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.post(IMPORT_URL, {"csv": CSV}, content_type="application/json").status_code == 403
