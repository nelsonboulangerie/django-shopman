"""O fim da corrida resolve os avisos de cancelamento dela (#2496).

A recusa da central ("A TaOn não cancelou"), o envio sem resultado e o pedido
cancelado com a corrida aberta abrem avisos ``integration_failed``, fora da
resolução automática por status. Com a corrida encerrada (C, N ou F) nenhum
deles é mais verdade; os outros avisos ``integration_failed`` do pedido ficam.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import alert as alert_adapter
from shopman.shop.adapters import courier_mock
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _dispatched_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"

REFUSED = "A TaOn não cancelou a corrida A. Cancele pela central da TaOn."
ORDER_CANCELLED = "O pedido A47 foi cancelado e a corrida segue aberta na central: cancele a corrida por lá."
OTHER = "Dedupe: fiscal:emit_nfce:pedido X: a nota não saiu."


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


def _open(ref):
    return set(
        OperatorAlert.objects.filter(order_ref=ref, type="integration_failed", resolved_at__isnull=True)
        .values_list("message", flat=True)
    )


def _alerts(order):
    for message in (REFUSED, courier.CANCEL_UNKNOWN_MESSAGE, ORDER_CANCELLED, OTHER):
        alert_adapter.create("integration_failed", "critical", message, order_ref=order.ref)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("status", ["C", "N", "F"])
def test_the_end_of_the_ride_resolves_its_cancel_alerts_and_keeps_the_others(
    shop, status, django_capture_on_commit_callbacks
):
    order = _dispatched_order(shop)
    _alerts(order)
    with django_capture_on_commit_callbacks(execute=True):
        assert courier.apply_status(order, status, source="webhook") == "applied"
    remaining = _open(order.ref)
    assert not any(marker in message for message in remaining for marker in courier.CANCEL_ALERT_MARKERS)
    assert len(remaining) == 1 and next(iter(remaining)).endswith("a nota não saiu.")
    resolved = OperatorAlert.objects.filter(order_ref=order.ref, resolved_at__isnull=False)
    assert set(resolved.values_list("resolved_by", flat=True)) == {f"courier:{status}"}


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_live_ride_keeps_the_cancel_alerts(shop, django_capture_on_commit_callbacks):
    """A central recusou e a corrida segue: o aviso é verdade até ela acabar."""
    order = _dispatched_order(shop)
    _alerts(order)
    with django_capture_on_commit_callbacks(execute=True):
        courier.apply_status(order, "A", source="webhook")
    assert len(_open(order.ref)) == 4


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_another_order_keeps_its_cancel_alert(shop, django_capture_on_commit_callbacks):
    order = _dispatched_order(shop)
    other = _dispatched_order(shop, ref="CR-2")
    _alerts(other)
    with django_capture_on_commit_callbacks(execute=True):
        courier.apply_status(order, "N", source="webhook")
    assert len(_open(other.ref)) == 4
