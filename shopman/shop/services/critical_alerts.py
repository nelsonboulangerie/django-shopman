"""Durable critical email paging, debounced by type; unknown delivery is fenced."""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify

logger = logging.getLogger(__name__)


def enqueue(alert):
    recipient = str(getattr(settings, "SHOPMAN_OPERATOR_EMAIL", "") or "").strip()
    if not recipient:
        logger.warning("operator_alert.external_recipient_missing")
        return None
    with transaction.atomic():
        receipt, created = IdempotencyKey.objects.get_or_create(
            scope="operator_critical_email", key=alert.type,
            defaults={"status": "in_progress", "expires_at": None},
        )
        receipt = IdempotencyKey.objects.select_for_update().get(pk=receipt.pk)
        now = timezone.now()
        if not created and receipt.expires_at and receipt.expires_at > now:
            return None
        task = Directive.objects.create(topic=NOTIFICATION_SEND, payload={
            "event": "operator_critical", "recipient": recipient, "backends": ["email"],
            "alert_id": alert.pk,
            # Never copy arbitrary provider errors/customer data into an email.
            "context": {"alert_type": alert.type, "order_ref": alert.order_ref},
        })
        receipt.status = "done"
        receipt.expires_at = now + timedelta(minutes=15)
        receipt.response_body = {"directive_id": task.pk}
        receipt.save(update_fields=["status", "expires_at", "response_body"])
        return task


def deliver(message):
    from shopman.shop.adapters import notification_email

    with transaction.atomic():
        task = Directive.objects.select_for_update().get(pk=message.pk)
        payload = dict(task.payload or {})
        state = payload.get("critical_delivery")
        if state == "accepted":
            return
        if state in {"started", "unknown"}:
            raise DirectiveTerminalError("critical email acceptance unconfirmed; inspect original delivery")
        if not notification_email.is_available(payload["recipient"]):
            raise DirectiveTransientError("critical email backend unavailable")
        payload["critical_delivery"] = "started"
        task.payload = payload
        task.save(update_fields=["payload", "updated_at"])
    result = notify(event="operator_critical", recipient=payload["recipient"],
                    context=payload["context"], backend="email")
    state = "accepted" if result.success else "unknown" if result.outcome_unknown else "rejected"
    with transaction.atomic():
        task = Directive.objects.select_for_update().get(pk=message.pk)
        task.payload = {**task.payload, "critical_delivery": state}
        task.save(update_fields=["payload", "updated_at"])
    if state == "unknown":
        raise DirectiveTerminalError("critical email acceptance unconfirmed; inspect original delivery")
    if state == "rejected":
        raise DirectiveTransientError("critical email rejected")
