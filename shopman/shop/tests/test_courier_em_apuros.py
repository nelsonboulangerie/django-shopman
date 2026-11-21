"""Corrida em apuros (revisão das Entregas, F8).

- AN/AW/T do webhook: nas redondezas, esperando na loja além do combinado e a
  troca de entregador (TAON-12), que antes eram descartados.
- Identificação de quem leva dinheiro e maquininha: o veículo vem em
  ``vehicle{}`` (TAON-14), e a foto mora só no cache, só durante a corrida.
- A auto-conclusão não marca entregue com o entregador na rua (ENT-14).
- A batida não morre em 6 h nem com o polling desligado (ENT-07).
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters import courier_machine, courier_mock
from shopman.shop.directives import COURIER_SYNC, DELIVERY_AUTO_COMPLETE
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.handlers.delivery_auto_complete import DeliveryAutoCompleteHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.webhooks.machine import signature_for

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
API_KEY = "chave-da-api-machine"
MACHINE = {"webhook_token": "tok-machine-1", "api_key": API_KEY}
RIDE = "184532"


class SignedClient(APIClient):
    def post(self, path, data=None, format=None, content_type=None, **extra):
        body = json.dumps(data if data is not None else {}).encode("utf-8")
        extra.setdefault("HTTP_SIGNATURE_V2", signature_for(body, API_KEY))
        return super().post(path, body, content_type="application/json", **extra)


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(name="Nelson", city="Londrina", state_code="PR", latitude=-23.34, longitude=-51.15)


def _order(ref="AP-1", *, status=Order.Status.READY, block=None) -> Order:
    return Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"S-{ref}", status=status, snapshot={"items": []},
        data={
            "fulfillment_type": "delivery",
            "customer": {"name": "Ana", "phone": "5543999990000"},
            "delivery_address_structured": {"latitude": -23.31, "longitude": -51.16},
            "courier": {"provider": "machine", "ride_ref": RIDE, "status": "A",
                        "requested_at": timezone.now().isoformat(), **(block or {})},
        },
        total_q=5000,
    )


def _event(code, *, at="2026-10-01T13:20:05Z", event_id="ev-1"):
    return {"datetime": at, "event_id": event_id, "company_id": 8, "request_id": int(RIDE),
            "status_code": code, "status_label": code}


def _post(payload):
    return SignedClient().post(f"{reverse('webhooks:machine-webhook')}?token=tok-machine-1", payload)


# ── AN / AW / T ─────────────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_near_and_waiting_events_feed_the_pickup_clock(shop):
    order = _order()
    assert _post(_event("AN", at="2026-10-01T13:18:00Z")).data["kind"] == "event"
    _post(_event("AW", at="2026-10-01T13:27:00Z", event_id="ev-2"))
    order.refresh_from_db()
    progress = courier.get_block(order)["progress"]
    assert progress["near_pickup_at"] == "2026-10-01T13:18:00Z"
    # Quem espera, chegou: o relógio da espera conta mesmo sem o AP.
    assert progress["arrived_pickup_at"] == "2026-10-01T13:27:00Z"
    assert progress["waited_pickup_at"] == "2026-10-01T13:27:00Z"
    assert courier.get_block(order)["status"] == "A"
    view = courier.progress_view(courier.get_block(order))
    assert view["near_pickup_at"] and view["waited_pickup_at"]


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_events_after_collection_change_nothing(shop):
    order = _order(block={"status": "E", "dispatched_at": timezone.now().isoformat()})
    _post(_event("AW"))
    order.refresh_from_db()
    assert "progress" not in courier.get_block(order)


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_transfer_reopens_the_same_ride_and_is_never_a_failure(shop):
    order = _order(block={"driver": {"name": "Diego"}})
    _post(_event("T", at="2026-10-01T13:25:00Z"))
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["ride_ref"] == RIDE  # a MESMA corrida
    assert block["status"] == "D"
    assert "driver" not in block
    assert courier.reopen_view(block) == {"at": "2026-10-01T13:25:00Z", "driver": "Diego", "reason": "transfer"}
    assert not block.get("attempts")


# ── Identificação: o veículo e a foto ───────────────────────────────


def test_driver_reads_the_vehicle_the_way_taon_sends_it():
    body = {
        "driver": {"name": "Diego Ferreira", "phone": "43998761203",
                   "photo_url": "https://cdn.taon.example/drivers/8101.jpg?sig=abc"},
        "vehicle": {"model": "Honda CG", "color": "Prata", "vehicle_plate": "ABC1D23"},
    }
    driver = courier_machine.driver_from(body)
    assert driver == {"name": "Diego Ferreira", "phone": "43998761203", "vehicle_plate": "ABC1D23",
                      "vehicle_model": "Honda CG", "vehicle_color": "Prata"}
    assert courier.vehicle_line(driver) == "Honda CG prata · ABC1D23"
    assert courier_machine.driver_photo_url(body).startswith("https://")
    assert courier_machine.driver_photo_url({"driver": {"photo_url": "http://inseguro/x.jpg"}}) == ""


def test_vehicle_line_without_model_still_says_the_color():
    assert courier.vehicle_line({"vehicle_color": "preta", "vehicle_plate": "XYZ9K88"}) == "Preta · XYZ9K88"
    assert courier.vehicle_line({}) == ""


def _photo_response(body=b"\xff\xd8jpeg", content_type="image/jpeg", status=200):
    response = MagicMock(status_code=status, headers={"Content-Type": content_type})
    response.raw.read.return_value = body
    return response


def test_photo_lives_only_in_the_cache_and_only_while_the_ride_lives(shop):
    order = _order()
    courier.remember_driver_photo(RIDE, "https://cdn.taon.example/8101.jpg")
    assert "photo" not in json.dumps(order.data)  # nunca no pedido
    with patch("requests.get", return_value=_photo_response()) as get:
        assert courier.driver_photo(RIDE) == (b"\xff\xd8jpeg", "image/jpeg")
        assert courier.driver_photo(RIDE) == (b"\xff\xd8jpeg", "image/jpeg")
    assert get.call_count == 1  # baixada uma vez, servida do cache

    courier.apply_status(order, "F", source="poll")
    assert not courier.has_driver_photo(RIDE)
    assert courier.driver_photo(RIDE) is None


def test_photo_that_is_not_an_image_is_refused(shop):
    _order()
    courier.remember_driver_photo(RIDE, "https://cdn.taon.example/8101.jpg")
    with patch("requests.get", return_value=_photo_response(b"<html>", "text/html")):
        assert courier.driver_photo(RIDE) is None
    assert not courier.has_driver_photo(RIDE)


def test_photo_endpoint_is_no_store_and_404_without_ride(shop, admin_client):
    url = reverse("api-backstage-delivery-driver-photo", kwargs={"ride": "999"})
    response = admin_client.get(url)
    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"

    _order()
    courier.remember_driver_photo(RIDE, "https://cdn.taon.example/8101.jpg")
    with patch("requests.get", return_value=_photo_response()):
        response = admin_client.get(reverse("api-backstage-delivery-driver-photo", kwargs={"ride": RIDE}))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "no-store"


# ── Auto-conclusão (ENT-14) ──────────────────────────────────────────


def _auto_complete(order):
    directive = Directive.objects.create(topic=DELIVERY_AUTO_COMPLETE, payload={"order_ref": order.ref})
    directive.status = Directive.Status.RUNNING
    DeliveryAutoCompleteHandler().handle(message=directive, ctx={})
    directive.refresh_from_db()
    order.refresh_from_db()
    return directive


def test_auto_complete_waits_while_the_driver_is_on_the_street(shop):
    order = _order(status=Order.Status.DISPATCHED, block={
        "status": "E", "dispatched_at": timezone.now().isoformat(),
        "progress": {"picked_up_at": timezone.now().isoformat(), "trip_minutes": 20},
    })
    directive = _auto_complete(order)
    assert order.status == Order.Status.DISPATCHED
    assert directive.status == Directive.Status.QUEUED
    # A entrega prevista pela TaOn (coleta + 20 min de viagem), mais a folga.
    assert directive.available_at > timezone.now() + timedelta(minutes=20)


def test_auto_complete_concludes_and_warns_when_the_reading_stopped(shop):
    from shopman.backstage.models import OperatorAlert

    order = _order(status=Order.Status.DISPATCHED, block={
        "status": "E", "dispatched_at": timezone.now().isoformat(),
        "sync": {"failing_since": (timezone.now() - timedelta(minutes=40)).isoformat()},
    })
    with patch("shopman.shop.services.operator_orders.confirm_received", return_value=True) as confirm:
        _auto_complete(order)
    confirm.assert_called_once()
    alert = OperatorAlert.objects.get(order_ref=order.ref)
    assert "marcado entregue pelo prazo" in alert.message


def test_auto_complete_without_ride_is_the_old_safety_net(shop):
    order = _order(status=Order.Status.DISPATCHED, block={"status": "F"})
    assert courier.auto_complete_hold_until(order, grace_minutes=30) is None


# ── A batida lenta (ENT-07) ──────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_old_ride_keeps_a_slow_heartbeat_and_says_it_is_open_too_long(shop):
    order = _order(block={"requested_at": (timezone.now() - timedelta(hours=courier.MAX_POLL_HOURS + 1)).isoformat()})
    message = Directive.objects.create(topic=COURIER_SYNC, payload={"order_ref": order.ref},
                                       status=Directive.Status.RUNNING)
    with patch.object(courier_mock, "read_ride", return_value={"status": "A"}, create=True):
        CourierSyncHandler().handle(message=message, ctx={})
    beat = Directive.objects.filter(topic=COURIER_SYNC, status=Directive.Status.QUEUED).exclude(pk=message.pk).get()
    assert beat.available_at >= timezone.now() + timedelta(seconds=courier.SLOW_POLL_SECONDS - 5)
    assert courier.ride_open_too_long(courier.get_block(order))
