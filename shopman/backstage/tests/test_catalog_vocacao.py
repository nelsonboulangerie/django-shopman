"""Vocação do produto no painel do Gestor (UX-V1).

A vocação é a ``ProductConsumptionTag`` do SKU: mora fora do produto, serve só
ao B.I. e é editada pelo mesmo PATCH do painel, com a mesma permissão
(``shop.manage_catalog``). "" remove; o modelo não muda.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag, Reading
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
plain_staff = fixtures.plain_staff
shop = fixtures.shop
pytestmark = pytest.mark.django_db
URL = fixtures.DETAIL_URL.format(sku="PAO")


@pytest.fixture(autouse=True)
def attribute_registry(db):
    from shopman.shop.attribute_defaults import ensure_definitions

    ensure_definitions()


@pytest.fixture
def roles(db):
    return {
        "leva": ConsumptionRole.objects.create(ref="leva", label="Leva", reading=Reading.TAKEAWAY, ordering=20),
        "hibrido": ConsumptionRole.objects.create(ref="hibrido", label="Híbrido", reading=Reading.HYBRID, ordering=30),
        "antigo": ConsumptionRole.objects.create(ref="antigo", label="Antigo", is_active=False, ordering=40),
    }


def _patch(client, patch):
    body = {**client.get(URL).json()["action"]["payload_schema"], "patch": patch}
    return client.patch(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))


def test_detail_reads_vocation_and_active_choices(client, operator, catalog, roles):
    ProductConsumptionTag.objects.create(sku="PAO", role=roles["leva"])
    client.force_login(operator)
    product = client.get(URL).json()["product"]
    assert product["vocation"] == "leva"
    assert [choice["ref"] for choice in product["vocation_choices"]] == ["leva", "hibrido"]
    assert product["vocation_choices"][0]["label"] == "Leva"


def test_detail_without_tag_reads_empty_vocation(client, operator, catalog, roles):
    client.force_login(operator)
    assert client.get(URL).json()["product"]["vocation"] == ""


def test_inactive_role_in_use_stays_visible(client, operator, catalog, roles):
    ProductConsumptionTag.objects.create(sku="PAO", role=roles["antigo"])
    client.force_login(operator)
    product = client.get(URL).json()["product"]
    assert product["vocation"] == "antigo"
    assert "antigo" in [choice["ref"] for choice in product["vocation_choices"]]


def test_patch_creates_reviewed_tag_without_touching_product(client, operator, catalog, roles):
    client.force_login(operator)
    response = _patch(client, {"vocation": "hibrido"})
    assert response.status_code == 200, response.json()
    assert response.json()["product"]["vocation"] == "hibrido"
    tag = ProductConsumptionTag.objects.get(sku="PAO")
    assert tag.role == roles["hibrido"]
    assert tag.reviewed is True


def test_patch_changes_role_and_drops_old_weight(client, operator, catalog, roles):
    ProductConsumptionTag.objects.create(sku="PAO", role=roles["hibrido"], eat_in_weight=59, reviewed=False, note="medido")
    client.force_login(operator)
    assert _patch(client, {"vocation": "leva"}).status_code == 200
    tag = ProductConsumptionTag.objects.get(sku="PAO")
    assert tag.role == roles["leva"]
    assert tag.eat_in_weight is None
    assert tag.reviewed is True
    assert tag.note == "medido"


def test_patch_empty_removes_tag(client, operator, catalog, roles):
    ProductConsumptionTag.objects.create(sku="PAO", role=roles["leva"])
    client.force_login(operator)
    response = _patch(client, {"vocation": ""})
    assert response.status_code == 200
    assert response.json()["product"]["vocation"] == ""
    assert not ProductConsumptionTag.objects.filter(sku="PAO").exists()


def test_patch_vocation_with_product_field_saves_both(client, operator, catalog, roles):
    client.force_login(operator)
    assert _patch(client, {"vocation": "leva", "name": "Pão francês"}).status_code == 200
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Pão francês"
    assert ProductConsumptionTag.objects.get(sku="PAO").role == roles["leva"]


def test_failed_product_field_rolls_back_vocation(client, operator, catalog, roles):
    client.force_login(operator)
    response = _patch(client, {"vocation": "leva", "base_price_q": None})
    assert response.status_code == 400
    assert not ProductConsumptionTag.objects.filter(sku="PAO").exists()


@pytest.mark.parametrize("value", ["antigo", "nao-existe", 3])
def test_patch_rejects_unknown_or_inactive_role(client, operator, catalog, roles, value):
    client.force_login(operator)
    response = _patch(client, {"vocation": value})
    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "vocation"
    assert body["detail"].startswith("Vocação")
    assert not ProductConsumptionTag.objects.filter(sku="PAO").exists()


def test_vocation_requires_manage_catalog(client, plain_staff, operator, catalog, roles):
    client.force_login(operator)
    body = {**client.get(URL).json()["action"]["payload_schema"], "patch": {"vocation": "leva"}}
    client.force_login(plain_staff)
    body["expected_actor_id"] = plain_staff.pk
    response = client.patch(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 403
    assert not ProductConsumptionTag.objects.filter(sku="PAO").exists()


def test_matrix_marks_rows_and_lists_sellable_without_vocation(client, operator, catalog, roles):
    from shopman.offerman.models import Product

    ProductConsumptionTag.objects.create(sku="PAO", role=roles["leva"])
    Product.objects.create(sku="FORA", name="Fora de venda", unit="un", base_price_q=100, is_sellable=False)
    client.force_login(operator)
    matrix = client.get(fixtures.MATRIX_URL, {"collection": "doces"}).json()["matrix"]
    assert {row["sku"]: row["has_vocation"] for row in matrix["rows"]} == {"BOLO": False}
    # O aviso é da loja inteira, não do recorte da coleção.
    assert matrix["vocation_pending"] == [{"sku": "BOLO", "name": "Bolo"}]
