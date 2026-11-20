"""A posição do entregador: um lugar grava, com a hora e a via; o poll só sem webhook (F7b).

Usa o adapter mock da TaOn (sem rede). A posição é dado pessoal: nenhum teste aceita
a coordenada no log.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_SYNC
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier, courier_position
from shopman.shop.tests.test_courier_service import _dispatched_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
WEBHOOK = courier_position.SOURCE_WEBHOOK
POLL = courier_position.SOURCE_POLL


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


# ── gravar e ler ────────────────────────────────────────────────────


def test_the_position_keeps_where_when_and_who_said():
    assert courier_position.store_position("R1", "-23.305", "-51.162", source=WEBHOOK,
                                           at="2026-11-20T15:00:00Z")
    position = courier_position.read("R1")
    assert position["latitude"] == -23.305 and position["longitude"] == -51.162
    assert position["at"].isoformat() == "2026-11-20T15:00:00+00:00"
    assert position["source"] == WEBHOOK


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (1786381200000, "2026-08-10T17:00:00+00:00"),  # ms, como o lote da TaOn
        (1786381200, "2026-08-10T17:00:00+00:00"),  # segundos
        ("1786381200000", "2026-08-10T17:00:00+00:00"),
        ("2026-08-10T14:00:00-03:00", "2026-08-10T17:00:00+00:00"),
    ],
)
def test_the_hour_is_the_one_the_service_sent(at, expected):
    courier_position.store_position("R1", -23.3, -51.1, source=WEBHOOK, at=at)
    assert courier_position.read("R1")["at"].isoformat() == expected


def test_without_a_readable_hour_the_position_is_from_now():
    before = timezone.now()
    courier_position.store_position("R1", -23.3, -51.1, source=POLL, at="ontem")
    assert courier_position.read("R1")["at"] >= before


def test_a_position_from_the_future_is_from_now():
    courier_position.store_position("R1", -23.3, -51.1, source=WEBHOOK,
                                    at=(timezone.now() + timedelta(hours=3)).isoformat())
    assert courier_position.read("R1")["at"] <= timezone.now()


@pytest.mark.parametrize(
    ("lat", "lng", "source"),
    [
        ("x", "-51.1", WEBHOOK),
        (None, "-51.1", WEBHOOK),
        ("-91", "-51.1", WEBHOOK),
        ("-23.3", "181", WEBHOOK),
        ("0", "0", WEBHOOK),  # o GPS sem sinal
        ("nan", "-51.1", WEBHOOK),
        ("-23.3", "-51.1", "palpite"),
    ],
)
def test_what_is_not_a_position_is_not_stored(lat, lng, source):
    assert not courier_position.store_position("R1", lat, lng, source=source)
    assert courier_position.read("R1") is None


def test_an_older_position_never_replaces_a_newer_one():
    courier_position.store_position("R1", -23.30, -51.10, source=WEBHOOK, at="2026-11-20T15:00:10Z")
    assert not courier_position.store_position("R1", -23.99, -51.99, source=WEBHOOK, at="2026-11-20T15:00:00Z")
    assert courier_position.read("R1")["latitude"] == -23.30


def test_a_record_without_hour_is_no_position():
    cache.set("courier:pos:R1", {"lat": "-23.3", "lng": "-51.1"}, 120)
    assert courier_position.read("R1") is None


# ── o aviso ao Gestor ───────────────────────────────────────────────


def test_one_push_per_ride_every_ten_seconds():
    with patch("shopman.shop.handlers._sse_emitters.emit_courier_position") as push:
        courier_position.store_position("R1", -23.30, -51.10, source=WEBHOOK)
        courier_position.store_position("R1", -23.31, -51.11, source=WEBHOOK)
        courier_position.store_position("R2", -23.32, -51.12, source=WEBHOOK)
        assert [call.args[0] for call in push.call_args_list] == ["R1", "R2"]
        cache.delete("courier:pos:push:R1")  # passaram os 10 s
        courier_position.store_position("R1", -23.33, -51.13, source=WEBHOOK)
    assert [call.args[0] for call in push.call_args_list] == ["R1", "R2", "R1"]
    assert courier_position.PUSH_THROTTLE_SECONDS == 10


def test_the_push_names_the_ride_never_the_coordinate(django_capture_on_commit_callbacks):
    with patch("django_eventstream.send_event") as send, django_capture_on_commit_callbacks(execute=True):
        courier_position.store_position("R1", -23.305, -51.162, source=WEBHOOK)
    channel, event_type, payload = send.call_args.args
    assert (channel, event_type, payload) == ("backstage-orders-main", "backstage-courier-position", {"ride": "R1"})


# ── o poll só quando o webhook falta ────────────────────────────────


def _accepted(order) -> None:
    """Aceita do lado da central (o mock só dá posição a corrida aceita) e do nosso."""
    courier_mock.set_status(courier.get_block(order)["id_mch"], "A")
    courier.apply_status(order, "A", source="poll")


class _Logged(logging.Handler):
    """O que estes loggers escreveram (o LOGGING do projeto não propaga ao caplog)."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture
