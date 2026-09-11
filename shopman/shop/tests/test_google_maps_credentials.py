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
