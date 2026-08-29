"""Payment timeout handler — cancels unpaid digital orders at the payment deadline."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import PAYMENT_TIMEOUT

_UNCERTAIN_STATUSES = {"unknown"}


class PaymentTimeoutHandler:
    """Resolve unpaid PIX/card orders once the displayed payment timer expires."""

    topic = PAYMENT_TIMEOUT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_service
        from shopman.shop.services.cancellation import cancel

        payload = message.payload or {}
        expires_at = _parse_deadline(payload.get("expires_at"))
        if expires_at and timezone.now() < expires_at:
            message.status = "queued"
            message.available_at = expires_at
            message.save(update_fields=["status", "available_at", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        if order.status not in {Order.Status.NEW, Order.Status.ACCEPTED}:
            return

        payment_data = (order.data or {}).get("payment") or {}
        if payload.get("intent_ref") and payment_data.get("intent_ref") != payload["intent_ref"]:
            return

        method = str(payment_data.get("method") or "").lower()
        status = (payment_service.get_payment_status(order) or "").lower()
        if payment_service.has_sufficient_captured_payment(order) is True:
            return
        if method == "card" and status == "authorized":
            return
        if status in _UNCERTAIN_STATUSES:
            return

        # Última linha contra webhook perdido: perguntar ao gateway antes de
        # cancelar um pedido digital possivelmente pago (PIX e cartão).
        from shopman.orderman.exceptions import DirectiveTransientError

        gateway_state = payment_service.settle_from_gateway(order)
        if gateway_state in {"paid", "authorized"}:
            # ``authorized`` é o cartão em ``requires_capture``: o dinheiro está
            # reservado para a loja e a captura é do lifecycle. Cancelar aqui
            # seria devolver "não deu certo" a quem pagou.
            return
        if gateway_state == "indeterminate":
            raise DirectiveTransientError(
                "gateway indisponível para verificar pagamento antes do cancel"
            )

        payment_service.cancel(order, reason="payment_timeout")
        cancelled = cancel(
            order,
            reason="payment_timeout",
            actor="payment.timeout",
            extra_data={"payment_timeout_at": timezone.now().isoformat()},
        )
        if cancelled:
            from shopman.shop.services import notification

            notification.send(order, "payment_expired")


def _parse_deadline(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if not timezone.is_aware(dt):
        return timezone.make_aware(dt)
    return dt


__all__ = ["PaymentTimeoutHandler"]
