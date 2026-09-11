"""Tests for explicit live/ready probes and their compatibility aliases."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.views.health import _LOCMEM_BACKEND, ProbeRateLimiter


@pytest.fixture
def client():
    return Client()


def test_live_is_process_only_when_all_dependencies_are_down(client):
    with (
        patch("shopman.shop.views.health._check_database") as database,
        patch("shopman.shop.views.health._check_cache") as cache,
        patch("shopman.shop.views.health._check_migrations") as migrations,
        patch("shopman.shop.views.health._check_queue") as queue,
    ):
        response = client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"process": "ok"}}
    database.assert_not_called()
    cache.assert_not_called()
    migrations.assert_not_called()
    queue.assert_not_called()


def test_legacy_health_alias_keeps_the_safe_liveness_contract(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json()["checks"] == {"process": "ok"}


def test_ready_ok(client, db):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"] == {
        "database": "ok",
        "cache": (
            "skipped"
            if settings.CACHES.get("default", {}).get("BACKEND") == _LOCMEM_BACKEND
            else "ok"
        ),
        "migrations": "ok",
        "queue": "ok",
    }


def test_legacy_ready_alias_keeps_dependency_contract(client, db):
    response = client.get(reverse("ready"))

    assert response.status_code == 200
    assert set(response.json()["checks"]) == {
        "database",
        "cache",
        "migrations",
        "queue",
    }


@override_settings(CACHES={"default": {"BACKEND": _LOCMEM_BACKEND}})
def test_ready_cache_skipped_with_locmem(client, db):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["checks"]["cache"] == "skipped"


@pytest.mark.parametrize(
    ("checker", "reason"),
    [
        ("_check_database", "OperationalError"),
        ("_check_migrations", "37 pending"),
        ("_check_queue", "provider response must never be public"),
    ],
)
def test_ready_dependency_failure_is_503_without_public_detail(
    client,
    db,
    checker,
    reason,
):
    with patch(
        f"shopman.shop.views.health.{checker}",
        return_value=("fail", reason),
    ):
        response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert reason not in response.content.decode()
    assert payload["checks"][checker.removeprefix("_check_")] == "fail"


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
def test_ready_cache_roundtrip_failure_is_503_and_sanitized(client, db):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json()["checks"]["cache"] == "fail"
    assert "roundtrip" not in response.content.decode()


def test_ready_detects_overdue_queue_without_calling_provider(client, db):
    Directive.objects.create(
        topic="notification.send",
        status="queued",
        payload={},
        available_at=timezone.now() - timedelta(seconds=31),
    )
    with patch(
        "shopman.orderman.worker_heartbeat.last_beat",
        return_value=None,
    ):
        response = client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json()["checks"]["queue"] == "fail"
    assert "worker" not in response.content.decode()


def test_live_does_not_flap_when_ready_queue_is_degraded(client, db):
    Directive.objects.create(
        topic="notification.send",
        status="queued",
        payload={},
        available_at=timezone.now() - timedelta(seconds=31),
    )
    with patch("shopman.orderman.worker_heartbeat.last_beat", return_value=None):
        assert client.get(reverse("health-ready")).status_code == 503
    assert client.get(reverse("health-live")).status_code == 200


@override_settings(
    ALLOWED_HOSTS=["shopman-staging.ondigitalocean.app"],
    SECURE_SSL_REDIRECT=True,
)
def test_app_platform_probe_host_reaches_explicit_ready(client, db):
    response = client.get(
        reverse("health-ready"),
        HTTP_HOST="100.127.25.212:8000",
    )

    assert response.status_code == 200


@override_settings(ALLOWED_HOSTS=["shopman-staging.ondigitalocean.app"])
def test_app_platform_probe_host_does_not_bypass_business_routes(client, db):
    response = client.get(
        "/api/v1/storefront/menu/",
        HTTP_HOST="100.127.25.212:8000",
    )

    assert response.status_code == 400


def test_probe_no_csrf_required(client):
    response = client.post(reverse("health-live"))

    assert response.status_code == 405


def test_live_fast_p95(client):
    timings = []
    for _ in range(20):
        start = time.perf_counter()
        client.get(reverse("health-live"))
        timings.append(time.perf_counter() - start)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    assert p95 < 0.5, f"/health/live/ p95={p95:.3f}s exceeds 500ms budget"


def test_live_has_zero_queries_and_tiny_payload(client, db, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get(reverse("health-live"))

    assert len(response.content) <= 128


def test_ready_has_bounded_queries_and_payload(client, db, django_assert_max_num_queries):
    with django_assert_max_num_queries(10):
        response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert len(response.content) <= 512


@pytest.mark.parametrize("route", ["health-live", "health-ready"])
def test_probe_response_is_not_cacheable(client, db, route):
    response = client.get(reverse(route))

    assert response["Cache-Control"] == "no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_probe_rate_limiter_is_bounded_and_resets_without_cache_dependency():
    now = [100.0]
    limiter = ProbeRateLimiter(
        limit=2,
        window_seconds=60,
        max_clients=2,
        clock=lambda: now[0],
    )

    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True
    assert limiter.allow("c") is True
    assert len(limiter._buckets) == 2
    now[0] += 60
    assert limiter.allow("a") is True


def test_probe_route_enforces_rate_limit_with_retry_after(client):
    limiter = ProbeRateLimiter(limit=2)
    with patch("shopman.shop.views.health._probe_rate_limiter", limiter):
        assert client.get(reverse("health-live")).status_code == 200
        assert client.get(reverse("health-live")).status_code == 200
        response = client.get(reverse("health-live"))

    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert response.json() == {
        "status": "error",
        "checks": {"rate_limit": "fail"},
    }


def test_ready_error_never_leaks_stacktrace_or_reason(client, db):
    with patch(
        "shopman.shop.views.health._check_database",
        return_value=("fail", "OperationalError: secret-host.internal"),
    ):
        response = client.get(reverse("health-ready"))

    body = response.content.decode()
    assert "Traceback" not in body
    assert "shopman/shop/views/health.py" not in body
    assert "OperationalError" not in body
    assert "secret-host.internal" not in body
    assert set(json.loads(body)) == {"status", "checks"}
