"""Falha de saída do Google Geocoding não pode morrer em logger.warning.

Três pontos cegos cobertos aqui:

1. transporte/status ruim em ``reverse_geocode``/``forward_geocode`` vira
   ``OperatorAlert`` (tipo ``integration_failed``) além do log;
2. status de INTEGRAÇÃO (quota/chave) no ``forward_geocode`` NÃO grava cache
   negativo — uma janela de quota não pode congelar "sem coordenada" por 24h;
3. o antifraude de entrega segue fail-open (UX de checkout), mas registra
   alerta crítico quando roda cego.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache

from shopman.backstage.models import OperatorAlert
from shopman.shop.services.geocoding import GeocodingError, forward_geocode, reverse_geocode


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _api_key(settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"


@pytest.fixture(autouse=True)
def _cache_clear():
    cache.clear()
    yield
    cache.clear()


def _urlopen_patch(payload: dict):
    return patch(
        "shopman.shop.services.geocoding.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    )


@pytest.mark.django_db
def test_forward_geocode_quota_status_alerts_and_skips_negative_cache() -> None:
    with _urlopen_patch({"status": "OVER_QUERY_LIMIT", "results": []}) as mocked:
        assert forward_geocode("Rua das Flores, 123, Londrina") is None
        # Segunda chamada volta ao Google: quota NÃO virou cache negativo de 24h.
        assert forward_geocode("Rua das Flores, 123, Londrina") is None

    assert mocked.call_count == 2
    alert = OperatorAlert.objects.get(type="integration_failed")
    assert "forward_geocode" in alert.message
    assert "OVER_QUERY_LIMIT" in alert.message


@pytest.mark.django_db
def test_forward_geocode_zero_results_keeps_negative_cache_and_stays_quiet() -> None:
    """Endereço realmente sem coordenada é dado, não falha: cache negativo sim,
    alerta não."""
    with _urlopen_patch({"status": "ZERO_RESULTS", "results": []}) as mocked:
        assert forward_geocode("Rua Que Nao Existe, 999") is None
        assert forward_geocode("Rua Que Nao Existe, 999") is None

    assert mocked.call_count == 1  # segunda resposta veio do cache negativo
    assert not OperatorAlert.objects.filter(type="integration_failed").exists()


@pytest.mark.django_db
def test_forward_geocode_transport_failure_alerts_and_returns_none() -> None:
    with patch(
        "shopman.shop.services.geocoding.urllib.request.urlopen",
        side_effect=OSError("connection refused"),
    ):
        assert forward_geocode("Rua das Flores, 123, Londrina") is None

    alert = OperatorAlert.objects.get(type="integration_failed")
    assert "forward_geocode" in alert.message
    assert "OSError" in alert.message


@pytest.mark.django_db
def test_reverse_geocode_bad_status_alerts_and_raises() -> None:
    with _urlopen_patch({"status": "REQUEST_DENIED", "results": []}):
        with pytest.raises(GeocodingError):
            reverse_geocode(-23.31, -51.16)

    alert = OperatorAlert.objects.get(type="integration_failed")
    assert "reverse_geocode" in alert.message
    assert "REQUEST_DENIED" in alert.message


@pytest.mark.django_db
def test_reverse_geocode_transport_failure_alerts_and_raises() -> None:
    with patch(
        "shopman.shop.services.geocoding.urllib.request.urlopen",
        side_effect=OSError("timeout"),
    ):
        with pytest.raises(GeocodingError):
            reverse_geocode(-23.31, -51.16)

    alert = OperatorAlert.objects.get(type="integration_failed")
    assert "reverse_geocode" in alert.message


@pytest.mark.django_db
def test_antifraud_check_stays_fail_open_but_alerts_critical() -> None:
    """Google indisponível não trava pedido legítimo — mas antifraude cego é o
    ponto cego mais grave, e o gestor fica sabendo na hora."""
    from shopman.shop.rules.validation import _coordinates_match_claimed_address

    session_data = {
        "delivery_address_structured": {
            "latitude": -23.31,
            "longitude": -51.16,
            "postal_code": "86020-000",
            "city": "Londrina",
        }
    }
    with patch(
        "shopman.shop.services.geocoding.reverse_geocode",
        side_effect=GeocodingError("Reverse geocoding request failed."),
    ):
        assert _coordinates_match_claimed_address(session_data) is True

    alert = OperatorAlert.objects.get(type="integration_failed")
    assert alert.severity == "critical"
    assert "antifraude" in alert.message
