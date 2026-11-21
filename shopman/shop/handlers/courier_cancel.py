"""Durable cancellation of one observed ride, using the existing Directive worker.

A solicitação é da CORRIDA (``courier_ref``), não de um pedido: a corrida com
várias paradas se cancela inteira, e o ``C`` vale para cada pedido que a carrega
(``order_refs``). O motivo enviado à central sai da letra da corrida lida na
hora (``courier_machine.cancel_reason_for``); recusa por motivo da fase errada
(erro 102) relê a letra e reenvia uma vez. Recusa definitiva nunca fica muda:
estado ``refused``, aviso crítico e SSE ``cancel_failed``.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters.courier_machine import (
    BEFORE_ACCEPT_STATUSES,
    CANCEL_INTENT_OPERATOR,
    CANCEL_REASON_REFUSED_CODE,
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    CourierError,
    cancel_reason_for,
)
from shopman.shop.directives import COURIER_CANCEL
from shopman.shop.services import courier, delivery_services
from shopman.shop.services.observability import operational_event_on_commit

logger = logging.getLogger(__name__)

#: As letras que a leitura da central pode devolver e este handler entende.
_KNOWN_LETTERS = CANCELLABLE_STATUSES | TERMINAL_STATUSES | {"E", "U"}


class CourierCancelHandler:
    topic = COURIER_CANCEL

    def handle(self, *, message: Directive, ctx: dict) -> None:
        message.refresh_from_db()
        payload = message.payload or {}
        ride_id = payload.get("courier_ref")
        order = self._lead(payload)
        if order is None:
            return
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            message = Directive.objects.select_for_update().get(pk=message.pk)
            state = (message.payload or {}).get("cancel_attempt", {}).get("state")
            if state in {"not_applied", "refused"}:
                return
            if state == "accepted":
                self._adopt(message)
                return
            if state not in {"started", "unknown"}:
                block = courier.get_block(order)
                if block.get("ride_ref") != ride_id or not courier.ride_cancellable(block):
                    self._record(message, "not_applied")
                    return
                adapter = delivery_services.courier_backend(block)
                if adapter is None:
                    self._record(message, "not_applied")
                    raise DirectiveTerminalError("Adapter indisponível; nenhum cancelamento foi enviado.")
                known_letter = str(block.get("status") or "")
                self._record(message, "started", started_at=timezone.now().isoformat())
        if state in {"started", "unknown"}:
            self._unknown(order, message)
        # A letra de AGORA, lida da central (só GET): o motivo aceito depende
        # dela, e a que está no pedido pode ter ficado para trás.
        letter = self._fresh_letter(adapter, ride_id) or known_letter
        if letter == "C":
            # A central já cancelou: não há o que pedir, só reconhecer.
            self._record(message, "accepted", letter=letter)
            self._adopt(message)
            return
        if letter not in CANCELLABLE_STATUSES:
            # Coletada, finalizada ou não atendida lá, e o pedido ainda não
            # soube: nada é enviado, e a leitura traz o fato já.
            self._record(message, "not_applied", letter=letter)
            courier.schedule_sync(order, delay_seconds=0)
            return
        intent = payload.get("reason_id") if payload.get("reason_id") is not None else (
            payload.get("intent") or CANCEL_INTENT_OPERATOR)
        try:
            accepted, sent = self._send(adapter, ride_id, letter, intent)
        except CourierError as exc:
            if exc.outcome_unknown:
                self._unknown(order, message)
            self._refused(order, message, exc)
        except Exception:
            logger.warning("courier.cancel_unknown order=%s directive=%s", order.ref, message.pk, exc_info=True)
            self._unknown(order, message)
        if accepted is not True:
            self._unknown(order, message)
        self._record(message, "accepted", letter=letter, reasons=sent)
        self._adopt(message)

    @staticmethod
    def _lead(payload: dict):
        """O pedido pelo qual a corrida responde: o primeiro que ainda a carrega."""
        refs = [str(ref) for ref in payload.get("order_refs") or [payload.get("order_ref")] if ref]
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=refs)}
        orders = [by_ref[ref] for ref in refs if ref in by_ref]
        holding = [order for order in orders if courier.get_block(order).get("ride_ref") == payload.get("courier_ref")]
        return (holding or orders or [None])[0]

    @staticmethod
    def _fresh_letter(adapter, ride_id: str) -> str:
        """A letra da corrida lida agora; vazio quando a leitura falha (vale a do pedido)."""
        try:
            read_ride = getattr(adapter, "read_ride", None)
            letter = (read_ride(ride_id) or {}).get("status") if read_ride else adapter.get_status(ride_id)
        except Exception:
            logger.info("courier.cancel_letter_unread ride_ref=%s", ride_id, exc_info=True)
            return ""
        letter = letter.strip().upper() if isinstance(letter, str) else ""
        return letter if letter in _KNOWN_LETTERS else ""

    def _send(self, adapter, ride_id: str, letter: str, intent) -> tuple[bool, list[int]]:
        """POST /cancelar com o motivo da fase; no erro 102, relê a letra e reenvia UMA vez."""
        reason = cancel_reason_for(letter, intent)
        try:
            return adapter.cancel(ride_id, reason_id=reason), [reason]
        except CourierError as exc:
            if CANCEL_REASON_REFUSED_CODE not in getattr(exc, "codes", ()):
                raise
            logger.warning("courier.cancel_reason_refused ride_ref=%s letter=%s reason=%s", ride_id, letter, reason)
        # A corrida mudou de fase entre a leitura e o envio (aceita, ou voltou
        # à procura). Vale a letra relida; se ela não muda o motivo, o da outra fase.
        again = self._fresh_letter(adapter, ride_id)
        if again == "C":
            return True, [reason]
        retry = cancel_reason_for(again, intent) if again in CANCELLABLE_STATUSES else reason
        if retry == reason:
            retry = cancel_reason_for("A" if letter in BEFORE_ACCEPT_STATUSES else "D", intent)
        return adapter.cancel(ride_id, reason_id=retry), [reason, retry]

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
        attempt = payload["cancel_attempt"]
        operational_event_on_commit("operator.effect.state", directive_id=message.pk, effect=message.topic,
            resource_ref=payload.get("order_ref"), worker_attempt=message.attempts, state=state,
            external_ref=payload.get("courier_ref"), started_at=attempt.get("started_at"), recorded_at=attempt["updated_at"],
            unknown_reason="acceptance_unconfirmed" if state == "unknown" else "")

    @staticmethod
    def _members(message) -> list:
        """Todo pedido que carrega esta corrida AGORA (o ``C`` arquiva e apaga quem estava nela)."""
        payload = message.payload or {}
        refs = [str(ref) for ref in payload.get("order_refs") or [payload.get("order_ref")] if ref]
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=refs)}
        return [by_ref[ref] for ref in refs
                if ref in by_ref and courier.get_block(by_ref[ref]).get("ride_ref") == payload.get("courier_ref")]

    @classmethod
    def _adopt(cls, message):
        # apply_status compares this observed ride under its own fresh Order lock.
        # Os companheiros são lidos ANTES do primeiro C: a corrida cancelada
        # volta inteira para Aguardando, com o troco e a maquininha de cada um.
        source = f"operator:{(message.payload or {}).get('actor', '')}"
        for order in cls._members(message):
            courier.apply_status(order, "C", source=source)

    def _refused(self, order, message, exc):
        """A central recusou de vez: a corrida segue aberta, e o operador precisa saber."""
        from shopman.shop.adapters import alert as alert_adapter

        self._record(message, "refused", refusal=str(exc)[:300])
        explanation = courier.cancel_refused_message(order)
        for member in self._members(message) or [order]:
            courier._emit_sse(member, {"kind": "cancel_failed"})
        try:
            if not alert_adapter.recent_exists("integration_failed", message.created_at, order_ref=order.ref,
                                               message_contains="não cancelou"):
                alert_adapter.create("integration_failed", "critical", explanation, order_ref=order.ref)
        except Exception:
            logger.warning("courier.cancel_alert_failed order=%s directive=%s", order.ref, message.pk, exc_info=True)
        raise DirectiveTerminalError(f"A central recusou o cancelamento: {exc}") from exc

    def _unknown(self, order, message):
        from shopman.shop.adapters import alert as alert_adapter

        self._record(message, "unknown")
        explanation = courier.CANCEL_UNKNOWN_MESSAGE
        for member in self._members(message) or [order]:
            courier._emit_sse(member, {"kind": "cancel_unknown"})
        try:
            if not alert_adapter.recent_exists("integration_failed", message.created_at, order_ref=order.ref, message_contains="Cancelamento sem resultado confirmado"):
                alert_adapter.create("integration_failed", "critical", explanation, order_ref=order.ref)
        except Exception:
            logger.warning("courier.cancel_alert_failed order=%s directive=%s", order.ref, message.pk, exc_info=True)
        raise DirectiveTerminalError(explanation)
