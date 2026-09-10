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
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify
from shopman.shop.services import notification as notification_svc

logger = logging.getLogger(__name__)


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

        # Se a prova de aceite já foi persistida e o worker caiu antes de marcar
        # a Directive como done, o replay conclui sem novo envio. Continua
        # existindo a janela inevitável entre o aceite externo e este save; sem
        # chave idempotente aceita pelo provider não há como fechá-la localmente.
        previous_delivery = payload.get("notification_delivery") or {}
        if previous_delivery.get("status") in {"accepted", "skipped"}:
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        # Guarda: pular reminders de pagamento se já pago
        if template == "payment.reminder":
            payment_status = payment_svc.get_payment_status(order) or ""
            if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                self._record_skip(message, "payment_not_pending")
                return

        success, last_error = notification_svc.deliver_order_notification(order, template, payload)
        # ``deliver_order_notification`` registra aceite, skip legítimo ou a
        # última falha no dicionário recebido. Persistir antes de retornar/lançar
        # torna o resultado observável no mesmo fato que já governa retries.
        if payload.get("notification_delivery"):
            message.payload = payload
            message.save(update_fields=["payload", "updated_at"])

        if success:
            return

        # Todos os backends falharam — escalate if exhausted, then raise
        exhausted = message.attempts >= 5
        if exhausted:
            self._escalate(order_ref, template, last_error)
            raise DirectiveTerminalError(last_error or "all backends failed after 5 attempts")

        raise DirectiveTransientError(last_error or "all backends failed")

    def _escalate(self, order_ref: str, template: str, last_error: str | None) -> None:
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
                    f"Notificação '{template}' falhou após 5 tentativas "
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
        else:
            template = context.get("template") or event

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


__all__ = ["NotificationSendHandler"]
