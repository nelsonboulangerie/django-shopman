"""B.I. — custo da TaOn ao lado do frete cobrado, uma vez por corrida."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections import bi_delivery_cost
from shopman.backstage.projections.bi_delivery_cost import build_bi_delivery_cost

pytestmark = pytest.mark.django_db


def _order(ref, *, ride, fee_q=800, status="dispatched"):
    order = Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=5000 + fee_q,
        data={"fulfillment_type": "delivery", "courier": ride})
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=5000, line_total_q=5000)
    if fee_q:
        OrderItem.objects.create(order=order, line_id="fee", sku="__DELIVERY_FEE__", name="Entrega", qty=1,
            unit_price_q=fee_q, line_total_q=fee_q, meta={"type": "delivery_fee"})
    return order


def _ride(id_mch, *, status="F", final_value_q=None, estimate_q=None, ride_orders=None, when=None):
    ride = {"id_mch": id_mch, "status": status, "requested_at": (when or timezone.now()).isoformat()}
    if final_value_q is not None:
        ride["final_value_q"] = final_value_q
    if estimate_q is not None:
        ride["estimate"] = {"value_q": estimate_q}
    if ride_orders:
        ride["ride_orders"] = ride_orders
    return ride


def test_shared_ride_counts_once_and_estimate_fills_the_missing_final_value():
    # Uma corrida com duas paradas: os dois pedidos guardam o valor inteiro.
    shared = _ride("900", final_value_q=1500, ride_orders=["NB-A", "NB-B"])
    _order("NB-A", ride=shared)
    _order("NB-B", ride=shared)
    # Terminou sem valor final: entra pela cotação.
    _order("NB-C", ride=_ride("901", estimate_q=1100), fee_q=0)
    # Cancelada sem valor: não custou.
    _order("NB-D", ride=_ride("902", status="C"))

    report = build_bi_delivery_cost()

    assert bi_delivery_cost.ride_cost_q(shared) == (1500, False)
    assert (report.rides, report.deliveries, report.estimated_rides) == (2, 3, 1)
    assert report.cost_q == 1500 + 1100
    assert report.fee_q == 800 + 800
    assert report.balance_q == 1600 - 2600
    assert report.cost_per_delivery_q == round(2600 / 3)
    (day,) = report.days
    assert (day.rides, day.deliveries, day.cost_q, day.fee_q) == (2, 3, 2600, 1600)


def test_archived_ride_keeps_its_cost_and_cancelled_order_has_no_fee():
    earlier = _ride("910", final_value_q=900, when=timezone.now() - timedelta(days=1))
    _order("NB-E", ride={**_ride("911", final_value_q=1300), "attempts": [earlier]}, status="cancelled")

    report = build_bi_delivery_cost()

    assert report.cost_q == 900 + 1300
    assert report.fee_q == 0
    # O pedido cancelado não conta como entrega levada.
    assert report.deliveries == 0
    assert len(report.days) == 2


def test_shared_ride_never_falls_back_to_a_single_stop_estimate():
    ride = _ride("940", estimate_q=900, ride_orders=["NB-H", "NB-I"])
    assert bi_delivery_cost.ride_cost_q(ride) is None


def test_an_order_in_two_rides_counts_its_fee_once():
    first = _ride("950", final_value_q=1000, when=timezone.now() - timedelta(days=1))
    _order("NB-J", ride={**_ride("951", final_value_q=1100), "attempts": [first]})
    report = build_bi_delivery_cost()
    assert (report.rides, report.deliveries, report.fee_q) == (2, 1, 800)


def test_rides_outside_the_window_stay_out():
    _order("NB-F", ride=_ride("920", final_value_q=1000, when=timezone.now() - timedelta(days=40)))
    assert build_bi_delivery_cost().rides == 0


def test_endpoint_serves_the_reading(client):
    user = User.objects.create_user("gestor", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_bi"))
    client.force_login(user)
    _order("NB-G", ride=_ride("930", final_value_q=1200))
    body = client.get(reverse("api-backstage-bi-delivery-cost")).json()
    assert body["bi"]["cost_q"] == 1200
    assert body["bi"]["fee_q"] == 800
