"""Uma corrida da TaOn para vários pedidos: uma solicitação, uma parada por pedido.

Usa o adapter mock (``courier_mock``), sem rede. A leitura da corrida é uma só
(no primeiro pedido) e vale para todos os pedidos dela.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_SYNC
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


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
PAID = {"method": "pix", "status": "captured"}


def _at(ref, lat, lng, **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng)
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


def _run(directive):
    CourierDispatchHandler().handle(message=directive, ctx={})


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_one_ride_carries_every_order_in_route_order(shop):
    # A loja fica em (-23.3405, -51.1580): B é a mais perto, depois A, depois C.
    far = _at("CR-A", -23.30, -51.16)
    near = _at("CR-B", -23.335, -51.158)
    farthest = _at("CR-C", -23.25, -51.17, payment={"method": "cash", "collection": "on_delivery"})

    directive = courier.request_group_dispatch([far, near, farthest], actor="operator:ana")
    _run(directive)

    assert len(courier_mock.rides()) == 1
    ride_id, ride = next(iter(courier_mock.rides().items()))
    body = ride["payload"]
    assert [stop["id_externo"] for stop in body["paradas"]] == ["CR-B", "CR-A", "CR-C"]
    # O dinheiro de C volta à loja: a corrida inteira pede retorno.
    assert body["retorno"] is True
    for order in (far, near, farthest):
        order.refresh_from_db()
        block = courier.get_block(order)
        assert block["id_mch"] == ride_id
        assert block["ride_orders"] == ["CR-B", "CR-A", "CR-C"]
    # Cada pedido guarda a observação da SUA parada.
    assert courier.get_block(farthest)["door_charge_note"].startswith("Pedido C · Cobrar R$ 50,00 em dinheiro")
    assert courier.get_block(far)["door_charge_note"] == "Pedido A · Pago, não cobrar"
    # Uma leitura só, no pedido da primeira parada.
    syncs = Directive.objects.filter(topic=COURIER_SYNC)
    assert [task.payload["order_ref"] for task in syncs] == ["CR-B"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_one_reading_moves_every_order_of_the_ride(shop):
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    _run(courier.request_group_dispatch([a, b], actor="operator:ana"))
    a.refresh_from_db()
    ride_id = courier.get_block(a)["id_mch"]

    courier_mock.set_status(ride_id, "E")
    CourierSyncHandler().handle(message=Directive.objects.get(topic=COURIER_SYNC), ctx={})
    for order in (a, b):
        order.refresh_from_db()
        assert courier.get_block(order)["status"] == "E"
        assert order.status == Order.Status.DISPATCHED

    courier_mock.set_status(ride_id, "F")
    CourierSyncHandler().handle(message=Directive.objects.filter(topic=COURIER_SYNC).last(), ctx={})
    for order in (a, b):
        order.refresh_from_db()
        assert order.status in {Order.Status.DELIVERED, Order.Status.COMPLETED}


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_takes_an_order_that_takes_the_card_machine(shop):
    a = _at("CR-A", -23.30, -51.16)
    card = _at("CR-B", -23.335, -51.158, payment={"method": "credit", "collection": "on_delivery"})
    # A maquininha não tira o pedido da corrida: a custódia é de quem chama.
    assert courier.group_refusal(a) == ""
    assert courier.group_refusal(card) == ""


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_needs_two_orders_and_no_order_called_twice(shop):
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    with pytest.raises(ValueError, match="dois pedidos"):
        courier.request_group_dispatch([a], actor="operator:ana")
    courier.request_dispatch(b, actor="operator:ana")
    with pytest.raises(ValueError, match="sendo chamado"):
        courier.request_group_dispatch([a, b], actor="operator:ana")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancelling_one_order_never_cancels_the_ride_of_the_others(shop):
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    _run(courier.request_group_dispatch([a, b], actor="operator:ana"))
    a.refresh_from_db()
    courier.on_order_cancelled(a)
    assert not Directive.objects.filter(topic="courier.cancel").exists()
    alert = OperatorAlert.objects.get(order_ref="CR-A")
    assert "tirar a parada" in alert.message


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_quote_follows_the_route_the_ride_will_take(shop):
    far = _at("CR-A", -23.30, -51.16)
    near = _at("CR-B", -23.335, -51.158, payment={"method": "cash", "collection": "on_delivery"})

    quote = courier.estimate_for_ride([far, near])

    # A mesma ordem da corrida aberta, uma parada no meio e o retorno do dinheiro.
    assert quote["stops"] == ["CR-B", "CR-A"]
    assert quote["with_return"] is True
    assert quote["value_q"] == 1250 + 400


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_quote_needs_every_address_on_the_map(shop):
    a = _at("CR-A", -23.30, -51.16)
    b = _at("CR-B", -23.335, -51.158)
    address = dict(b.data["delivery_address_structured"], latitude=None, longitude=None)
    b.data = {**b.data, "delivery_address_structured": address}
    b.save(update_fields=["data"])
    assert courier.estimate_for_ride([a, b]) is None
