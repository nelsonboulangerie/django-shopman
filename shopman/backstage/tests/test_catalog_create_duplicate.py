"""Criar produto do zero e duplicar (7.2, onda 1): service, API e contrato.

A maior lacuna do catálogo: criar um produto novo e duplicar um existente. A
escrita reusa o escritor canônico do detalhe (intenção + revisão + recibo local)
e grava com ``save()`` para disparar a re-projeção iFood/Meta.
"""

from uuid import uuid4

import pytest
from shopman.offerman.models import Product, ProductComponent

from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import CatalogError
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
plain_staff = fixtures.plain_staff
shop = fixtures.shop
pytestmark = pytest.mark.django_db

CREATE_URL = "/api/v1/backstage/catalog/product/create/"
DUPLICATE_URL = "/api/v1/backstage/catalog/product/duplicate/"


@pytest.fixture(autouse=True)
def attribute_registry(db):
    from shopman.shop.attribute_defaults import ensure_definitions

    ensure_definitions()


def _action(client, ref, collection=""):
    actions = client.get(fixtures.MATRIX_URL, {"collection": collection}).json()["actions"]
    return next(action for action in actions if action["ref"] == ref)


def _post(client, url, body):
    return client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))


# ── contrato e gate ─────────────────────────────────────────────────────────


def test_matrix_exposes_create_action(client, operator, catalog):
    client.force_login(operator)
    action = _action(client, "create-product")
    assert action["method"] == "POST"
    assert action["idempotency"] == "required"
    assert action["payload_schema"]["base_revision"]
    assert action["payload_schema"]["expected_actor_id"] == operator.pk


@pytest.mark.parametrize("url", [CREATE_URL, DUPLICATE_URL])
def test_create_and_duplicate_require_manage_catalog(client, plain_staff, catalog, url):
    client.force_login(plain_staff)
    body = {"sku": "X", "name": "X"}
    assert client.post(url, body, content_type="application/json").status_code == 403


def test_duplicate_read_requires_manage_catalog(client, plain_staff, catalog):
    client.force_login(plain_staff)
    assert client.get(DUPLICATE_URL, {"ref": "PAO"}).status_code == 403


def test_create_requires_intention(client, operator, catalog):
    client.force_login(operator)
    assert client.post(CREATE_URL, {"sku": "X", "name": "X"}, content_type="application/json").status_code == 400


# ── criar ───────────────────────────────────────────────────────────────────


def test_create_product_from_scratch(client, operator, catalog):
    client.force_login(operator)
    action = _action(client, "create-product")
    body = {
        **action["payload_schema"],
        "sku": "SONHO",
        "name": "Sonho",
        "base_price_q": 700,
        "unit": "un",
        "short_description": "Sonho de creme",
        "keywords": ["doce"],
    }
    response = _post(client, CREATE_URL, body)
    assert response.status_code == 200, response.json()
    assert response.json()["outcome"] == "applied"
    assert response.json()["product"]["sku"] == "SONHO"

    product = Product.objects.get(sku="SONHO")
    assert product.name == "Sonho"
    assert product.base_price_q == 700
    assert product.short_description == "Sonho de creme"
    assert list(product.keywords.names()) == ["doce"]
    # Nasce fora dos canais e da curadoria: publicar e colecionar são gestos próprios.
    assert not product.listing_items.exists()
    assert not product.collection_items.exists()


