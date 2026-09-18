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
        if isinstance(result, _Deferred):
            _defer_directive(message, seconds=result.seconds)
            return
        if result == "retryable":
            raise DirectiveTransientError("stock alert provider rejected delivery")


class _Deferred:
    """O provedor não foi chamado e só pode ser depois de ``seconds`` segundos."""

    __slots__ = ("seconds",)

    def __init__(self, seconds: int):
        self.seconds = seconds


def _defer_directive(message, *, seconds: int) -> None:
    """Devolver a directive à fila para depois da janela, sem gastar tentativa.

    Contato ocupado não é falha do provedor: o backoff exponencial do worker (2, 4,
    8 s…) chamaria de novo DENTRO da janela de assentamento e esgotaria as tentativas
    à toa. Mesmo padrão de contenção de ``catalog_projection``.
    """
    from datetime import timedelta

    message.status = "queued"
    message.attempts = max(0, message.attempts - 1)
    message.available_at = timezone.now() + timedelta(seconds=seconds)
    message.save(update_fields=["status", "attempts", "available_at", "updated_at"])


def _claim(delivery_id: int) -> str:
    from shopman.shop.services.notification import (
        lock_subscription_channel,
        subscription_notification_allowed,
    )
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import sku_state

    channel_ref = StockAlertDelivery.objects.filter(pk=delivery_id).values_list(
        "subscription__channel_ref", flat=True
    ).first()
    if channel_ref is None:
        raise DirectiveTerminalError("stock alert delivery not found")
    with transaction.atomic():
        lock_subscription_channel(channel_ref)
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
        if not sub.is_active:
            return _suppress(delivery, "subscription_inactive")
        try:
            from shopman.shop.services.marketing_age import customer_is_known_minor

            if customer_is_known_minor(sub.customer_ref):
                return _suppress(delivery, "known_minor")
        except Exception as exc:
            raise DirectiveTransientError("age_check_failed") from exc
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
        suppressed = _suppress_outside_whatsapp_canary(delivery)
        if suppressed:
            return suppressed

        delivery.status = StockAlertDelivery.Status.CLAIMED
        delivery.claimed_at = timezone.now()
        delivery.last_error_code = ""
        delivery.save(update_fields=["status", "claimed_at", "last_error_code", "updated_at"])
        return "claimed"


def _send_claimed(delivery_id: int) -> str | _Deferred:
    from shopman.shop.services.notification import (
        lock_subscription_channel,
        subscription_notification_allowed,
    )
    from shopman.shop.services.observability import operational_event
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import sku_state, stock_alerts

    channel_ref = StockAlertDelivery.objects.filter(pk=delivery_id).values_list(
        "subscription__channel_ref", flat=True
    ).first()
    if channel_ref is None:
        raise DirectiveTerminalError("stock alert delivery not found")
    with transaction.atomic():
        lock_subscription_channel(channel_ref)
        delivery = (
            StockAlertDelivery.objects.select_for_update()
            .select_related("subscription", "occurrence")
            .get(pk=delivery_id)
        )
        if delivery.status != StockAlertDelivery.Status.CLAIMED:
            return delivery.status
        sub = delivery.subscription
        occurrence = delivery.occurrence
        if not sub.is_active or not subscription_notification_allowed(
            customer_ref=sub.customer_ref, phone=sub.contact_phone
        ):
            return _suppress(delivery, "subscription_inactive_before_send")
        try:
            from shopman.shop.services.marketing_age import customer_is_known_minor

            if customer_is_known_minor(sub.customer_ref):
                return _suppress(delivery, "known_minor_before_send")
        except Exception as exc:
            raise DirectiveTransientError("age_recheck_failed") from exc
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
        from shopman.shop.services import manychat_marketing_safety

        if not result.success and manychat_marketing_safety.is_flow_deferral(getattr(result, "error", None)):
            # Nada foi escrito no ManyChat: a pessoa ainda tem outra mensagem com flow
            # assentando. Volta para a fila, sem virar "tentar novamente" nem incerto.
            delivery.status = StockAlertDelivery.Status.QUEUED
            delivery.claimed_at = None
            delivery.last_error_code = result.error
            delivery.save(update_fields=["status", "claimed_at", "last_error_code", "updated_at"])
            settle = manychat_marketing_safety.flow_settle_seconds()
            return _Deferred(max(settle, int(getattr(result, "retry_after_seconds", None) or 0)))

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


def _suppress_outside_whatsapp_canary(delivery) -> str:
    """No ensaio do WhatsApp, quem está fora da lista não vira tentativa.

    Em ``blocked`` nada muda (o adapter continua recusando, como antes); em ``canary``
    a supressão aqui, com motivo explícito, evita a fila de retries de uma recusa
    certa. Só vale quando o aviso sai pelo ManyChat.
    """
    from shopman.shop.services import manychat_marketing_safety
    from shopman.storefront.services import stock_alerts

    sub = delivery.subscription
    if not manychat_marketing_safety.canary_excludes(sub.customer_ref):
        return ""
    if stock_alerts.delivery_backend(sub) != "manychat":
        return ""
    return _suppress(delivery, manychat_marketing_safety.CANARY_RECIPIENT_EXCLUDED_CODE)


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
