"""Pending iFood rejection notifies once on CAN, without duplicating local rejects."""

from contextlib import ExitStack
from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop import lifecycle
from shopman.shop.models import Channel
from shopman.shop.services import cancellation, operator_orders


@pytest.fixture
def no_external_effects(db):
    with ExitStack() as stack:
        for target in (
            "shopman.shop.services.kds.cancel_tickets", "shopman.shop.services.stock.release",
            "shopman.shop.services.stock.revert_fulfilled", "shopman.shop.lifecycle._settle_cancelled_payment",
            "shopman.shop.lifecycle._release_coupon_use", "shopman.shop.services.fiscal.cancel",
            "shopman.shop.services.loyalty.revoke", "shopman.shop.services.loyalty.restore",
        ):
            stack.enter_context(patch(target))
        yield


def make_order(channel, external_ref):
    Channel.objects.create(ref=channel, name=channel)
    return Order.objects.create(ref="NOTIFY-REJECT", channel_ref=channel, external_ref=external_ref, status="new")


def reject(order):
    operator_orders.reject_order(
        order, reason="Sem estoque", actor="operator:a", rejected_by="a", cancellation_code="501",
        prepared_identity=(order.channel_ref, order.external_ref),
    )
    order.refresh_from_db()


def notifications(order):
    return Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref)


def test_pending_rejection_sends_no_notice_until_can_then_one_final_notice(no_external_effects):
    order = make_order("ifood", "official-order")
    reject(order)
    assert order.status == "new"
    assert not notifications(order).exists()
    cancellation.cancel(order, reason="Cancelamento confirmado pelo iFood", actor="system:ifood", extra_data={"ifood_cancelled": True})
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert order.data["rejected_by"] == "a"
    lifecycle.dispatch(order, "on_cancelled")
    lifecycle.dispatch(order, "on_cancelled")
    assert notifications(order).count() == 1
    assert notifications(order).get().payload["template"] == "order_cancelled"


@pytest.mark.parametrize(("channel", "external_ref"), [("web", ""), ("ifood", "IFOOD-SIM-123")])
def test_local_rejection_does_not_add_a_second_cancellation_notice(no_external_effects, channel, external_ref):
    order = make_order(channel, external_ref)
    reject(order)
    assert order.status == "cancelled"
    lifecycle.dispatch(order, "on_cancelled")
    assert notifications(order).count() == 1
    assert notifications(order).get().payload["template"] == "order_rejected"
