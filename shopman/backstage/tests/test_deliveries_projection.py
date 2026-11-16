"""A seção Entregas do Gestor: o que aguarda entregador e as corridas vivas.

Usa o adapter mock da TaOn (sem rede). O número da corrida é a cor dela na tela:
nasce na chamada, não muda enquanto a corrida vive e volta a ficar livre depois.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.backstage.projections.deliveries import build_deliveries, deliveries_waiting_count
from shopman.shop.adapters import courier_mock
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
PAID = {"method": "pix", "status": "captured"}


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


def _at(ref, lat, lng, **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng, neighborhood="Centro")
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


def _call(*orders):
    directive = courier.request_group_dispatch(list(orders), actor="operator:ana") if len(orders) > 1 \
        else courier.request_dispatch(orders[0], actor="operator:ana")
    CourierDispatchHandler().handle(message=directive, ctx={})
    for order in orders:
        order.refresh_from_db()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_waiting_lists_deliveries_without_a_ride_with_coordinates(shop):
    _at("EN-A", -23.30, -51.16)
    _at("EN-B", -23.31, -51.17)

    deliveries = build_deliveries()

    assert deliveries.origin is not None and deliveries.origin.latitude == pytest.approx(-23.3405)
    assert [stop.ref for stop in deliveries.waiting] == ["EN-A", "EN-B"]
    first = deliveries.waiting[0]
    assert (first.latitude, first.longitude, first.place) == (-23.30, -51.16, "Centro")
    assert deliveries.rides == ()
    assert deliveries_waiting_count() == 2


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_called_ride_leaves_waiting_and_shows_as_one_ride_with_its_number(shop):
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    alone = _at("EN-C", -23.32, -51.15)

    _call(a, b)

    deliveries = build_deliveries()
    assert [stop.ref for stop in deliveries.waiting] == ["EN-C"]
    (ride,) = deliveries.rides
    assert ride.number == 1
    assert ride.state == "searching"
    # As paradas na ordem do percurso (a mais perto da loja primeiro).
    assert [stop.ref for stop in ride.stops] == ["EN-B", "EN-A"]
    assert courier.get_block(a)["ride_number"] == courier.get_block(b)["ride_number"] == 1

    _call(alone)
    numbers = [ride.number for ride in build_deliveries().rides]
    assert numbers == [1, 2]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_number_is_freed_when_the_ride_ends(shop):
    a = _at("EN-A", -23.30, -51.16)
    b = _at("EN-B", -23.31, -51.16)
    _call(a)
    _call(b)
    assert courier.get_block(b)["ride_number"] == 2

    # Entregue e pago antes (nada volta com o entregador): a corrida acabou.
    for status in ("A", "E", "F"):
        courier.apply_status(a, status, source="test")
        a.refresh_from_db()

    assert courier.next_ride_number() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_ride_link_is_offered_only_when_the_ride_has_one_stop(shop):
    """O link é de UMA parada: com várias, "o link da corrida" seria o de um cliente só."""
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    alone = _at("EN-C", -23.32, -51.15)
    _call(a, b)
    _call(alone)
    for order in (a, b, alone):
        courier.apply_status(order, "A", source="test")
        order.refresh_from_db()

    shared, single = build_deliveries().rides
    assert [stop.ref for stop in shared.stops] == ["EN-B", "EN-A"]
    # Cada pedido tem o link da própria parada gravado, e mesmo assim a corrida não oferece um.
    assert courier.proven_tracking(courier.get_block(a))["url"] != courier.proven_tracking(courier.get_block(b))["url"]
    assert shared.tracking_url == ""
    assert single.tracking_url == f"https://rastreio.mock/pedido/{courier.get_block(alone)['id_mch']}"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_bags_sum_the_declared_volumes_and_name_who_is_missing(shop):
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    a.data = {**a.data, "volumes": 2}
    a.save(update_fields=["data"])

    _call(a, b)

    (ride,) = build_deliveries().rides
    assert ride.bags == 2
    assert ride.undeclared == ("B",)  # o código curto do pedido, como o balcão fala


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_endpoint_answers_for_who_runs_the_board(shop):
    _at("EN-A", -23.30, -51.16)
    user = get_user_model().objects.create_user("gestor", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    client = APIClient()
    client.force_authenticate(user)

    body = client.get("/api/v1/backstage/deliveries/").json()
    count = client.get("/api/v1/backstage/deliveries/count/").json()

    assert [stop["ref"] for stop in body["waiting"]] == ["EN-A"]
    assert body["waiting"][0]["dispatch_action"]["payload_schema"]["expected_actor_id"] == user.pk
    assert count == {"waiting": 1}


def test_anonymous_is_refused():
    assert APIClient().get("/api/v1/backstage/deliveries/").status_code in (401, 403)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_orders_never_show(shop):
    order = _at("EN-A", -23.30, -51.16)
    order.data = {**order.data, "fulfillment_type": "pickup"}
    order.save(update_fields=["data"])
    assert Order.objects.count() == 1
    assert build_deliveries().waiting == ()
