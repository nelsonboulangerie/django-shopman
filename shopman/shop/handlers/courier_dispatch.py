"""Courier dispatch handler — abre a corrida na Machine (Directive ``courier.dispatch``).

Enfileirado por ``courier.request_dispatch`` quando um pedido delivery fica
pronto (lifecycle ``on_ready`` com ``fulfillment.courier="auto"``), pelo
re-despacho manual do operador no gestor, ou por ``courier.request_group_dispatch``
(uma corrida, uma parada por pedido). Resultado remoto desconhecido exige
verificação; replay de aceite conhecido apenas recupera o vínculo local.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.services.observability import operational_event_on_commit

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
        # Uma corrida pode levar vários pedidos (``courier.request_group_dispatch``):
        # ``order_refs`` na ordem pedida; a corrida de um pedido só não tem a lista.
        refs = [str(ref) for ref in payload.get("order_refs") or [payload.get("order_ref")] if ref]
        orders = self._orders(refs)
        if not orders:
            return
        receipt = payload.get("dispatch_attempt", {})
        state = receipt.get("state")
        if state == "accepted":
            self._adopt(orders, message, receipt["courier_ref"])
            return
        if state in {"started", "unknown"} or (not state and message.attempts > 1):
            self._unknown(orders, message, "Tentativa anterior sem resultado confirmado.")
        if state in {"not_applied", "inert", "released"}:
            return
        if len(orders) != len(refs):
            self._set_attempt(message, "not_applied")
            return
        if any(get_fulfillment_type(order) != "delivery" or order.status not in courier.RIDE_ORDER_STATUSES
               for order in orders):
            self._set_attempt(message, "not_applied")
            return
        if not all(courier.house_dispatches(order) for order in orders):
            # Entrega do marketplace (ou de dono desconhecido): nunca abre corrida
            # paga, nem com a tarefa já na fila antes da marca chegar.
            self._set_attempt(message, "not_applied")
            return
        if any(courier.has_active_ride(order) for order in orders):
            return
        adapter = get_adapter("courier")
        if adapter is None:
            self._set_attempt(message, "inert")
            return
        if len(orders) == 1:
            courier.estimate_for_order(orders[0], store=True)
        try:
            body = courier.build_machine_payload(*orders)
        except ValueError as exc:
            self._set_attempt(message, "not_applied")
            self._record_terminal_failure(orders, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc

        # Claim the exact attempt locally, then release all locks before I/O.
        with transaction.atomic():
            orders = list(Order.objects.select_for_update().filter(pk__in=[o.pk for o in orders]).order_by("pk"))
            orders = sorted(orders, key=lambda order: refs.index(order.ref))
            message = Directive.objects.select_for_update().get(pk=message.pk)
            current = (message.payload or {}).get("dispatch_attempt", {})
            if current.get("state") == "accepted":
                self._adopt(orders, message, current["courier_ref"])
                return
            if current.get("state") in {"not_applied", "inert", "released"}:
                return
            other = next((task for task in (courier.unresolved_dispatch(order, exclude_pk=message.pk)
                                            for order in orders) if task is not None), None)
            if other is not None and not current:
                self._set_attempt(message, "not_applied", blocked_by=other.pk)
                blocked_elsewhere = True
            else:
                blocked_elsewhere = False
            blocked = bool(current) or other is not None
            if not blocked:
                if any(order.status not in courier.RIDE_ORDER_STATUSES or courier.has_active_ride(order)
                       for order in orders):
                    self._set_attempt(message, "not_applied")
                    return
                # Use the freshly locked orders, never the pre-estimate snapshot.
                body = courier.build_machine_payload(*orders)
                # A observação que vai à TaOn fica no recibo: a corrida aberta
                # guarda a cobrança que o entregador leva (``courier.charge_outdated``).
                notes = {order.ref: courier.ride_note(body, order.ref) for order in orders}
                stops = [str(stop.get("id_externo") or "") for stop in body.get("paradas") or []]
                self._set_attempt(message, "started", fingerprint=mutation_fingerprint(body), started_at=timezone.now().isoformat(),
                    note=notes[orders[0].ref], notes=notes, stops=stops)
        if blocked_elsewhere:
            raise DirectiveTerminalError("Outro despacho exige verificação; esta tarefa não chamou a central.")
        if blocked:
            self._unknown(orders, message, "Outro processo ou tentativa já iniciou este despacho.")

        try:
            result = adapter.dispatch(body)
        except CourierError as exc:
            if exc.outcome_unknown:
                self._unknown(orders, message, str(exc))
            self._set_attempt(message, "not_applied")
            self._record_terminal_failure(orders, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc
        except Exception as exc:
            logger.warning("courier.dispatch_unknown orders=%s directive=%s", ",".join(refs), message.pk, exc_info=True)
            self._unknown(orders, message, str(exc))
        if result.inert:
            self._set_attempt(message, "inert")
            return
        if not result.courier_ref:
            self._unknown(orders, message, "A central não devolveu a referência da solicitação.")
        # Persist acceptance before local adoption. If adoption fails, retry only
        # links this known ride; it never creates another remote solicitation.
        self._set_attempt(message, "accepted", courier_ref=result.courier_ref)
        self._adopt(orders, message, result.courier_ref)

    @staticmethod
    def _orders(refs: list[str]) -> list:
        """Os pedidos da tarefa, na ordem da tarefa (os que ainda existem)."""
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=refs)}
        return [by_ref[ref] for ref in refs if ref in by_ref]

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
            operational_event_on_commit("operator.effect.state", directive_id=locked.pk, effect=locked.topic,
                resource_ref=payload.get("order_ref"), worker_attempt=locked.attempts, state=state,
                external_ref=receipt.get("courier_ref"), started_at=receipt.get("started_at"), recorded_at=receipt["updated_at"],
                unknown_reason="acceptance_unconfirmed" if state == "unknown" else "")

    def _unknown(self, orders, message, detail):
        self._set_attempt(message, "unknown")
        explanation = "Despacho sem resultado confirmado. Confira na central antes de abrir outra corrida. " + detail
        self._record_terminal_failure(orders, explanation)
        raise DirectiveTerminalError(explanation)

    def _adopt(self, orders, message, courier_ref):
        """Grava a corrida aberta em cada pedido dela; só o primeiro agenda a leitura."""
        from shopman.shop.services import courier

        receipt = (message.payload or {}).get("dispatch_attempt") or {}
        notes = receipt.get("notes") if isinstance(receipt.get("notes"), dict) else {}
        # A ordem das paradas que foi à TaOn (recibo); sem ela, a da tarefa.
        stops = [str(ref) for ref in receipt.get("stops") or [] if ref] or [order.ref for order in orders]
        actor = str((message.payload or {}).get("actor") or "courier.dispatch")
        with transaction.atomic():
            locked = list(Order.objects.select_for_update().filter(pk__in=[o.pk for o in orders]).order_by("pk"))
            for order in locked:
                block = dict(courier.get_block(order))
                known = {block.get("id_mch"), *[attempt.get("id_mch") for attempt in block.get("attempts", [])]}
                if courier_ref in known:
                    continue
                if courier.has_active_ride(order):
                    raise DirectiveTerminalError("A central aceitou outra referência; confira as duas corridas antes de vincular.")
                opened_at = timezone.now().isoformat()
                block.update(provider="machine", id_mch=courier_ref, status="D", status_at={"D": opened_at},
                    requested_at=opened_at, last_event_at=opened_at, last_source="dispatch")
                if len(stops) > 1:
                    block["ride_orders"] = stops
                else:
                    block.pop("ride_orders", None)
                note = str(notes.get(order.ref) or (receipt.get("note") if len(locked) == 1 else "") or "")
                if note:
                    block["door_charge_note"] = note
                else:
                    block.pop("door_charge_note", None)
                block.pop("error", None)
                courier._save_block(order, block, emit={"kind": "dispatched", "status": "D"})
                order.emit_event(event_type="courier_ride_opened", actor=actor,
                                 payload={"id_mch": courier_ref, **({"ride_orders": stops} if len(stops) > 1 else {})})
            seconds = courier.poll_seconds()
            if seconds > 0 and locked:
                # A leitura é da corrida, não do pedido: uma batida só, que aplica a todos.
                courier.schedule_sync(locked[0], delay_seconds=min(seconds, courier.FIRST_SYNC_SECONDS))
        for order in locked:
            if order.status not in courier.RIDE_ORDER_STATUSES:
                self._record_terminal_failure([order], "A central aceitou a corrida enquanto o pedido mudou. Confira a corrida vinculada antes de agir.")

    @staticmethod
    def _record_terminal_failure(orders, message: str) -> None:
        for order in orders:
            CourierDispatchHandler._record_order_failure(order, message)

    @staticmethod
    @transaction.atomic
    def _record_order_failure(order, message: str) -> None:
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
                f"A corrida do pedido {order.ref} não abriu na central ({message[:200]}). "
                "Abra o pedido e chame o entregador de novo.",
                order_ref=order.ref,
            )
        except Exception:
            logger.warning("courier.alert_failed order=%s", order.ref, exc_info=True)


__all__ = ["CourierDispatchHandler"]
