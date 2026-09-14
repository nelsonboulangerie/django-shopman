"""Revisão conserva evidência remota e não modifica dados locais nem envia HTTP."""

import copy
import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Directive

from shopman.shop.models import Channel
from shopman.shop.services.ifood_catalog_review import build_ifood_catalog_review, validate_review_snapshot


@pytest.fixture
def snapshot():
    return {"schema_version": 1, "merchant_id": "merchant", "catalog_id": "catalog", "context": "DEFAULT",
        "captured_at": "2026-09-14T10:00:00-03:00", "source": "imported_file",
        "categories": [{"id": "category", "name": "Pães", "items": [{"id": "item", "productId": "product"}]}],
        "category_items": [{"categoryId": "category", "items": [{"id": "item", "productId": "product",
            "externalCode": "ROOT", "price": {"value": "18.50"}, "status": "AVAILABLE",
            "contextModifiers": [{"catalogContext": "DEFAULT", "externalCode": "SKU",
                "price": {"value": "21.90", "originalValue": None}, "status": "UNAVAILABLE", "itemContextId": "context-item"}]}],
            "products": [{"id": "product", "name": "Pão real", "description": "Descrição remota", "imagePath": "remote/photo.jpg", "industrialized": True}],
            "options": [{"id": "opt", "unknownFutureField": "preserved"}], "optionGroups": []}]}


def review(snapshot):
    return build_ifood_catalog_review(snapshot=snapshot, products=[SimpleNamespace(sku="SKU", name="Exemplo")],
        local_details={"SKU": {"sku": "SKU", "name": "Exemplo", "image_url": "local.jpg"}})


def test_full_context_product_photo_and_components_preserved(snapshot):
    original = copy.deepcopy(snapshot)
    result = review(snapshot)
    row, = result["items"]
    assert row["identity"]["name"] == "Pão real"
    assert row["identity"]["candidate_skus"] == ("SKU",)
    assert row["remote"]["effective_context"] == {"externalCode": "SKU", "price": {"value": "21.90", "originalValue": None},
        "status": "UNAVAILABLE", "itemContextId": "context-item"}
    assert row["remote"]["product"]["imagePath"] == "remote/photo.jpg"
    assert row["remote"]["product"]["industrialized"] is True
    assert result["remote_snapshot"] == original == snapshot
    assert result["summary"]["pending"] == 1
    assert result["write_authorized"] is False
    assert row["binding_confirmed"] is False
    result["remote_snapshot"]["category_items"][0]["options"].clear()
    assert snapshot == original


def test_missing_optional_product_is_not_filled_from_local(snapshot):
    del snapshot["category_items"][0]["products"]
    row, = review(snapshot)["items"]
    assert row["remote"]["product"] is None
    assert row["identity"]["name"] == ""
    assert "ausentes" in row["notices"][1]


@pytest.mark.parametrize("change", [
    lambda s: s.update(schema_version=True),
    lambda s: s.update(captured_at="2026-09-14T10:00:00"),
    lambda s: s.update(category_items=[]),
    lambda s: s["category_items"].append(copy.deepcopy(s["category_items"][0])),
    lambda s: s["categories"][0].update(items=[]),
    lambda s: s["category_items"][0]["items"][0].update(categoryId="other"),
    lambda s: s["category_items"][0]["items"][0].update(productId="other"),
    lambda s: s["category_items"][0].update(options={}),
])
def test_inconsistent_snapshot_rejected(snapshot, change):
    change(snapshot)
    with pytest.raises(ValueError):
        validate_review_snapshot(snapshot)


def test_invalid_context_never_shows_effective_price_or_candidate(snapshot):
    snapshot["category_items"][0]["items"][0]["contextModifiers"] = None
    row, = review(snapshot)["items"]
    assert row["remote"]["effective_context"] is None
    assert row["local_candidates"] == []


