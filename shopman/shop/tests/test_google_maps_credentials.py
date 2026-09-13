from __future__ import annotations

from shopman.shop.services.google_maps_credentials import browser_api_key, server_api_key


def test_split_credentials_take_precedence_over_legacy_key(settings) -> None:
    settings.GOOGLE_MAPS_API_KEY = "legacy"
    settings.GOOGLE_MAPS_BROWSER_API_KEY = "browser-only"
    settings.GOOGLE_MAPS_SERVER_API_KEY = "server-only"

    assert browser_api_key() == "browser-only"
    assert server_api_key() == "server-only"


def test_legacy_key_is_a_rollout_fallback(settings) -> None:
    settings.GOOGLE_MAPS_API_KEY = "legacy"
    settings.GOOGLE_MAPS_BROWSER_API_KEY = ""
    settings.GOOGLE_MAPS_SERVER_API_KEY = ""

    assert browser_api_key() == "legacy"
    assert server_api_key() == "legacy"


def test_production_never_uses_legacy_fallback(settings):
    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.GOOGLE_MAPS_API_KEY = "legacy-server-secret"
    settings.GOOGLE_MAPS_BROWSER_API_KEY = ""
    settings.GOOGLE_MAPS_SERVER_API_KEY = ""
    assert browser_api_key() == server_api_key() == ""


def test_shared_explicit_credential_fails_closed(settings):
    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.GOOGLE_MAPS_API_KEY = ""
    settings.GOOGLE_MAPS_BROWSER_API_KEY = "shared-secret"
    settings.GOOGLE_MAPS_SERVER_API_KEY = "shared-secret"
    assert browser_api_key() == server_api_key() == ""


def test_distinct_production_credentials_reach_only_their_destination(settings):
    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.GOOGLE_MAPS_API_KEY = ""
    settings.GOOGLE_MAPS_BROWSER_API_KEY = "public-browser"
    settings.GOOGLE_MAPS_SERVER_API_KEY = "private-server"
    assert browser_api_key() == "public-browser"
    assert server_api_key() == "private-server"


def test_deploy_check_refuses_shared_maps_credentials_without_leaking_them(settings):
    from shopman.shop.checks import check_google_maps_credential_boundary

    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.GOOGLE_MAPS_API_KEY = "private-legacy-secret"
    errors = check_google_maps_credential_boundary(None)
    assert [error.id for error in errors] == ["SHOPMAN_E023"]
    assert "private-legacy-secret" not in str(errors)
