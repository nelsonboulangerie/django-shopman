"""Geocoding reverso tem teto diário GLOBAL de custo, e falha fechado.

O endpoint público ``/api/v1/geocode/reverse/`` tinha só 30/min por IP: mil IPs
fazem mil chamadas pagas ao Google por minuto, sem teto nenhum no dia. Agora
cada chamada que vai ao Google gasta de um contador diário compartilhado
(``SHOPMAN_GEOCODE_REVERSE_DAILY_LIMIT``); passado o teto, recusa com mensagem
clara até a virada do dia.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import geocoding
from shopman.shop.services.geocoding import GeocodingDailyLimitReached, reverse_geocode

_OK = {
    "status": "OK",
    "results": [
        {
            "formatted_address": "Rua A, 1, Londrina - PR",
            "address_components": [],
            "geometry": {"location": {"lat": -23.3, "lng": -51.1}},
            "place_id": "p1",
        }
    ],
}


class _FakeResponse:
    def read(self) -> bytes:
        return json.dumps(_OK).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _setup(settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    settings.GOOGLE_MAPS_BROWSER_API_KEY = ""
    settings.GOOGLE_MAPS_SERVER_API_KEY = ""
    settings.SHOPMAN_GEOCODE_REVERSE_DAILY_LIMIT = 3
    cache.clear()
    yield
    cache.clear()


def _google():
    return patch("shopman.shop.services.geocoding.urllib.request.urlopen", return_value=_FakeResponse())


@pytest.mark.django_db
def test_calls_past_the_daily_cap_never_reach_google():
    with _google() as urlopen:
        for i in range(3):
            reverse_geocode(-23.0 - i, -51.0)
        with pytest.raises(GeocodingDailyLimitReached):
            reverse_geocode(-24.5, -51.0)
    assert urlopen.call_count == 3


@pytest.mark.django_db
def test_cache_hit_does_not_spend_the_budget():
    with _google() as urlopen:
        for _ in range(5):
            reverse_geocode(-23.0, -51.0)
    assert urlopen.call_count == 1


@pytest.mark.django_db
def test_crossing_the_cap_alerts_once():
    with _google():
        for i in range(3):
            reverse_geocode(-23.0 - i, -51.0)
        for i in range(3):
            with pytest.raises(GeocodingDailyLimitReached):
                reverse_geocode(-30.0 - i, -51.0)
    alerts = OperatorAlert.objects.filter(type="integration_failed")
    assert alerts.count() == 1
    assert "teto diário" in alerts.first().message


@pytest.mark.django_db
def test_unreadable_counter_fails_closed(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("redis fora")

    monkeypatch.setattr(geocoding.cache, "incr", _boom)
    with _google() as urlopen, pytest.raises(GeocodingDailyLimitReached):
        reverse_geocode(-23.0, -51.0)
    assert urlopen.call_count == 0


@pytest.mark.django_db
def test_zero_closes_the_door(settings):
    settings.SHOPMAN_GEOCODE_REVERSE_DAILY_LIMIT = 0
    with _google() as urlopen, pytest.raises(GeocodingDailyLimitReached):
        reverse_geocode(-23.0, -51.0)
    assert urlopen.call_count == 0


@pytest.mark.django_db
@override_settings(RATELIMIT_ENABLE=False)
def test_endpoint_answers_429_with_a_clear_message(client):
    with _google():
        for i in range(3):
            assert client.post("/api/v1/geocode/reverse/", {"lat": -23.0 - i, "lng": -51.0}).status_code == 200
        resp = client.post("/api/v1/geocode/reverse/", {"lat": -29.0, "lng": -51.0})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "geocode_daily_limit_reached"
    assert "Digite o endereço" in body["detail"]