def test_shared_product_keeps_separate_items_and_ambiguous_codes(snapshot):
    detail = snapshot["category_items"][0]
    second = copy.deepcopy(detail["items"][0])
    second["id"] = "item-2"
    detail["items"].append(second)
    snapshot["categories"][0]["items"].append({"id": "item-2", "productId": "product"})
    result = review(snapshot)
    assert len(result["items"]) == 2
    assert result["summary"]["ambiguous"] == 2
    assert all(row["review_status"] == "pending" and not row["binding_confirmed"] for row in result["items"])


@pytest.mark.django_db
def test_command_only_selects_and_retains_raw_digest_and_decimal(snapshot, tmp_path):
    Channel.objects.create(ref="ifood", name="iFood")
    p = Product.objects.create(sku="SKU", name="Exemplo", base_price_q=100)
    listing = Listing.objects.create(ref="ifood", name="iFood")
    ListingItem.objects.create(listing=listing, product=p, price_q=200)
    file = tmp_path / "snapshot.json"
    file.write_text(json.dumps(snapshot).replace('"21.90"', '21.900000000000001'))
    output = StringIO()
    before = Directive.objects.count()
    with patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP proibido")), CaptureQueriesContext(connection) as queries:
        call_command("prepare_ifood_catalog_review", snapshot=str(file), channel="ifood", stdout=output)
    assert all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
    assert Directive.objects.count() == before
    result = json.loads(output.getvalue())
    assert len(result["source_file_sha256"]) == 64
    row, = result["items"]
    assert row["remote"]["effective_context"]["price"]["value"] == "21.900000000000001"
    assert row["local_candidates"][0]["base_price_q"] == 100
    assert row["local_candidates"][0]["offers"][0]["price_q"] == 200
    p.refresh_from_db()
    assert p.name == "Exemplo"


def test_bad_input_fails_before_database_without_leaking_content(tmp_path):
    file = tmp_path / "input.json"
    file.write_text('{"secret":"do-not-expose"}')
    with pytest.raises(CommandError) as error:
        call_command("prepare_ifood_catalog_review", snapshot=str(file), channel="ifood")
    assert "do-not-expose" not in str(error.value)


def test_empty_snapshot_does_not_claim_platform_completeness(snapshot):
    snapshot.update(categories=[], category_items=[])
    result = review(snapshot)
    assert result["coverage"]["internally_consistent"]
    assert not result["coverage"]["origin_verified"]
    assert not result["write_authorized"]


@pytest.mark.django_db
def test_numeric_external_code_never_coerces_into_candidate(snapshot, tmp_path):
    Channel.objects.create(ref="ifood", name="iFood")
    Product.objects.create(sku="1.25", name="Exemplo", base_price_q=100)
    item = snapshot["category_items"][0]["items"][0]
    item["externalCode"] = 1.25
    item.pop("contextModifiers")
    file = tmp_path / "numeric.json"
    file.write_text(json.dumps(snapshot))
    output = StringIO()
    call_command("prepare_ifood_catalog_review", snapshot=str(file), channel="ifood", stdout=output)
    row, = json.loads(output.getvalue())["items"]
    assert row["local_candidates"] == []
    assert row["identity"]["status"] == "missing_code"


def test_duplicate_json_keys_rejected_before_database(tmp_path):
    file = tmp_path / "duplicate.json"
    file.write_text('{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(CommandError):
        call_command("prepare_ifood_catalog_review", snapshot=str(file), channel="ifood")


@pytest.mark.django_db
def test_concurrent_product_creation_has_controlled_error(snapshot, tmp_path):
    Channel.objects.create(ref="ifood", name="iFood")
    file = tmp_path / "snapshot.json"
    file.write_text(json.dumps(snapshot))
    with patch.object(ListingItem.objects, "filter") as offers:
        offers.return_value.select_related.return_value.order_by.return_value = [SimpleNamespace(product=SimpleNamespace(sku="new"))]
        with pytest.raises(CommandError, match="mudou durante a leitura"):
            call_command("prepare_ifood_catalog_review", snapshot=str(file), channel="ifood")
