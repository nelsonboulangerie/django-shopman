from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from jsonschema import Draft202012Validator, FormatChecker

from shopman.shop.logging import JsonLogFormatter
from shopman.storefront.models import CatalogStructureHead
from shopman.storefront.observability import log_catalog_observation
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

SNAPSHOT_URL = "/api/v1/storefront/continuum/v0.2/catalog-structure/"


def _config(**overrides):
    config = dict(settings.SHOPMAN_CONTINUUM)
    config.update({
        "catalog_shadow_enabled": True,
        "catalog_snapshot_enabled": True,
        "kill_switch": False,
    })
    config.update(overrides)
    return config


def test_public_snapshot_is_credentialless_versioned_and_schema_valid(client):
    _seed_surface()
    cache.clear()

    with override_settings(SHOPMAN_CONTINUUM=_config()):
        response = client.get(SNAPSHOT_URL, HTTP_ACCEPT="application/cloudevents+json")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/cloudevents+json")
    assert response["Cache-Control"].startswith("public,")
    assert response["Vary"] == "Accept"
    assert not response.cookies
    assert "projection;dur=" in response["Server-Timing"]
    assert "db;dur=" in response["Server-Timing"]
    for name in (
        "ETag",
        "Continuum-Stream",
        "Continuum-Epoch",
        "Continuum-Sequence",
        "Continuum-State-Token",
        "Continuum-State-Digest",
        "Continuum-Fresh-For-Ms",
        "Continuum-Stale-If-Error-Ms",
        "Continuum-Age-Ms",
    ):
        assert response[name]

    document = response.json()
    schema_path = Path(settings.BASE_DIR) / "contracts/continuum/v0.2/message.schema.json"
    schema = json.loads(schema_path.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    assert document["data"]["state"]["items"]["PAO-FRANCES"]["name"] == "Pão Francês"
    assert "base_price_q" not in document["data"]["state"]["items"]["PAO-FRANCES"]
    assert "availability" not in document["data"]["state"]["items"]["PAO-FRANCES"]


def test_conditional_get_repeats_complete_tuple_without_regenerating_body(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        first = client.get(SNAPSHOT_URL)
        second = client.get(SNAPSHOT_URL, HTTP_IF_NONE_MATCH=first["ETag"])

    assert second.status_code == 304
    assert second.content == b""
    for name in (
        "ETag",
        "Continuum-Stream",
        "Continuum-Epoch",
        "Continuum-Sequence",
        "Continuum-State-Token",
        "Continuum-State-Digest",
        "Continuum-Fresh-For-Ms",
        "Continuum-Stale-If-Error-Ms",
        "Continuum-Age-Ms",
        "Cache-Control",
        "Vary",
    ):
        assert second[name] == first[name]


def test_conditional_get_and_head_use_weak_comparison_with_strong_response_etag(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        first = client.get(SNAPSHOT_URL)
        weak_validator = f"W/{first['ETag']}"
        conditional_get = client.get(SNAPSHOT_URL, HTTP_IF_NONE_MATCH=weak_validator)
        conditional_head = client.head(SNAPSHOT_URL, HTTP_IF_NONE_MATCH=weak_validator)

    assert not first["ETag"].startswith("W/")
    for response in (conditional_get, conditional_head):
        assert response.status_code == 304
        assert response.content == b""
        for name in (
            "ETag",
            "Continuum-Stream",
            "Continuum-Epoch",
            "Continuum-Sequence",
            "Continuum-State-Token",
            "Continuum-State-Digest",
            "Continuum-Fresh-For-Ms",
            "Continuum-Stale-If-Error-Ms",
            "Continuum-Age-Ms",
            "Cache-Control",
            "Vary",
        ):
            assert response[name] == first[name]


def test_public_snapshot_rejects_every_audience_dimension_before_lookup(client, django_assert_num_queries):
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        with django_assert_num_queries(0):
            cookie = client.get(SNAPSHOT_URL, HTTP_COOKIE="sessionid=secret")
        with django_assert_num_queries(0):
            bearer = client.get(SNAPSHOT_URL, HTTP_AUTHORIZATION="Bearer secret")
        with django_assert_num_queries(0):
            query = client.get(f"{SNAPSHOT_URL}?cohort=candidate")

    assert [cookie.status_code, bearer.status_code, query.status_code] == [400, 400, 400]
    assert all(response["Cache-Control"] == "private, no-store" for response in (cookie, bearer, query))
    assert not CatalogStructureHead.objects.exists()


def test_public_snapshot_bytes_do_not_vary_by_host_and_warm_path_is_fixed(client, django_assert_max_num_queries):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        first = client.get(SNAPSHOT_URL, HTTP_HOST="public-a.example.test")
        with django_assert_max_num_queries(2):
            second = client.get(SNAPSHOT_URL, HTTP_HOST="public-b.example.test")

    assert second.status_code == 200
    assert second.content == first.content
    assert second["ETag"] == first["ETag"]


def test_structural_change_advances_sequence_and_etag(client, django_capture_on_commit_callbacks):
    product = _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        first = client.get(SNAPSHOT_URL)
        product.name = "Pão Francês Crocante"
        with django_capture_on_commit_callbacks(execute=True):
            product.save(update_fields=["name", "updated_at"])
        second = client.get(SNAPSHOT_URL)

    assert int(second["Continuum-Sequence"]) == int(first["Continuum-Sequence"]) + 1
    assert second["ETag"] != first["ETag"]
    assert second.json()["data"]["state"]["items"][product.sku]["name"] == product.name


def test_shadow_is_side_effect_free_for_visible_contract_and_kill_switch_rolls_back(client):
    _seed_surface()
    off = _config(catalog_shadow_enabled=False, catalog_snapshot_enabled=False)
    with override_settings(SHOPMAN_CONTINUUM=off):
        baseline = client.get("/api/v1/storefront/menu/")

    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        shadow = client.get("/api/v1/storefront/menu/")
    assert shadow.status_code == 200
    assert shadow.json() == baseline.json()
    assert CatalogStructureHead.objects.filter(channel_ref="web").exists()

    CatalogStructureHead.objects.all().delete()
    with override_settings(SHOPMAN_CONTINUUM=_config(kill_switch=True)):
        rolled_back = client.get("/api/v1/storefront/menu/")
        candidate = client.get(SNAPSHOT_URL)
    assert rolled_back.json() == baseline.json()
    assert candidate.status_code == 404
    assert not CatalogStructureHead.objects.exists()


def test_snapshot_limits_fail_closed_without_affecting_canonical_menu(client):
    _seed_surface()
    constrained = _config()
    constrained["limits"] = {**constrained["limits"], "max_decoded_response_bytes": 32}
    with override_settings(SHOPMAN_CONTINUUM=constrained):
        candidate = client.get(SNAPSHOT_URL)
        canonical = client.get("/api/v1/storefront/menu/")

    assert candidate.status_code == 503
    assert candidate["Cache-Control"] == "private, no-store"
    assert canonical.status_code == 200
    assert canonical.json()["catalog"]["items"][0]["sku"] == "PAO-FRANCES"


def test_warm_read_model_has_fixed_query_budget_below_canonical_menu(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        client.get(SNAPSHOT_URL)
        with CaptureQueriesContext(connection) as candidate_queries:
            candidate = client.get(SNAPSHOT_URL)
        with CaptureQueriesContext(connection) as canonical_queries:
            canonical = client.get("/api/v1/storefront/menu/")

    assert candidate.status_code == canonical.status_code == 200
    assert len(candidate_queries) <= 2
    assert len(candidate_queries) < len(canonical_queries)


def test_observability_keeps_numeric_metrics_structured_and_allowlisted(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "shopman.storefront.observability.logger.info",
        lambda message, *, extra: captured.update(message=message, extra=extra),
    )
    log_catalog_observation(
        path="storefront_menu",
        projection_ms=12.34,
        query_count=7,
        forbidden_payload="customer@example.test",
    )

    record = logging.makeLogRecord({"msg": captured["message"], **captured["extra"]})
    document = json.loads(JsonLogFormatter().format(record))
    assert document["message"] == "storefront_catalog_observation"
    assert document["projection_ms"] == 12.34
    assert document["query_count"] == 7
    assert "forbidden_payload" not in document
