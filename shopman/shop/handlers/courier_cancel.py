"""Durable cancellation of one observed ride, using the existing Directive worker."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters import get_adapter
from shopman.shop.adapters.courier_machine import CANCELLABLE_STATUSES, CourierError
from shopman.shop.directives import COURIER_CANCEL
from shopman.shop.services import courier

logger = logging.getLogger(__name__)


class CourierCancelHandler:
    topic = COURIER_CANCEL

    def handle(self, *, message: Directive, ctx: dict) -> None:
        message.refresh_from_db()
        payload = message.payload or {}
        order = Order.objects.filter(ref=payload.get("order_ref")).first()
        if order is None:
            return
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            message = Directive.objects.select_for_update().get(pk=message.pk)
            state = (message.payload or {}).get("cancel_attempt", {}).get("state")
            if state == "not_applied":
                return
            if state == "accepted":
                self._adopt(order, message)
                return
            if state not in {"started", "unknown"}:
                block = courier.get_block(order)
                if block.get("id_mch") != payload.get("courier_ref") or block.get("status") not in CANCELLABLE_STATUSES:
                    self._record(message, "not_applied")
                    return
                adapter = get_adapter("courier")
                if adapter is None:
                    self._record(message, "not_applied")
                    raise DirectiveTerminalError("Adapter indisponível; nenhum cancelamento foi enviado.")
                self._record(message, "started", started_at=timezone.now().isoformat())
        if state in {"started", "unknown"}:
            self._unknown(order, message)
        try:
            accepted = adapter.cancel(payload["courier_ref"], reason_id=payload.get("reason_id"))
        except CourierError as exc:
            if exc.outcome_unknown:
                self._unknown(order, message)
            self._record(message, "not_applied")
            raise DirectiveTerminalError(f"A central recusou o cancelamento: {exc}") from exc
        except Exception:
            logger.warning("courier.cancel_unknown order=%s directive=%s", order.ref, message.pk, exc_info=True)
            self._unknown(order, message)
        if accepted is not True:
            self._unknown(order, message)
        self._record(message, "accepted")
        self._adopt(order, message)

    @staticmethod
    @transaction.atomic
    def _record(message, state, **values):
        message = Directive.objects.select_for_update().get(pk=message.pk)
        payload = dict(message.payload or {})
        receipt = dict(payload.get("cancel_attempt") or {})
        if receipt.get("state") == "accepted" and state != "accepted":
            return
        payload["cancel_attempt"] = {**receipt, **values, "state": state, "updated_at": timezone.now().isoformat()}
        message.payload = payload
        message.save(update_fields=["payload", "updated_at"])

    @staticmethod
    def _adopt(order, message):
        # apply_status compares this observed ride under its own fresh Order lock.
        if courier.get_block(order).get("id_mch") != message.payload.get("courier_ref"):
            return
        courier.apply_status(order, "C", source=f"operator:{message.payload.get('actor', '')}")

    def _unknown(self, order, message):
        from shopman.shop.adapters import alert as alert_adapter

        self._record(message, "unknown")
        explanation = "Cancelamento sem resultado confirmado. Confira esta corrida na central antes de reenviar."
        courier._emit_sse(order, {"kind": "cancel_unknown"})
        try:
            if not alert_adapter.recent_exists("integration_failed", message.created_at, order_ref=order.ref, message_contains="Cancelamento sem resultado confirmado"):
                alert_adapter.create("integration_failed", "critical", explanation, order_ref=order.ref)
        except Exception:
            logger.warning("courier.cancel_alert_failed order=%s directive=%s", order.ref, message.pk, exc_info=True)
        raise DirectiveTerminalError(explanation)
