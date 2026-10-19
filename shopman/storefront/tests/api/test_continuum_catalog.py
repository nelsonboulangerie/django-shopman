from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker

from shopman.shop.logging import JsonLogFormatter
from shopman.shop.observability import log_catalog_observation
from shopman.storefront.continuum import REFRESH_TOPIC, refresh_head, rendered_message
from shopman.storefront.models import CatalogStructureHead
from shopman.storefront.presentation import build_catalog
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

SNAPSHOT_URL = "/api/v1/storefront/continuum/v0.2/catalog-structure/"


def _refresh():
    """O que o worker faz: monta (ou reconcilia) a cabeça do snapshot."""
    return refresh_head(channel_ref="web")


def _drain_refresh():
    """O worker de diretivas pega a reconstrução enfileirada pela escrita."""
    from shopman.orderman.models import Directive

    Directive.objects.filter(topic=REFRESH_TOPIC, status="queued").update(available_at=timezone.now())
    call_command("process_directives", limit=10)


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
        _refresh()
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
        _refresh()
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
        "Cache-Control",
        "Vary",
    ):
        assert second[name] == first[name]
    assert int(second["Continuum-Age-Ms"]) >= int(first["Continuum-Age-Ms"])


def test_conditional_get_and_head_use_weak_comparison_with_strong_response_etag(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        _refresh()
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
            "Cache-Control",
            "Vary",
        ):
            assert response[name] == first[name]
        assert int(response["Continuum-Age-Ms"]) >= int(first["Continuum-Age-Ms"])


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
    with override_settings(
        SHOPMAN_CONTINUUM=_config(),
        ALLOWED_HOSTS=["public-a.example.test", "public-b.example.test"],
    ):
        _refresh()
        first = client.get(SNAPSHOT_URL, HTTP_HOST="public-a.example.test")
        with django_assert_max_num_queries(2):
            second = client.get(SNAPSHOT_URL, HTTP_HOST="public-b.example.test")

    assert second.status_code == 200
    assert second.content == first.content
    assert second["ETag"] == first["ETag"]


def test_structural_change_advances_sequence_and_etag(client, django_capture_on_commit_callbacks):
    product = _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        _refresh()
        first = client.get(SNAPSHOT_URL)
        product.name = "Pão Francês Crocante"
        with django_capture_on_commit_callbacks(execute=True):
            product.save(update_fields=["name", "updated_at"])
        # Até o worker passar, o GET publica a cabeça suja como está, sem montar nada.
        stale = client.get(SNAPSHOT_URL)
        _drain_refresh()
        second = client.get(SNAPSHOT_URL)

    assert stale.status_code == 200
    assert stale["Continuum-Sequence"] == first["Continuum-Sequence"]
    assert int(second["Continuum-Sequence"]) == int(first["Continuum-Sequence"]) + 1
    assert second["ETag"] != first["ETag"]
    assert second.json()["data"]["state"]["items"][product.sku]["name"] == product.name


def test_burst_of_catalog_writes_queues_one_refresh(django_capture_on_commit_callbacks):
    from shopman.orderman.models import Directive

    product = _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        _refresh()
        with django_capture_on_commit_callbacks(execute=True):
            for name in ("Pão 1", "Pão 2", "Pão 3"):
                product.name = name
                product.save(update_fields=["name", "updated_at"])

    assert Directive.objects.filter(topic=REFRESH_TOPIC).count() == 1


def test_catalog_write_with_continuum_off_queues_nothing(django_capture_on_commit_callbacks):
    from shopman.orderman.models import Directive

    product = _seed_surface()
    off = _config(catalog_shadow_enabled=False, catalog_snapshot_enabled=False)
    with override_settings(SHOPMAN_CONTINUUM=off):
        with django_capture_on_commit_callbacks(execute=True):
            product.name = "Pão sem Continuum"
            product.save(update_fields=["name", "updated_at"])

    assert not Directive.objects.filter(topic=REFRESH_TOPIC).exists()


