"""Entregas do Gestor: a posição do entregador chega com a hora e quem disse (F7b).

A idade ("Posição agora", "Última posição há 3 min") é conta da tela; a projeção dá a
hora da posição, sem perguntar nada ao serviço numa leitura.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from shopman.backstage.projections.deliveries import build_deliveries
from shopman.backstage.projections.order_queue import _courier_block
from shopman.shop.adapters import courier_mock
from shopman.shop.models import Shop
from shopman.shop.services import courier, courier_position
from shopman.shop.tests.test_courier_service import _dispatched_order

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


def _accepted(shop):
    order = _dispatched_order(shop)
    courier_mock.set_status(courier.get_block(order)["ride_ref"], "A")
    courier.apply_status(order, "A", source="poll")
    order.refresh_from_db()
    return order


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_ride_shows_where_when_and_who_said(shop):
    order = _accepted(shop)
    ride_id = courier.get_block(order)["ride_ref"]
    courier_position.store_position(ride_id, -23.31, -51.16, source=courier_position.SOURCE_WEBHOOK,
                                    at="2026-11-20T15:45:00Z")

    (ride,) = build_deliveries().rides

    assert ride.position.latitude == -23.31 and ride.position.longitude == -51.16
    assert ride.position.at == "2026-11-20T15:45:00+00:00"
    assert ride.position.source_label == "pela TaOn"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_reading_the_screen_never_asks_the_service(shop):
    _accepted(shop)
    with patch.object(courier_mock, "get_position") as asked:
        (ride,) = build_deliveries().rides
    asked.assert_not_called()
    assert ride.position is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_house_courier_position_says_it_came_from_his_phone(shop):
    order = _accepted(shop)
    courier_position.store_position(courier.get_block(order)["ride_ref"], -23.31, -51.16,
                                    source=courier_position.SOURCE_OWN_FLEET)
    (ride,) = build_deliveries().rides
    assert ride.position.source_label == "pelo celular do entregador"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_order_panel_reads_the_same_position(shop):
    order = _accepted(shop)
    courier_position.store_position(courier.get_block(order)["ride_ref"], -23.31, -51.16,
                                    source=courier_position.SOURCE_POLL, at="2026-11-20T15:45:00Z")
    position = _courier_block(order)["position"]
    assert position == {"latitude": -23.31, "longitude": -51.16, "at": "2026-11-20T15:45:00+00:00",
                        "source_label": "pela TaOn"}