def logged():
    handler = _Logged()
    names = ("shopman.shop.services.courier_position", "shopman.shop.webhooks.machine",
             "shopman.shop.handlers.courier_sync", "shopman.shop.services.courier")
    for name in names:
        logging.getLogger(name).addHandler(handler)
    yield handler
    for name in names:
        logging.getLogger(name).removeHandler(handler)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_with_the_webhook_quiet_the_beat_asks_the_service(shop):
    order = _dispatched_order(shop)
    _accepted(order)
    block = courier.get_block(order)

    assert courier_position.poll_if_silent(block)
    position = courier_position.read(block["id_mch"])
    assert position["source"] == POLL
    assert (position["latitude"], position["longitude"]) == (-23.3045, -51.1696)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_with_the_webhook_alive_nobody_asks(shop):
    order = _dispatched_order(shop)
    _accepted(order)
    block = courier.get_block(order)
    courier_position.store_position(block["id_mch"], -23.30, -51.10, source=WEBHOOK)

    with patch.object(courier_mock, "get_position") as asked:
        assert not courier_position.poll_if_silent(block)
    asked.assert_not_called()
    assert courier_position.read(block["id_mch"])["source"] == WEBHOOK


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_webhook_quiet_for_more_than_thirty_seconds_counts_as_missing(shop):
    order = _dispatched_order(shop)
    _accepted(order)
    block = courier.get_block(order)
    old = timezone.now() - timedelta(seconds=courier_position.WEBHOOK_SILENT_SECONDS + 5)
    courier_position.store_position(block["id_mch"], -23.30, -51.10, source=WEBHOOK, at=old.isoformat())

    assert courier_position.poll_if_silent(block)
    assert courier_position.read(block["id_mch"])["source"] == POLL


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_nobody_asks_before_someone_accepts(shop):
    order = _dispatched_order(shop)
    with patch.object(courier_mock, "get_position") as asked:
        assert not courier_position.poll_if_silent(courier.get_block(order))
    asked.assert_not_called()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_service_without_get_position_is_not_asked(shop):
    """O entregador da casa não tem central: a posição dele só chega se o celular mandar."""
    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    block = courier.get_block(order)
    house = SimpleNamespace(ride_state=courier_mock.ride_state)
    with patch("shopman.shop.services.delivery_services.courier_backend", return_value=house):
        assert not courier_position.poll_if_silent(block)
    assert courier_position.store_position(block["id_mch"], -23.30, -51.10,
                                           source=courier_position.SOURCE_OWN_FLEET)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_failed_poll_never_stops_the_beat_nor_logs_the_place(shop, logged):
    order = _dispatched_order(shop)
    _accepted(order)
    block = courier.get_block(order)
    with patch.object(courier_mock, "get_position", MagicMock(side_effect=RuntimeError("-23.3045"))):
        assert not courier_position.poll_if_silent(block)
    assert "courier.position_poll_failed" in logged.text
    assert "-23.3045" not in logged.text


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_sync_beat_brings_the_position_when_the_webhook_is_quiet(shop, logged):
    order = _dispatched_order(shop)
    ride = courier.get_block(order)["id_mch"]
    courier_mock.set_status(ride, "A")
    directive = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)

    CourierSyncHandler().handle(message=directive, ctx={})

    assert courier_position.read(ride)["source"] == POLL
    assert "courier.position_poll" in logged.text
    assert "-23.3045" not in logged.text and "-51.1696" not in logged.text


# ── o webhook grava com a hora do lote e não loga a coordenada ───────


def test_the_webhook_batch_never_logs_the_place(shop, logged):
    from django.urls import reverse

    from shopman.shop.tests.test_machine_webhook import MACHINE, SignedClient

    batch = {
        "event_id": "01a01e79-080c-7d22-bdf6-432b1ba40c44",
        "datetime": "2026-11-20T15:00:10Z",
        "data": [{"timestamp": 1795705200000, "company_id": 8, "request_id": 184532, "driver_id": 8101,
                  "coordinates": {"latitude": -23.305123, "longitude": -51.162456}}],
    }
    url = f"{reverse('webhooks:machine-webhook')}?token={MACHINE['webhook_token']}"
    with override_settings(SHOPMAN_MACHINE=MACHINE):
        response = SignedClient().post(url, batch, format="json")
    assert response.status_code == 200
    assert courier_position.read("184532")["source"] == WEBHOOK
    assert "position_batch" in logged.text
    assert "23.305123" not in logged.text and "51.162456" not in logged.text
