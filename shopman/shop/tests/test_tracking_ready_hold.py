"""O cliente só lê "Pronto" quando a janela de desfazer do pronto fecha (beta 06/11).

A Cozinha leva o pedido a READY na hora, mas o aviso de pronto espera a janela
(``order_undo.ready_hold``), e o Gestor ainda pode devolver o pedido ao preparo.
O acompanhamento mostrava "Pronto" enquanto o Gestor dizia "aviso ao cliente sai
em 0:10" com Desfazer à mão.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.models import Channel, Shop
from shopman.shop.projections import order_tracking
from shopman.shop.services import kds as kds_core

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready_in_window(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    order = Order.objects.create(
        ref="TRACK-HOLD-1",
        channel_ref="web",
        session_key="sk-TRACK-HOLD-1",
        status=Order.Status.PREPARING,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    station = KDSInstance.objects.create(ref="forno", name="Forno", type="prep")
    ticket = KDSTicket.objects.create(
        session_key=order.session_key, kds_instance=station, status="in_progress",
        items=[{"sku": "PAO", "name": "Pão", "qty": 1}],
    )
    kds_core.complete_ticket(ticket, actor="kds:op")
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert order.data["auto_ready"]["undo_until"]
    return order


def _close_window(order: Order) -> Order:
    data = dict(order.data)
    data["auto_ready"] = {**data["auto_ready"], "undo_until": (timezone.now() - timedelta(seconds=1)).isoformat()}
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()
    return order


def test_inside_the_undo_window_the_customer_still_reads_preparing(ready_in_window):
    tracking = order_tracking.build_tracking(ready_in_window)

    assert tracking.status == "preparing"
    assert tracking.display_status_key == "preparing"
    assert tracking.promise.state == "preparing"
    assert not any(step.key == "ready" for step in tracking.progress_steps)
    assert not any(event.label_key == "ready" for event in tracking.timeline)

    polled = order_tracking.build_tracking_status(ready_in_window)
    assert polled.status == "preparing"
    assert polled.display_status_key == "preparing"
    assert order_tracking.display_status_key(ready_in_window) == "preparing"
    # Só a leitura do cliente muda: o pedido de verdade segue pronto.
    ready_in_window.refresh_from_db()
    assert ready_in_window.status == Order.Status.READY


def test_when_the_window_closes_the_customer_reads_ready(ready_in_window):
    order = _close_window(ready_in_window)

    tracking = order_tracking.build_tracking(order)

    assert tracking.status == "ready"
    assert tracking.display_status_key == "ready_pickup"
    assert tracking.promise.state == "ready_pickup"
    assert any(step.key == "ready" and step.state == "current" for step in tracking.progress_steps)
    assert any(event.label_key == "ready" for event in tracking.timeline)
