"""A coluna Editando honesta (F4b): cotação de 1 a 4 pedidos com "juntas contra
separadas", a ordem da rota igual nos dois lados e o custo que a corrida mostra.

Adapter mock da TaOn (sem rede): uma parada cota R$ 12,50; cada parada a mais na
mesma corrida soma R$ 4,00.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from shopman.backstage.projections import bi_delivery_cost
from shopman.backstage.projections.deliveries import build_deliveries
from shopman.shop.adapters import courier_mock
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
PAID = {"method": "pix", "status": "captured"}
QUOTE = "/api/v1/backstage/orders/courier-ride/quote/"
FIXTURE = Path(__file__).resolve().parents[3] / "surfaces/orders-nuxt/tests/fixtures/route-order.json"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson Boulangerie", route="Av. Madre Leônia Milito", street_number="446",
        neighborhood="Bela Suíça", city="Londrina", state_code="PR",
        formatted_address="Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR",
        latitude=-23.3405, longitude=-51.1580,
    )


@pytest.fixture
def client():
    user = get_user_model().objects.create_user("gestor", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    api = APIClient()
    api.force_authenticate(user)
    return api


def _at(ref, lat, lng, **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng)
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


# ── a ordem da rota: a mesma fixture do vitest ─────────────────────────────


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text())["cases"], ids=lambda case: case["name"])
def test_route_order_is_the_same_on_both_sides(case):
    origin = case["origin"]
    stops = [(stop["ref"], {"latitude": stop["latitude"], "longitude": stop["longitude"]}) for stop in case["stops"]]
    route = courier._route((origin["latitude"], origin["longitude"]) if origin else None, stops)
    assert [ref for ref, _ in route] == case["expected"]


# ── cotação: de 1 a 4 pedidos ──────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_one_order_is_quoted_too(shop, client):
    _at("ED-A", -23.31, -51.16)
    body = client.get(QUOTE, {"refs": ["ED-A"]}).json()
    assert body["estimate"]["value_q"] == 1250
    assert body["estimate"]["stops"] == ["ED-A"]
    # Uma parada não compara com nada.
    assert "separate_value_q" not in body["estimate"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_two_orders_compare_together_against_separate(shop, client):
    _at("ED-A", -23.31, -51.16)
    _at("ED-B", -23.335, -51.158)
    body = client.get(QUOTE, {"refs": ["ED-A", "ED-B"]}).json()["estimate"]
    assert body["value_q"] == 1650
    assert body["stops"] == ["ED-B", "ED-A"]
    assert (body["separate_value_q"], body["saving_q"]) == (2500, 850)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_no_comparison_when_one_separate_quote_is_missing(shop, client):
    _at("ED-A", -23.31, -51.16)
    _at("ED-B", -23.335, -51.158)
    real = courier.estimate_for_order

    def flaky(order):
        return None if order.ref == "ED-B" else real(order)

    with mock.patch.object(courier, "estimate_for_order", side_effect=flaky):
        body = client.get(QUOTE, {"refs": ["ED-A", "ED-B"]}).json()["estimate"]
    assert body["value_q"] == 1650
    # Soma com buraco mente: sem a comparação.
    assert "separate_value_q" not in body and "saving_q" not in body


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_quote_refuses_zero_and_more_than_the_ride_holds(shop, client):
    assert client.get(QUOTE).status_code == 400
    refs = [f"ED-{n}" for n in range(courier.MAX_RIDE_STOPS + 1)]
    assert client.get(QUOTE, {"refs": refs}).status_code == 400


# ── o custo que a corrida mostra (J13) ─────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_joined_ride_shows_the_route_quote_never_the_old_single_one(shop):
    far = _at("ED-A", -23.31, -51.16)
    near = _at("ED-B", -23.335, -51.158)
    # Antes de juntar, o operador cotou A sozinho no Painel: R$ 12,50.
    courier.store_estimate(far, courier.estimate_for_order(far), expected_revision=courier.dispatch_revision(far))
    directive = courier.request_group_dispatch([far, near], actor="operator:ana")
    CourierDispatchHandler().handle(message=directive, ctx={})

    (ride,) = build_deliveries().rides
    assert (ride.cost_display, ride.cost_label) == ("R$ 16,50", "Cotação da corrida")


def test_cost_is_never_the_single_quote_of_a_joined_ride():
    from shopman.backstage.projections.deliveries import _ride_cost

    solo = {"estimate": {"value_q": 1250}}
    assert _ride_cost(solo, ["A", "B"]) == (0, "")
    assert _ride_cost(solo, ["A"]) == (1250, "Cotação da corrida")
    route = {"estimate": {"value_q": 1650, "stops": ["B", "A"]}}
    assert _ride_cost(route, ["A", "B"]) == (1650, "Cotação da corrida")
    assert _ride_cost({**route, "final_value_q": 1700}, ["A", "B"]) == (1700, "Valor pago à TaOn")


def test_bi_counts_the_route_quote_of_a_finished_joined_ride():
    ride = {"status": "F", "ride_orders": ["A", "B"], "estimate": {"value_q": 1650, "stops": ["B", "A"]}}
    assert bi_delivery_cost.ride_cost_q(ride) == (1650, True)
    single = {"status": "F", "ride_orders": ["A", "B"], "estimate": {"value_q": 1250}}
    assert bi_delivery_cost.ride_cost_q(single) is None
