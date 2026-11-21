"""A manobra da tela "Dirigindo" pelo Routes API (#2509): uma chamada na saída, outra só
quando ele sai da rota, teto do dia no Admin, e cada chamada registrada (DEV-2026-067)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from shopman.shop.models import PaidApiCall, Shop
from shopman.shop.services import route_guide

pytestmark = [pytest.mark.django_db]

def _encode(points):
    """Codifica pontos no formato do Google (o inverso de ``decode_polyline``), para o teste."""
    out, last_lat, last_lng = [], 0, 0
    for lat, lng in points:
        for value, last in ((round(lat * 1e5), last_lat), (round(lng * 1e5), last_lng)):
            delta = value - last
            delta = ~(delta << 1) if delta < 0 else delta << 1
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))
        last_lat, last_lng = round(lat * 1e5), round(lng * 1e5)
    return "".join(out)


# Dois passos: segue pela avenida e vira à direita na Rua Caracas.
FIRST = [(-23.3405, -51.1580), (-23.3380, -51.1600)]
SECOND = [(-23.3380, -51.1600), (-23.3300, -51.1650)]
ANSWER = {"routes": [{"legs": [{"steps": [
    {"polyline": {"encodedPolyline": _encode(FIRST)},
     "navigationInstruction": {"maneuver": "DEPART", "instructions": "Siga pela Av. Madre Leônia Milito"}},
    {"polyline": {"encodedPolyline": _encode(SECOND)},
     "navigationInstruction": {"maneuver": "TURN_RIGHT", "instructions": "Vire à direita na R. Caracas"}},
]}]}]}


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    with override_settings(GOOGLE_MAPS_SERVER_API_KEY="server-key-test", GOOGLE_MAPS_API_KEY=""):
        yield


def _shop(**routes):
    return Shop.objects.create(name="Nelson Boulangerie", latitude=-23.3405, longitude=-51.1580,
                               integrations={"google_routes": routes} if routes else {})


def test_the_google_polyline_decodes():
    assert route_guide.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_one_call_stores_the_route_and_the_meter_counts_it():
    _shop()
    with patch.object(route_guide, "_request", return_value=ANSWER) as call:
        assert route_guide.compute("CASA-1", FIRST[0], [SECOND[-1]]) is True
    assert call.call_count == 1
    guide = route_guide.view("CASA-1", (-23.3395, -51.1590))
    assert guide["path"][0] == [-23.3405, -51.158]
    assert guide["next"]["instruction"] == "Vire à direita na R. Caracas"
    assert guide["next"]["maneuver"] == "TURN_RIGHT"
    assert guide["next"]["meters"] > 0
    row = PaidApiCall.objects.get()
    assert (row.provider, row.purpose, row.outcome, row.cost_usd_micros) == (
        "google_routes", "courier_maneuver", "ok", route_guide.COST_USD_MICROS)


def test_the_daily_cap_lives_in_the_shop_and_past_it_nothing_is_called():
    _shop(calls_per_day=1)
    with patch.object(route_guide, "_request", return_value=ANSWER) as call:
        assert route_guide.compute("CASA-1", FIRST[0], [SECOND[-1]]) is True
        assert route_guide.compute("CASA-2", FIRST[0], [SECOND[-1]]) is False
    assert call.call_count == 1
    assert list(PaidApiCall.objects.order_by("created_at").values_list("outcome", "cost_usd_micros")) == [
        ("ok", route_guide.COST_USD_MICROS), ("denied", 0)]
    assert route_guide.read("CASA-2") is None  # a página fica na linha reta


def test_switched_off_or_without_key_there_is_no_call():
    _shop(enabled=False)
    with patch.object(route_guide, "_request") as call:
        assert route_guide.compute("CASA-1", FIRST[0], [SECOND[-1]]) is False
    call.assert_not_called()
    assert not PaidApiCall.objects.exists()


def test_an_error_falls_back_to_the_straight_line_and_is_recorded():
    _shop()
    with patch.object(route_guide, "_request", side_effect=TimeoutError("lento")):
        assert route_guide.compute("CASA-1", FIRST[0], [SECOND[-1]]) is False
    row = PaidApiCall.objects.get()
    assert (row.outcome, row.error_type, row.cost_usd_micros) == ("error", "TimeoutError", 0)
    assert route_guide.view("CASA-1", None) is None


def test_off_route_follows_the_meters_chosen_in_the_admin():
    _shop(reroute_meters=50)
    with patch.object(route_guide, "_request", return_value=ANSWER):
        route_guide.compute("CASA-1", FIRST[0], [SECOND[-1]])
    assert route_guide.off_route("CASA-1", (-23.3381, -51.1601)) is False  # em cima da linha
    assert route_guide.off_route("CASA-1", (-23.3500, -51.1800)) is True   # a uns 2 km dela


def test_the_admin_cap_never_passes_the_code_brake():
    _shop(calls_per_day=999_999, reroute_meters=1)
    config = route_guide.settings_for_shop()
    assert config["calls_per_day"] == route_guide.MAX_CALLS_PER_DAY
    assert config["reroute_meters"] == 30
