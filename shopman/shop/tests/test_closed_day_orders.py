"""Evidência direta de shopman.shop.services.closed_day_orders."""

from __future__ import annotations

from datetime import date

from shopman.backstage.models import OperatorAlert
from shopman.orderman.models import Order
from shopman.shop.services import closed_day_orders


def test_closed_day_orders_finds_open_orders_and_alerts(db):
    Order.objects.create(
        ref="ENC-PAGA",
        channel_ref="web",
        status="accepted",
        total_q=5000,
        data={"delivery_date": "2026-12-24"},
    )
    Order.objects.create(
        ref="ENC-CANC",
        channel_ref="web",
        status="cancelled",
        total_q=3000,
        data={"delivery_date": "2026-12-24"},
    )

    orders = closed_day_orders.open_orders_committed_between(date(2026, 12, 24))
    assert [order.ref for order in orders] == ["ENC-PAGA"]

    created = closed_day_orders.alert_orders_on_closed_day(orders, reason="teste")
    assert created == 1
    assert OperatorAlert.objects.filter(
        type="order_on_closed_day", order_ref="ENC-PAGA"
    ).count() == 1
