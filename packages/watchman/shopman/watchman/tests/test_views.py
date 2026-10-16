import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_live_probe_is_small_and_cache_safe(client):
    response = client.get("/health/live/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"process": "pass"}}
    assert response["Cache-Control"] == "no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


@override_settings(
    WATCHMAN={
        "CHECKS": ["shopman.watchman.tests.fixtures.FailCheck"],
        "PROFILES": {"liveness": ["failure"], "readiness": ["failure"], "diagnostic": ["failure"]},
    }
)
def test_explicit_failure_returns_503_without_private_evidence(client):
    response = client.get("/health/live/")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "checks": {"failure": "fail"}}
    assert b"private" not in response.content


@override_settings(
    WATCHMAN={
        "CHECKS": ["shopman.watchman.tests.fixtures.ErrorCheck"],
        "PROFILES": {"liveness": ["error"], "readiness": ["error"], "diagnostic": ["error"]},
    }
)
def test_observer_error_never_restarts_the_observed_process(client):
    response = client.get("/health/live/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"error": "unknown"}}


def test_status_requires_staff(client):
    assert client.get("/health/status/").status_code == 403

    user = get_user_model().objects.create_user(username="operator", password="secret", is_staff=False)
    client.force_login(user)
    assert client.get("/health/status/").status_code == 403


def test_staff_status_includes_versioned_diagnostics(client):
    user = get_user_model().objects.create_user(username="owner", password="secret", is_staff=True)
    client.force_login(user)

    response = client.get("/health/status/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["profile"] == "diagnostic"
    assert payload["checks"][0]["id"] == "process"
    assert "evidence" in payload["checks"][0]
