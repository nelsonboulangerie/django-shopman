"""Courier dispatch handler — abre a corrida na Machine (Directive ``courier.dispatch``).

Enfileirado por ``courier.request_dispatch`` quando um pedido delivery fica
pronto (lifecycle ``on_ready`` com ``fulfillment.courier="auto"``) ou pelo
re-despacho manual do operador no gestor. Resultado remoto desconhecido exige
verificação; replay de aceite conhecido apenas recupera o vínculo local.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_DISPATCH

logger = logging.getLogger(__name__)


class CourierDispatchHandler:
    """Abre a solicitação de entrega no adapter courier e grava a corrida no pedido."""

    topic = COURIER_DISPATCH

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.adapters import get_adapter
        from shopman.shop.adapters.courier_machine import CourierError
        from shopman.shop.services import courier
        from shopman.shop.services.order_helpers import get_fulfillment_type
        from shopman.shop.services.remote_mutations import mutation_fingerprint

        message.refresh_from_db()
        payload = message.payload or {}
        order = Order.objects.filter(ref=payload.get("order_ref")).first()
        if order is None:
            return
        receipt = payload.get("dispatch_attempt", {})
        state = receipt.get("state")
        if state == "accepted":
            self._adopt(order, message, receipt["courier_ref"])
            return
        if state in {"started", "unknown"} or (not state and message.attempts > 1):
            self._unknown(order, message, "Tentativa anterior sem resultado confirmado.")
        if state in {"not_applied", "inert"}:
            return
        if get_fulfillment_type(order) != "delivery" or order.status not in {Order.Status.READY, Order.Status.DISPATCHED}:
            self._set_attempt(message, "not_applied")
            return
        if courier.has_active_ride(order):
            return
        adapter = get_adapter("courier")
        if adapter is None:
            self._set_attempt(message, "inert")
            return
        courier.estimate_for_order(order, store=True)
        try:
            body = courier.build_machine_payload(order)
        except ValueError as exc:
            self._set_attempt(message, "not_applied")
            self._record_terminal_failure(order, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc

        # Claim the exact attempt locally, then release all locks before I/O.
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            message = Directive.objects.select_for_update().get(pk=message.pk)
            current = (message.payload or {}).get("dispatch_attempt", {})
            if current.get("state") == "accepted":
                self._adopt(order, message, current["courier_ref"])
                return
            if current.get("state") in {"not_applied", "inert"}:
                return
            other = courier.unresolved_dispatch(order, exclude_pk=message.pk)
            if other is not None and not current:
                self._set_attempt(message, "not_applied", blocked_by=other.pk)
                blocked_elsewhere = True
            else:
                blocked_elsewhere = False
            blocked = bool(current) or other is not None
            if not blocked:
                if order.status not in {Order.Status.READY, Order.Status.DISPATCHED} or courier.has_active_ride(order):
                    self._set_attempt(message, "not_applied")
                    return
                # Use the freshly locked order, never the pre-estimate snapshot.
                body = courier.build_machine_payload(order)
                self._set_attempt(message, "started", fingerprint=mutation_fingerprint(body), started_at=timezone.now().isoformat())
        if blocked_elsewhere:
            raise DirectiveTerminalError("Outro despacho exige verificação; esta tarefa não chamou a central.")
        if blocked:
            self._unknown(order, message, "Outro processo ou tentativa já iniciou este despacho.")

        try:
            result = adapter.dispatch(body)
        except CourierError as exc:
            if exc.outcome_unknown:
                self._unknown(order, message, str(exc))
            self._set_attempt(message, "not_applied")
            self._record_terminal_failure(order, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc
        except Exception as exc:
            self._unknown(order, message, str(exc))
        if result.inert:
            self._set_attempt(message, "inert")
            return
        if not result.courier_ref:
            self._unknown(order, message, "A central não devolveu a referência da solicitação.")
        # Persist acceptance before local adoption. If adoption fails, retry only
        # links this known ride; it never creates another remote solicitation.
        self._set_attempt(message, "accepted", courier_ref=result.courier_ref)
        self._adopt(order, message, result.courier_ref)

    @staticmethod
    def _set_attempt(message, state, **values):
        with transaction.atomic():
            locked = Directive.objects.select_for_update().get(pk=message.pk)
            payload = dict(locked.payload or {})
            receipt = dict(payload.get("dispatch_attempt") or {})
            receipt.update(state=state, updated_at=timezone.now().isoformat(), **values)
            payload["dispatch_attempt"] = receipt
            locked.payload = payload
            locked.save(update_fields=["payload", "updated_at"])
            message.payload = payload

    def _unknown(self, order, message, detail):
        self._set_attempt(message, "unknown")
        explanation = "Despacho sem resultado confirmado. Confira na central antes de abrir outra corrida. " + detail
        self._record_terminal_failure(order, explanation)
        raise DirectiveTerminalError(explanation)

    def _adopt(self, order, message, courier_ref):
        from shopman.shop.services import courier

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            block = dict(courier.get_block(order))
            known = {block.get("id_mch"), *[attempt.get("id_mch") for attempt in block.get("attempts", [])]}
            if courier_ref in known:
                return
            if courier.has_active_ride(order):
                raise DirectiveTerminalError("A central aceitou outra referência; confira as duas corridas antes de vincular.")
            block.update(provider="machine", id_mch=courier_ref, status="D",
                requested_at=timezone.now().isoformat(), last_event_at=timezone.now().isoformat(), last_source="dispatch")
            block.pop("error", None)
            courier._save_block(order, block, emit={"kind": "dispatched", "status": "D"})
            order.emit_event(event_type="courier_ride_opened", actor=str((message.payload or {}).get("actor") or "courier.dispatch"), payload={"id_mch": courier_ref})
            seconds = courier.poll_seconds()
            if seconds > 0:
                courier.schedule_sync(order, delay_seconds=min(seconds, courier.FIRST_SYNC_SECONDS))
        if order.status not in {Order.Status.READY, Order.Status.DISPATCHED}:
            self._record_terminal_failure(order, "A central aceitou a corrida enquanto o pedido mudou. Confira a corrida vinculada antes de agir.")

    @staticmethod
    @transaction.atomic
    def _record_terminal_failure(order, message: str) -> None:
        from django.utils import timezone

        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services import courier

        order = Order.objects.select_for_update().get(pk=order.pk)
        block = dict(courier.get_block(order))
        block["error"] = {"message": message[:500], "at": timezone.now().isoformat()}
        courier._save_block(order, block, emit={"kind": "dispatch_failed"})
        try:
            alert_adapter.create(
                "courier_dispatch_failed",
                "critical",
                f"Falha ao abrir corrida do pedido {order.ref}: {message[:200]}",
                order_ref=order.ref,
            )
        except Exception:
            logger.warning("courier.alert_failed order=%s", order.ref, exc_info=True)


__all__ = ["CourierDispatchHandler"]
