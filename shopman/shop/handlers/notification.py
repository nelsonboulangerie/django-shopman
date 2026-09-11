"""
Notification handler — processa directives notification.send.

Suporta dois tipos de notificação:
- Pedido: payload com order_ref → delega para services.notification.deliver_order_notification()
- Sistema: payload com event (ex: stock.alert) → notifica operador via email/console

O handler é fino: lê o directive, obtém o pedido, delega ao service, escreve o status.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify
from shopman.shop.services import notification as notification_svc
from shopman.shop.services.observability import operational_event_on_commit

logger = logging.getLogger(__name__)


def _enrich_system_context(template: str, raw_context: object) -> dict:
    """Resolve human labels at the integration boundary, keeping Stockman generic."""

    context = dict(raw_context) if isinstance(raw_context, dict) else {}
    if template != "stock_alert":
        return context

    sku = str(context.get("sku") or "").strip()
    if not sku or str(context.get("product_name") or "").strip():
        return context
    try:
        from shopman.offerman.models import Product

        product_name = (
            Product.objects.filter(sku=sku)
            .values_list("name", flat=True)
            .first()
        )
    except Exception:
        # O alerta continua útil pelo SKU se o catálogo estiver indisponível; o
        # worker registra o diagnóstico sem incluir destinatário ou conteúdo.
        logger.warning(
            "notification.system: product label unavailable for sku=%s",
            sku,
            exc_info=True,
        )
        return context
    if product_name:
        context["product_name"] = str(product_name).strip()
    return context


class NotificationSendHandler:
    """Processa directives de notificação. Topic: notification.send"""

    topic = NOTIFICATION_SEND

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        # Stock alert (no order_ref, has event field)
        if not payload.get("order_ref") and payload.get("event"):
            self._handle_system_notification(message)
            return

        self._handle_order_notification(message)

    def _handle_order_notification(self, message: Directive) -> None:
        """Handle order-related notifications — delega ao service."""
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_svc

        payload = message.payload
        order_ref = payload.get("order_ref")
        template = payload.get("template", "generic")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")


        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        # A fresh lock serializes worker redelivery, but never covers transport I/O.
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            fresh = Directive.objects.select_for_update().get(pk=message.pk)
            payload = dict(fresh.payload or {})
            previous = payload.get("notification_delivery") or {}
            if previous.get("status") in {"accepted", "skipped"}:
                return
            if previous.get("status") in {"started", "unknown"} or (
                fresh.attempts > 1 and previous.get("outcome") != "not_applied"
            ):
                raise DirectiveTerminalError("notification acceptance unconfirmed; automatic resend blocked")
            # Guarda: pular reminders de pagamento se já pago
            if template == "payment.reminder":
                payment_status = payment_svc.get_payment_status(order) or ""
                if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                    self._record_skip(fresh, "payment_not_pending")
                    return

            # Enqueue eligibility can expire while the worker is unavailable. Reuse
            # the same canonical link guard; do not send an obsolete charge notice.
            if template == notification_svc.PAYMENT_LINK_TEMPLATE:
                refusal = notification_svc.payment_link_resend_refusal(order, check_delivery=False)
                if refusal is not None:
                    self._record_skip(fresh, refusal.code)
                    return

            payload["notification_delivery"] = {
                "status": "started", "recorded_at": timezone.now().isoformat(),
            }
            fresh.payload = payload
            fresh.save(update_fields=["payload", "updated_at"])
            self._observe(fresh)
        message.payload = payload

        success, last_error = notification_svc.deliver_order_notification(order, template, payload)
        # ``deliver_order_notification`` registra aceite, skip legítimo ou a
        # última falha no dicionário recebido. Persistir antes de retornar/lançar
        # torna o resultado observável no mesmo fato que já governa retries.
        if payload.get("notification_delivery"):
            with transaction.atomic():
                fresh = Directive.objects.select_for_update().get(pk=message.pk)
                current = dict(fresh.payload or {})
                if (current.get("notification_delivery") or {}).get("status") != "accepted":
                    current["notification_delivery"] = payload["notification_delivery"]
                    fresh.payload = current
                    fresh.save(update_fields=["payload", "updated_at"])
                    self._observe(fresh)
                message.payload = fresh.payload

        if success:
            return
        if (payload.get("notification_delivery") or {}).get("status") in {"started", "unknown"}:
            self._escalate(order_ref, template, None, unknown=True)
            raise DirectiveTerminalError("notification acceptance unconfirmed; automatic resend blocked")

        # Todos os backends falharam — escalate if exhausted, then raise
        exhausted = message.attempts >= 5
        if exhausted:
            self._escalate(order_ref, template, last_error)
            raise DirectiveTerminalError(last_error or "all backends failed after 5 attempts")

        raise DirectiveTransientError(last_error or "all backends failed")

    @staticmethod
    def _observe(message: Directive) -> None:
        delivery = (message.payload or {}).get("notification_delivery") or {}
        operational_event_on_commit(
            "operator.effect.state", directive_id=message.pk, topic=message.topic,
            resource_ref=(message.payload or {}).get("order_ref"),
            worker_attempt=message.attempts, effect_state=delivery.get("status"),
            external_id=delivery.get("message_id"), recorded_at=delivery.get("recorded_at"),
            unknown_reason="acceptance_unconfirmed" if delivery.get("status") == "unknown" else None,
        )

    def _escalate(self, order_ref: str, template: str, last_error: str | None, *, unknown: bool = False) -> None:
        """Cria OperatorAlert quando entrega de notificação é exaurida."""
        try:
            from shopman.shop.adapters import alert as alert_adapter

            # Um replay/manual retry do mesmo fato não deve gerar uma pilha de
            # alertas idênticos. Enquanto a causa estiver aberta, ela é uma só.
            if alert_adapter.recent_exists(
                "notification_failed",
                timezone.now(),
                message_contains=f"'{template}'",
                order_ref=order_ref or "",
            ):
                return
            alert_adapter.create(
                "notification_failed",
                "error",
                (
                    (f"Aceite da notificação '{template}' não confirmado; confira o envio antes de reenviar. "
                     if unknown else f"Notificação '{template}' falhou após 5 tentativas ")
                    +
                    f"para pedido {order_ref}. Último erro: {last_error or 'desconhecido'}"
                ),
                order_ref=order_ref or "",
            )
            logger.warning(
                "notification_escalated order=%s template=%s",
                order_ref, template,
            )
        except Exception:
            logger.exception("Failed to create OperatorAlert for notification failure")

    @staticmethod
    def _record_skip(message: Directive, reason: str) -> None:
        payload = dict(message.payload or {})
        payload["notification_delivery"] = {
            "status": "skipped",
            "reason": reason,
            "recorded_at": timezone.now().isoformat(),
        }
        message.payload = payload
        message.save(update_fields=["payload", "updated_at"])

    def _handle_system_notification(self, message: Directive) -> None:
        """Handle system notifications (stock alerts, etc.) — routed to operator."""
        payload = message.payload
        event = payload.get("event", "system")
        context = payload.get("context", {})

        # Normalize event → template name (stock.alert.triggered → stock_alert)
        if "stock.alert" in event:
            template = "stock_alert"
            context = _stock_alert_context(context)
        else:
            template = context.get("template") or event
        context = _enrich_system_context(template, context)

        fallback_recipient = getattr(settings, "SHOPMAN_OPERATOR_EMAIL", None) or getattr(
            settings, "DEFAULT_FROM_EMAIL", "admin@shopman.local"
        )
        recipient = str(payload.get("recipient") or fallback_recipient)
        recipients = payload.get("recipients") if isinstance(payload.get("recipients"), dict) else {}

        result = None
        from shopman.shop.notifications import get_backend as _get_backend

        for backend_name in _system_backends(payload):
            backend_recipient = str(recipients.get(backend_name) or recipient or "").strip()
            if not backend_recipient:
                continue

            backend_module = _get_backend(backend_name)
            if backend_module and hasattr(backend_module, "is_available"):
                if not backend_module.is_available(backend_recipient):
                    logger.debug(
                        "notification.system: backend=%s not configured, skipping",
                        backend_name,
                    )
                    continue
            result = notify(event=template, recipient=backend_recipient, context=context, backend=backend_name)
            if result.success:
                return

        # All backends failed
        exhausted = message.attempts >= 5
        if exhausted:
            self._escalate("", event, result.error if result else None)
            raise DirectiveTerminalError((result.error if result else "unknown")[:500])

        raise DirectiveTransientError((result.error if result else "unknown")[:500])


def _system_backends(payload: dict) -> list[str]:
    raw = payload.get("backends") or ["email", "console"]
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",")]
    if not isinstance(raw, list):
        return ["email", "console"]
    backends = [str(item).strip() for item in raw if str(item).strip()]
    return backends or ["email", "console"]


def _stock_alert_context(context: dict) -> dict:
    """Nome humano + SKU para o alerta operacional de estoque.

    Stockman permanece agnóstico ao catálogo e publica apenas o SKU. A borda
    orquestradora enriquece antes de escolher o canal; assim e-mail, console e
    futuros adapters recebem a mesma descrição sem acoplar o kernel de estoque
    ao Offerman.
    """
    enriched = dict(context or {})
    sku = str(enriched.get("sku") or "").strip()
    product_name = str(enriched.get("product_name") or "").strip()
    if sku and not product_name:
        try:
            from shopman.shop.projections import catalog_context

            product = catalog_context.get_product(sku)
            product_name = str(getattr(product, "name", "") or "").strip()
        except Exception:  # silêncio-deliberado: o alerta degrada para o SKU já presente
            logger.debug(
                "notification.system: product lookup failed for stock alert sku=%s",
                sku,
                exc_info=True,
            )
    enriched["product_name"] = product_name or sku
    enriched["product_label"] = (
        f"{product_name} ({sku})" if product_name and product_name != sku else sku
    )
    return enriched


__all__ = ["NotificationSendHandler"]
