"""Directive handler for one occurrence-scoped stock alert delivery."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError

from shopman.shop.directives import STOCK_ALERT_DELIVER

logger = logging.getLogger(__name__)


class StockAlertDeliveryHandler:
    topic = STOCK_ALERT_DELIVER

    def handle(self, *, message, ctx: dict) -> None:
        del ctx
        delivery_id = (message.payload or {}).get("delivery_id")
        if not delivery_id:
            raise DirectiveTerminalError("missing delivery_id")

        outcome = _claim(int(delivery_id))
        if outcome == "indeterminate":
            _alert_indeterminate(int(delivery_id))
        if outcome != "claimed":
            return
        result = _send_claimed(int(delivery_id))
        if result == "retryable":
            raise DirectiveTransientError("stock alert provider rejected delivery")


def _claim(delivery_id: int) -> str:
    from shopman.shop.services.notification import (
        lock_subscription_channel,
        subscription_notification_allowed,
    )
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import sku_state

    with transaction.atomic():
        delivery = (
            StockAlertDelivery.objects.select_for_update()
            .select_related("subscription", "occurrence")
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None:
            raise DirectiveTerminalError("stock alert delivery not found")
        if delivery.status in {
            StockAlertDelivery.Status.ACCEPTED,
            StockAlertDelivery.Status.SUPPRESSED,
            StockAlertDelivery.Status.INDETERMINATE,
        }:
            return delivery.status
        if delivery.status == StockAlertDelivery.Status.CLAIMED:
            _mark_indeterminate(delivery, "stale_claim_before_retry")
            return StockAlertDelivery.Status.INDETERMINATE

        sub = delivery.subscription
        occurrence = delivery.occurrence
        lock_subscription_channel(sub.channel_ref)
        if not sub.is_active:
            return _suppress(delivery, "subscription_inactive")
        if occurrence.status != occurrence.Status.ELIGIBLE:
            return _suppress(delivery, f"occurrence_{occurrence.status}")
        if not subscription_notification_allowed(customer_ref=sub.customer_ref, phone=sub.contact_phone):
            return _suppress(delivery, "consent_not_allowed")
        try:
            state = sku_state.resolve(sku=sub.sku, channel_ref=sub.channel_ref)
        except Exception as exc:
            raise DirectiveTransientError("availability_check_failed") from exc
        if not state.can_add_to_cart:
            return _suppress(delivery, "unavailable_before_send")

        delivery.status = StockAlertDelivery.Status.CLAIMED
        delivery.claimed_at = timezone.now()
        delivery.last_error_code = ""
        delivery.save(update_fields=["status", "claimed_at", "last_error_code", "updated_at"])
        return "claimed"


def _send_claimed(delivery_id: int) -> str:
    from shopman.shop.services.notification import (
        lock_subscription_channel,
        subscription_notification_allowed,
    )
    from shopman.shop.services.observability import operational_event
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import sku_state, stock_alerts

    with transaction.atomic():
        delivery = (
            StockAlertDelivery.objects.select_for_update()
            .select_related("subscription", "occurrence")
            .get(pk=delivery_id)
        )
        if delivery.status != StockAlertDelivery.Status.CLAIMED:
            return delivery.status
        sub = delivery.subscription
        occurrence = delivery.occurrence
        lock_subscription_channel(sub.channel_ref)
        if not sub.is_active or not subscription_notification_allowed(
            customer_ref=sub.customer_ref, phone=sub.contact_phone
        ):
            return _suppress(delivery, "subscription_inactive_before_send")
        occurrence.refresh_from_db(fields=["status"])
        if occurrence.status != occurrence.Status.ELIGIBLE:
            return _suppress(delivery, f"occurrence_{occurrence.status}_before_send")
        try:
            state = sku_state.resolve(sku=sub.sku, channel_ref=sub.channel_ref)
        except Exception as exc:
            raise DirectiveTransientError("availability_recheck_failed") from exc
        if not state.can_add_to_cart:
            return _suppress(delivery, "unavailable_at_provider_boundary")

        event = "stock_arrived" if delivery.occurrence.event_type == "stock_back" else "production_ready"
        result = stock_alerts._deliver(
            sub,
            product_name=stock_alerts.product_name(sub.sku),
            event=event,
            available_qty=delivery.occurrence.available_qty,
        )
        if result.success:
            accepted_at = timezone.now()
            delivery.status = StockAlertDelivery.Status.ACCEPTED
            delivery.accepted_at = accepted_at
            delivery.provider_receipt_ref = str(result.message_id or "")[:160]
            delivery.last_error_code = ""
            delivery.save(
                update_fields=[
                    "status",
                    "accepted_at",
                    "provider_receipt_ref",
                    "last_error_code",
                    "updated_at",
                ]
            )
            type(sub).objects.filter(pk=sub.pk).update(notified_at=accepted_at, dispatch_accepted_at=accepted_at)
            operational_event(
                "stock_alert.delivery_accepted",
                delivery_ref=str(delivery.ref),
                occurrence_ref=str(delivery.occurrence.ref),
                event_type=delivery.occurrence.event_type,
            )
            return StockAlertDelivery.Status.ACCEPTED

        if getattr(result, "outcome_unknown", False) is True:
            error = getattr(result, "error", "")
            _mark_indeterminate(delivery, error if isinstance(error, str) and error else "provider_outcome_unknown")
            transaction.on_commit(lambda: _alert_indeterminate(delivery.pk))
            return StockAlertDelivery.Status.INDETERMINATE

        delivery.status = StockAlertDelivery.Status.RETRYABLE
        delivery.claimed_at = None
        error = getattr(result, "error", "")
        delivery.last_error_code = (error if isinstance(error, str) and error else "provider_rejected")[:100]
        delivery.save(update_fields=["status", "claimed_at", "last_error_code", "updated_at"])
        return "retryable"


def _suppress(delivery, reason: str) -> str:
    delivery.status = delivery.Status.SUPPRESSED
    delivery.last_error_code = reason[:100]
    delivery.save(update_fields=["status", "last_error_code", "updated_at"])
    return delivery.Status.SUPPRESSED


def _mark_indeterminate(delivery, reason: str) -> None:
    delivery.status = delivery.Status.INDETERMINATE
    delivery.last_error_code = reason[:100]
    delivery.save(update_fields=["status", "last_error_code", "updated_at"])


def _alert_indeterminate(delivery_id: int) -> None:
    from shopman.shop.services.observability import create_operator_alert
    from shopman.storefront.models import StockAlertDelivery

    delivery = StockAlertDelivery.objects.filter(pk=delivery_id).only("ref").first()
    if delivery is None:
        return
    create_operator_alert(
        type="stock_alert_dispatch_unknown",
        severity="warning",
        message=(
            "Resultado do aviso incerto. Consulte o provedor antes de repetir; "
            f"delivery_ref={delivery.ref}; runbook=docs/runbooks/stock-alert-delivery.md"
        ),
        dedupe_key=f"stock-alert:{delivery.ref}",
    )