def test_snapshot_get_never_writes_and_answers_503_before_the_first_build(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        response = client.get(SNAPSHOT_URL)

    assert response.status_code == 503
    assert response["Retry-After"] == "5"
    assert response["Cache-Control"] == "private, no-store"
    assert not CatalogStructureHead.objects.exists()


def test_periodic_reconciliation_recovers_when_signal_or_callback_is_lost(client):
    product = _seed_surface()
    config = _config(reconcile_after_ms=30_000)
    with override_settings(SHOPMAN_CONTINUUM=config):
        _refresh()
        first = client.get(SNAPSHOT_URL)

        # QuerySet.update represents both a bulk producer outside model signals
        # and a source commit whose on_commit callback was lost with the process.
        type(product).objects.filter(pk=product.pk).update(name="Pão reconciliado")
        head = CatalogStructureHead.objects.get(channel_ref="web")
        CatalogStructureHead.objects.filter(pk=head.pk).update(
            dirty=False,
            verified_at=timezone.now() - timedelta(milliseconds=30_001),
        )

        # O GET não reconcilia; o ciclo do maintenance_worker sim.
        assert client.get(SNAPSHOT_URL)["ETag"] == first["ETag"]
        call_command("refresh_catalog_structure")
        reconciled = client.get(SNAPSHOT_URL)

    assert int(reconciled["Continuum-Sequence"]) == int(first["Continuum-Sequence"]) + 1
    assert reconciled["ETag"] != first["ETag"]
    assert reconciled.json()["data"]["state"]["items"][product.sku]["name"] == "Pão reconciliado"


def test_http_freshness_does_not_force_expensive_origin_reconciliation(client):
    _seed_surface()
    config = _config(fresh_for_ms=30_000, reconcile_after_ms=300_000)
    with override_settings(SHOPMAN_CONTINUUM=config):
        _refresh()
        client.get(SNAPSHOT_URL)
        head = CatalogStructureHead.objects.get(channel_ref="web")
        CatalogStructureHead.objects.filter(pk=head.pk).update(
            dirty=False,
            verified_at=timezone.now() - timedelta(milliseconds=30_001),
        )

        _refresh()
        response = client.get(SNAPSHOT_URL)

    assert response.status_code == 200
    assert response["Continuum-Sequence"] == f"{head.sequence:020d}"


def test_reconciliation_recovers_after_crash_before_head_commit(monkeypatch):
    product = _seed_surface()
    config = _config(reconcile_after_ms=0)
    with override_settings(SHOPMAN_CONTINUUM=config):
        first, _ = refresh_head(channel_ref="web")
        type(product).objects.filter(pk=product.pk).update(name="Pão pós-crash")

        original_save = CatalogStructureHead.save

        def crash_before_commit(instance, *args, **kwargs):
            if instance.pk == first.pk and instance.sequence > first.sequence:
                raise RuntimeError("simulated_process_death_before_head_commit")
            return original_save(instance, *args, **kwargs)

        monkeypatch.setattr(CatalogStructureHead, "save", crash_before_commit)
        with pytest.raises(RuntimeError, match="simulated_process_death"):
            refresh_head(channel_ref="web")

        persisted = CatalogStructureHead.objects.get(pk=first.pk)
        assert persisted.sequence == first.sequence

        monkeypatch.setattr(CatalogStructureHead, "save", original_save)
        recovered, status = refresh_head(channel_ref="web")

    assert status == "reconcile"
    assert recovered.sequence == first.sequence + 1
    assert recovered.message["data"]["state"]["items"][product.sku]["name"] == "Pão pós-crash"


def test_committed_head_is_publishable_after_cache_loss():
    product = _seed_surface()
    config = _config(reconcile_after_ms=0)
    with override_settings(SHOPMAN_CONTINUUM=config):
        first, _ = refresh_head(channel_ref="web")
        type(product).objects.filter(pk=product.pk).update(name="Pão sem cache")
        catalog = build_catalog(channel_ref="web", request=None)
        committed = refresh_head(channel_ref="web")[0]

        # A morte depois do commit e antes da resposta perde somente cache
        # descartável. A linha versionada continua suficiente para publicar.
        cache.clear()
        body, cache_status = rendered_message(committed)

    assert catalog is not None
    assert committed.sequence == first.sequence + 1
    assert cache_status == "miss"
    assert json.loads(body)["data"]["state"]["items"][product.sku]["name"] == "Pão sem cache"


def test_restore_without_disposable_head_rotates_epoch_and_rebuilds(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        _refresh()
        first = client.get(SNAPSHOT_URL)
        CatalogStructureHead.objects.all().delete()
        assert client.get(SNAPSHOT_URL).status_code == 503
        call_command("refresh_catalog_structure")
        restored = client.get(SNAPSHOT_URL)

    assert restored.status_code == 200
    assert restored["Continuum-Epoch"] != first["Continuum-Epoch"]
    assert int(restored["Continuum-Sequence"]) == 1
    assert restored["ETag"] != first["ETag"]


def test_shadow_is_side_effect_free_for_visible_contract_and_kill_switch_rolls_back(client):
    _seed_surface()
    off = _config(catalog_shadow_enabled=False, catalog_snapshot_enabled=False)
    with override_settings(SHOPMAN_CONTINUUM=off):
        baseline = client.get("/api/v1/storefront/menu/")

    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        shadow = client.get("/api/v1/storefront/menu/")
    assert shadow.status_code == 200
    assert shadow.json() == baseline.json()
    # O shadow compara e não grava: sem cabeça, fica pendente para o worker.
    assert not CatalogStructureHead.objects.exists()
    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        _refresh()
    assert CatalogStructureHead.objects.filter(channel_ref="web").exists()

    CatalogStructureHead.objects.all().delete()
    with override_settings(SHOPMAN_CONTINUUM=_config(kill_switch=True)):
        rolled_back = client.get("/api/v1/storefront/menu/")
        candidate = client.get(SNAPSHOT_URL)
    assert rolled_back.json() == baseline.json()
    assert candidate.status_code == 404
    assert not CatalogStructureHead.objects.exists()


def test_warm_shadow_reuses_canonical_projection_and_adds_one_query(client, monkeypatch):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        _refresh()
    observations = []

    from shopman.storefront import continuum
    from shopman.storefront.api import surface

    monkeypatch.setattr(
        continuum,
        "catalog_structure_state",
        lambda catalog: pytest.fail("shadow recalculou a projeção canônica"),
    )
    monkeypatch.setattr(surface, "log_catalog_observation", lambda **fields: observations.append(fields))

    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        client.get("/api/v1/storefront/menu/")
        observations.clear()
        response = client.get("/api/v1/storefront/menu/")

    assert response.status_code == 200
    assert observations[-1]["shadow_equal"] is True
    assert observations[-1]["shadow_query_count"] == 1
    assert observations[-1]["cache_status"] == "hit:hit"


def test_shadow_reports_divergence_without_rebuilding(client, monkeypatch):
    product = _seed_surface()
    observations = []

    from shopman.storefront.api import surface

    monkeypatch.setattr(surface, "log_catalog_observation", lambda **fields: observations.append(fields))
    with override_settings(SHOPMAN_CONTINUUM=_config(catalog_snapshot_enabled=False)):
        client.get("/api/v1/storefront/menu/")
        assert observations[-1]["cache_status"] == "pending"
        _refresh()
        head = CatalogStructureHead.objects.get(channel_ref="web")
        # Signal perdido: o catálogo mudou e a cabeça não soube.
        type(product).objects.filter(pk=product.pk).update(name="Pão divergente")
        client.get("/api/v1/storefront/menu/")

    assert observations[-1]["shadow_equal"] is False
    assert observations[-1]["cache_status"].startswith("diverged:")
    assert CatalogStructureHead.objects.get(pk=head.pk).sequence == head.sequence


def test_snapshot_limits_fail_closed_without_affecting_canonical_menu(client):
    _seed_surface()
    constrained = _config()
    constrained["limits"] = {**constrained["limits"], "max_decoded_response_bytes": 32}
    with override_settings(SHOPMAN_CONTINUUM=constrained):
        _refresh()
        candidate = client.get(SNAPSHOT_URL)
        canonical = client.get("/api/v1/storefront/menu/")

    assert candidate.status_code == 503
    assert candidate["Cache-Control"] == "private, no-store"
    assert canonical.status_code == 200
    assert canonical.json()["catalog"]["items"][0]["sku"] == "PAO-FRANCES"


def test_warm_read_model_has_fixed_query_budget_below_canonical_menu(client):
    _seed_surface()
    with override_settings(SHOPMAN_CONTINUUM=_config()):
        _refresh()
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
        "shopman.shop.observability.logger.info",
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
