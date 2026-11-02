"""WP-RELEASE-01 R1: o endereço de versão do Django e a equivalência da sonda."""

from __future__ import annotations

import subprocess

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import Client, RequestFactory

from shopman.shop.middleware import APIVersionHeaderMiddleware
from shopman.shop.watchman_release import component_unchanged_since

SHA = "c" * 40
RELEASE_ID = "20261102-1403-ccccccc"


@pytest.fixture
def release_env(monkeypatch):
    monkeypatch.setenv("SHOPMAN_BUILD_SHA", SHA)
    monkeypatch.setenv("SHOPMAN_RELEASE_ID", RELEASE_ID)
    monkeypatch.setenv("SHOPMAN_RELEASE_COMPONENT", "web")


def test_release_address_is_mounted_beside_the_probes(release_env):
    # Sem `django_db` de propósito: qualquer consulta ao banco na pilha inteira
    # (middleware incluído) reprovaria este teste. O endereço é constante.
    response = Client().get("/health/release/")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "component": "web",
        "release_id": RELEASE_ID,
        "build_sha": SHA,
    }
    assert response["Cache-Control"] == "no-store"


def test_api_responses_name_the_release(release_env):
    middleware = APIVersionHeaderMiddleware(lambda request: HttpResponse("ok"))

    api = middleware(RequestFactory().get("/api/v1/storefront/menu/"))
    admin = middleware(RequestFactory().get("/admin/"))

    assert api["X-Shopman-Release"] == RELEASE_ID
    assert "X-Shopman-Release" not in admin


def test_api_responses_without_identity_carry_no_release_header(monkeypatch):
    monkeypatch.delenv("SHOPMAN_RELEASE_ID", raising=False)
    middleware = APIVersionHeaderMiddleware(lambda request: HttpResponse("ok"))

    assert "X-Shopman-Release" not in middleware(RequestFactory().get("/api/v1/x/"))


def test_release_probe_targets_are_exactly_the_deploy_components():
    targets = [t["id"] for t in settings.WATCHMAN["RELEASE_IDENTITY"]["targets"]]
    assert targets == ["web", "storefront-nuxt", "operator-floor", "operator-office"]
    assert settings.WATCHMAN["PROFILES"]["release"] == ["release_identity"]


# ── Equivalência: usa o git e a tabela do deploy_components ───────────────────


def _rev(ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=settings.BASE_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_same_commit_is_equivalent_for_every_component():
    head = _rev("HEAD")
    for component in ("web", "storefront-nuxt", "operator-floor", "operator-office"):
        assert component_unchanged_since(component, head, head) is True


def test_live_ahead_of_expected_is_not_equivalent():
    # O vivo não é ancestral do esperado: outro ramo ou histórico reescrito.
    try:
        parent = _rev("HEAD~1")
    except subprocess.CalledProcessError:
        pytest.skip("checkout raso: sem o commit anterior para comparar")
    assert component_unchanged_since("web", _rev("HEAD"), parent) is False


def test_unknown_commit_or_component_is_unknown():
    head = _rev("HEAD")
    assert component_unchanged_since("web", "f" * 40, head) is None
    assert component_unchanged_since("pdv-antigo", head, head) is None