def test_create_replays_the_same_intention(client, operator, catalog):
    client.force_login(operator)
    action = _action(client, "create-product")
    body = {**action["payload_schema"], "sku": "SONHO", "name": "Sonho"}
    key = str(uuid4())
    first = client.post(CREATE_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    second = client.post(CREATE_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == second.status_code == 200
    assert Product.objects.filter(sku="SONHO").count() == 1
    receipt = client.get(CREATE_URL, {"idempotency_key": key})
    assert receipt.status_code == 200
    assert receipt.json()["outcome"] == "applied"


def test_create_rejects_existing_sku(client, operator, catalog):
    client.force_login(operator)
    action = _action(client, "create-product")
    body = {**action["payload_schema"], "sku": "PAO", "name": "Outro pão"}
    response = _post(client, CREATE_URL, body)
    assert response.status_code == 400
    assert response.json()["field"] == "sku"
    assert Product.objects.filter(sku="PAO").count() == 1


def test_create_rejects_unknown_field(catalog):
    with pytest.raises(CatalogError, match="não editáveis"):
        catalog_service.create_product({"sku": "X", "name": "X", "nao_existe": 1})


def test_create_validates_the_nutrition_block(catalog):
    with pytest.raises(CatalogError):
        catalog_service.create_product({
            "sku": "X",
            "name": "X",
            "nutrition_facts": {"energy_kcal": 10},  # sem porção
        })


def test_service_create_emits_product_created(catalog, monkeypatch):
    from shopman.offerman import signals as offerman_signals

    calls = []
    monkeypatch.setattr(offerman_signals.product_created, "send", lambda **payload: calls.append(payload))
    catalog_service.create_product({"sku": "SONHO", "name": "Sonho"})
    assert [call["sku"] for call in calls] == ["SONHO"]


# ── duplicar ────────────────────────────────────────────────────────────────


def test_duplicate_snapshot_suggests_sku_and_name(client, operator, catalog):
    client.force_login(operator)
    response = client.get(DUPLICATE_URL, {"ref": "BOLO"})
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["source"] == {"sku": "BOLO", "name": "Bolo"}
    assert snapshot["suggested_sku"] == "BOLO-COPIA"
    assert snapshot["suggested_name"] == "Bolo (cópia)"
    assert snapshot["action"]["ref"] == "duplicate-product"
    assert snapshot["action"]["payload_schema"]["base_revision"]


def test_duplicate_copies_content_not_commercial_decisions(client, operator, catalog):
    from shopman.shop.services import attributes

    client.force_login(operator)
    source = catalog["bolo"]
    ProductComponent.objects.create(parent=source, component=catalog["pao"], qty=2)
    source.storage_tip = "Na geladeira"
    source.nutrition_facts = {"serving_size_g": 60, "energy_kcal": 210}
    source.save()
    attributes.set(source, "alergenos", ["glúten"], source="manual")
    attributes.set(source, "porcoes", "6 fatias", source="manual")

    snapshot = client.get(DUPLICATE_URL, {"ref": "BOLO"}).json()
    body = {
        **snapshot["action"]["payload_schema"],
        "ref": "BOLO",
        "sku": "BOLO-COPIA",
        "name": "Bolo de cenoura",
    }
    response = _post(client, DUPLICATE_URL, body)
    assert response.status_code == 200, response.json()
    assert response.json()["sku"] == "BOLO-COPIA"

    copy = Product.objects.get(sku="BOLO-COPIA")
    assert copy.name == "Bolo de cenoura"
    assert copy.base_price_q == source.base_price_q
    assert copy.unit == source.unit
    assert copy.storage_tip == "Na geladeira"
    assert copy.nutrition_facts == source.nutrition_facts
    assert list(copy.keywords.names()) == list(source.keywords.names())
    assert attributes.get(copy, "alergenos") == ["glúten"]
    assert attributes.get(copy, "porcoes") == "6 fatias"
    # Rótulo copiado congela como manual: a cópia não herdou a ficha técnica.
    assert attributes.source(copy, "alergenos") == "manual"
    assert set(copy.components.values_list("component__sku", flat=True)) == {"PAO"}
    # Não copia listing, coleção nem a decisão de publicar.
    assert not copy.listing_items.exists()
    assert not copy.collection_items.exists()
    assert copy.is_published is False
    assert copy.is_sellable is False
    # O original fica intacto.
    assert source.collection_items.exists()
    assert source.listing_items.exists()


def test_duplicate_drops_the_barcode(catalog):
    source = catalog["pao"]
    source.metadata = {**source.metadata, "social": {"gtin": "7891000053508"}, "gtin_source": "embalagem"}
    source.save()
    catalog_service.duplicate_product("PAO", {"sku": "PAO-COPIA"})
    copy = Product.objects.get(sku="PAO-COPIA")
    assert (copy.metadata.get("social") or {}).get("gtin", "") == ""
    assert "gtin_source" not in copy.metadata


def test_duplicate_conflicts_when_the_source_changed(client, operator, catalog):
    client.force_login(operator)
    snapshot = client.get(DUPLICATE_URL, {"ref": "PAO"}).json()
    body = {**snapshot["action"]["payload_schema"], "ref": "PAO", "sku": "PAO-COPIA"}
    catalog["pao"].name = "Pão reformulado"
    catalog["pao"].save()
    response = _post(client, DUPLICATE_URL, body)
    assert response.status_code == 409
    assert not Product.objects.filter(sku="PAO-COPIA").exists()


def test_duplicate_rejects_the_source_sku(catalog):
    with pytest.raises(CatalogError, match="diferente do original"):
        catalog_service.duplicate_product("PAO", {"sku": "PAO"})


def test_duplicate_rejects_existing_target_sku(catalog):
    with pytest.raises(CatalogError, match="Já existe"):
        catalog_service.duplicate_product("PAO", {"sku": "BOLO"})


# ── GTIN: rascunho com origem, correlação e foto ────────────────────────────

DRAFT_URL = "/api/v1/backstage/catalog/product/draft/"
PHOTO_URL = "/api/v1/backstage/catalog/product/photo/"
PHOTO_UPLOAD_URL = "/api/v1/backstage/catalog/product/photo/upload/"


def _ean13(base12: str) -> str:
    digits = [int(digit) for digit in base12]
    total = sum(digit * (3 if index % 2 else 1) for index, digit in enumerate(digits))
    return base12 + str((10 - total % 10) % 10)


def _fake_sources(monkeypatch):
    from shopman.shop.services import product_enrichment as enrichment

    monkeypatch.setattr(enrichment, "inert", lambda *args, **kwargs: False)
    monkeypatch.setattr(enrichment, "cosmos_token", lambda: "token")
    monkeypatch.setattr(enrichment, "fetch_cosmos", lambda gtin: {
        "description": "Geleia de morango",
        "brand": {"name": "Marca X"},
        "ncm": {"code": "20079990"},
        "net_weight": 320,
        "thumbnail": "https://exemplo/foto.jpg",
    })
    monkeypatch.setattr(enrichment, "fetch_off", lambda gtin: {
        "product_name": "Geleia",
        "brands": "Marca X",
        "ingredients_text": "morango, açúcar",
        "allergens_tags": ["en:gluten"],
    })


def test_product_draft_reports_origin_per_field(monkeypatch):
    _fake_sources(monkeypatch)
    draft = catalog_service.product_draft(_ean13("789100005350"))
    fields = draft["fields"]
    assert fields["name"]["source_label"] == "Cosmos (Bluesoft)"
    assert fields["ncm"]["value"] == "20079990"
    assert fields["allergens"]["value"] == ["glúten"]
    assert fields["ingredients_text"]["source_label"] == "Open Food Facts"
    assert draft["reference_photo"]["source"] == "cosmos"
    assert draft["reference_photo"]["license"]
    assert "correlate" in draft


def test_product_draft_rejects_bad_gtin():
    with pytest.raises(CatalogError, match="dígito verificador"):
        catalog_service.product_draft("7891000053500")


def test_draft_endpoint_returns_fields_with_origin(client, operator, catalog, monkeypatch):
    _fake_sources(monkeypatch)
    client.force_login(operator)
    response = client.post(DRAFT_URL, {"gtin": _ean13("789100005350")}, content_type="application/json")
    assert response.status_code == 200, response.json()
    draft = response.json()["draft"]
    assert draft["gtin"]
    assert draft["fields"]["ncm"]["source"] == "cosmos"
    assert draft["fields"]["brand"]["display"] == "Marca X"


def test_correlate_suggests_from_similar_products(catalog):
    catalog["pao"].metadata = {
        **(catalog["pao"].metadata or {}),
        "fiscal": {"ncm": "19059090", "profile": "padaria"},
        "social": {"brand": "Nelson"},
    }
    catalog["pao"].availability_policy = "planned_ok"
    catalog["pao"].is_batch_produced = True
    catalog["pao"].shelf_life_days = 1
    catalog["pao"].save()
    catalog["bolo"].metadata = {
        **(catalog["bolo"].metadata or {}),
        "fiscal": {"ncm": "19059090", "profile": "padaria"},
    }
    catalog["bolo"].save()
    draft = {"fields": {"ncm": {"value": "19059090"}, "brand": {"value": "Nelson"}}}
    result = catalog_service.correlate_suggestions(draft)
    assert {item["sku"] for item in result["correlates"]} == {"PAO", "BOLO"}
    by_field = {item["field"]: item["value"] for item in result["suggestions"]}
    assert by_field["availability_policy"] == "planned_ok"
    assert by_field["is_batch_produced"] is True
    assert by_field["shelf_life_days"] == 1
    assert by_field["fiscal_profile"] == "padaria"


def test_photo_enhance_off_by_default(settings):
    from shopman.backstage.services.exceptions import AiAssistNotConfigured

    settings.SHOPMAN_PRODUCT_IMAGE_ENHANCE_PROVIDER = ""
    with pytest.raises(AiAssistNotConfigured):
        catalog_service.enhance_product_photo("data:image/png;base64,AAAA")


def test_photo_enhance_is_deterministic(settings):
    import base64
    from io import BytesIO

    from PIL import Image

    settings.SHOPMAN_PRODUCT_IMAGE_ENHANCE_PROVIDER = "deterministic"
    source = Image.new("RGB", (40, 30), (200, 30, 30))
    buffer = BytesIO()
    source.save(buffer, format="PNG")
    raw = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    result = catalog_service.enhance_product_photo(raw)
    assert result["provider"] == "deterministic"
    assert result["image"].startswith("data:image/jpeg;base64,")
    output = Image.open(BytesIO(base64.b64decode(result["image"].split(",", 1)[1])))
    assert output.size == (1200, 1200)


def test_photo_endpoint_warns_when_off(client, operator, catalog):
    client.force_login(operator)
    response = client.post(PHOTO_URL, {"image": "data:image/png;base64,AAAA"}, content_type="application/json")
    assert response.status_code in (400, 503)


def _png_data_url() -> str:
    import base64
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (20, 20), (10, 120, 30)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def test_store_product_photo_uses_the_default_storage(tmp_path):
    from django.test import override_settings

    with override_settings(MEDIA_ROOT=str(tmp_path)):
        result = catalog_service.store_product_photo(_png_data_url(), filename="geleia.png")
    assert result["name"].startswith("products/geleia-")
    assert result["name"].endswith(".png")
    assert result["size"] > 0
    assert result["media_type"] == "image/png"
    assert result["name"] in result["url"]


def test_photo_upload_endpoint_stores_and_returns_url(client, operator, catalog, tmp_path):
    from django.test import override_settings

    client.force_login(operator)
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        response = client.post(
            PHOTO_UPLOAD_URL,
            {"image": _png_data_url(), "filename": "geleia.png"},
            content_type="application/json",
        )
    assert response.status_code == 200, response.json()
    assert response.json()["name"].startswith("products/geleia-")
    assert response.json()["url"].endswith(".png")


def test_photo_upload_is_degradable_when_storage_fails(monkeypatch):
    from django.core.files.storage import default_storage

    from shopman.backstage.services.exceptions import AiAssistNotConfigured

    def boom(*args, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(default_storage, "save", boom)
    with pytest.raises(AiAssistNotConfigured):
        catalog_service.store_product_photo(_png_data_url())

def test_create_with_gtin_draft_applies_and_records_origin(client, operator, catalog, monkeypatch):
    from shopman.shop.services import attributes

    _fake_sources(monkeypatch)
    client.force_login(operator)
    action = _action(client, "create-product")
    gtin = _ean13("789100005350")
    body = {
        **action["payload_schema"],
        "sku": "GELEIA",
        "name": "Geleia de morango",
        "enrichment": {
            "gtin": gtin,
            "accept": ["name", "brand", "ncm", "net_weight_g", "ingredients_text", "allergens"],
        },
    }
    response = _post(client, CREATE_URL, body)
    assert response.status_code == 200, response.json()
    applied = set(response.json()["enrichment"]["applied"])
    assert {"brand", "ncm", "net_weight_g", "ingredients_text", "allergens"} <= applied

    product = Product.objects.get(sku="GELEIA")
    assert (product.metadata.get("social") or {}).get("gtin") == gtin
    assert (product.metadata.get("social") or {}).get("brand") == "Marca X"
    assert (product.metadata.get("fiscal") or {}).get("ncm") == "20079990"
    assert product.unit_weight_g == 320
    assert product.ingredients_text == "morango, açúcar"
    assert attributes.get(product, "alergenos") == ["glúten"]
    accepted = (product.metadata.get("enrichment") or {}).get("accepted") or {}
    assert accepted["ncm"]["source"] == "cosmos"
    assert accepted["brand"]["accepted_by"] == "catalog-api"
    assert response.json()["product"]["name"] == "Geleia de morango"
