"""Vigia do cartão autorizado sem aceite (``payment.card_authorization_watch``).

Três paradas, uma Directive que se reagenda (``services/card_authorization``):

- ``stuck``: o pedido ficou parado além do aviso normal; avisa o Gestor com o
  prazo da autorização e se reagenda para 24 h antes dele;
- ``last_call``: faltam 24 h; avisa de novo, com prazo (interrompe a tela) e se
  reagenda para o vencimento;
- ``expire``: o prazo passou; pergunta ao Stripe e, vencida a autorização,
  cancela o pedido sem cobrança e grita (alerta crítico).

Pedido fora de ``new`` ou intent que já não está autorizado: nada a fazer
(aceito, a captura é do lifecycle; recusado, a autorização foi anulada).
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import CARD_AUTHORIZATION_WATCH


def _requeue(message: Directive, *, at: datetime, stage: str, expires_at: datetime) -> None:
    payload = dict(message.payload or {})
    payload["stage"] = stage
    payload["expires_at"] = expires_at.isoformat()
    message.payload = payload
    message.status = "queued"
    message.available_at = at
    message.save(update_fields=["payload", "status", "available_at", "updated_at"])


class CardAuthorizationWatchHandler:
    """Avisa antes de a autorização do cartão vencer; vencida, fecha o pedido."""

    topic = CARD_AUTHORIZATION_WATCH

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.services import card_authorization

        payload = message.payload or {}
        stage = str(payload.get("stage") or "stuck")
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return
        if order.status != Order.Status.NEW:
            return
        intent_ref = str(payload.get("intent_ref") or "")
        current_ref = str(((order.data or {}).get("payment") or {}).get("intent_ref") or "")
        if not intent_ref or current_ref != intent_ref:
            return

        # O prazo é relido do intent a cada parada: o ``capture_before`` do
        # Stripe pode ter chegado depois do agendamento.
        live_deadline = card_authorization.expires_at(order)
        if live_deadline is None:
            # O intent já não está autorizado (capturado, cancelado): nada a vigiar.
            return
        deadline = live_deadline

        now = timezone.now()
        last_call_at = deadline - card_authorization.LAST_CALL_BEFORE

        if stage == "stuck":
            card_authorization.alert_expiring(order, deadline, stage="stuck")
            if now < last_call_at:
                _requeue(message, at=last_call_at, stage="last_call", expires_at=deadline)
                return
            stage = "last_call"

        if stage == "last_call":
            if now < last_call_at:
                _requeue(message, at=last_call_at, stage="last_call", expires_at=deadline)
                return
            if now < deadline:
                card_authorization.alert_expiring(order, deadline, stage="last_call")
                _requeue(message, at=deadline, stage="expire", expires_at=deadline)
                return
            stage = "expire"

        if now < deadline:
            _requeue(message, at=deadline, stage="expire", expires_at=deadline)
            return

        outcome = card_authorization.expire(order, intent_ref=intent_ref)
        if outcome == "still_authorized":
            _requeue(
                message,
                at=now + card_authorization.GATEWAY_GRACE,
                stage="expire",
                expires_at=deadline,
            )
            return
        if outcome == "indeterminate":
            raise DirectiveTransientError(
                "gateway indisponível para conferir a autorização do cartão"
            )


__all__ = ["CardAuthorizationWatchHandler"]
