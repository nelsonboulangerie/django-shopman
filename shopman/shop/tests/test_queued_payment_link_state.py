"""A queued charge notice observes the current payment and order at execution."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.service import PaymentService

from shopman.shop.handlers.notification import NotificationSendHandler
from shopman.shop.services import notification

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("change,reason", [("capture", "payment_link_already_paid"), ("cancel", "payment_link_order_cancelled"), ("expire", "payment_link_expired")])
def test_invalidated_link_is_skipped_before_any_backend(change, reason):
    order = Order.objects.create(ref="QUEUED-LINK", status="accepted", total_q=1200,
        data={"payment": {"method": "link", "checkout_url": "https://example.invalid/synthetic"}})
    notification.send(order, notification.PAYMENT_LINK_TEMPLATE)
    directive = Directive.objects.get(topic=notification.TOPIC, payload__order_ref=order.ref)
    if change == "capture":
        intent = PaymentService.create_intent(order.ref, 1200, "card")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        order.data["payment"]["intent_ref"] = intent.ref
    elif change == "cancel":
        order.status = "cancelled"
    else:
        order.data["payment"]["expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    order.save(update_fields=["status", "data"])
    with patch.object(notification, "deliver_order_notification", return_value=(True, None)) as deliver:
        NotificationSendHandler().handle(message=directive, ctx={})
        deliver.assert_not_called()
    directive.refresh_from_db()
    assert directive.payload["notification_delivery"]["status"] == "skipped"
    assert directive.payload["notification_delivery"]["reason"] == reason


def test_pending_link_still_uses_existing_delivery_and_receipt():
    order = Order.objects.create(ref="VALID-LINK", status="accepted", total_q=1200,
        data={"payment": {"method": "link", "checkout_url": "https://example.invalid/synthetic"}})
    notification.send(order, notification.PAYMENT_LINK_TEMPLATE)
    directive = Directive.objects.get(topic=notification.TOPIC, payload__order_ref=order.ref)

    def accepted(_order, _template, payload):
        payload["notification_delivery"] = {"status": "accepted", "recorded_at": timezone.now().isoformat()}
        return True, None

    with patch.object(notification, "deliver_order_notification", side_effect=accepted) as deliver:
        NotificationSendHandler().handle(message=directive, ctx={})
        directive.refresh_from_db()
        NotificationSendHandler().handle(message=directive, ctx={})
        assert deliver.call_count == 1
