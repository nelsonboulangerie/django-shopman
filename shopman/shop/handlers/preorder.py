"""
Preorder handler — dispara o trabalho físico da encomenda NA data dela.

O lifecycle adia KDS e baixa de estoque de pedidos com ``delivery_date``
futura (``_on_accepted``/``_on_paid`` agendam ``preorder.activate`` com
``available_at`` na meia-noite da data). Este handler é o despertador:
na manhã da data, cria os tickets e baixa o que já materializou —
``lifecycle.activate_preorder`` faz exatamente o que a confirmação teria
feito se a data fosse hoje.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import PREORDER_ACTIVATE

logger = logging.getLogger(__name__)


class PreorderActivateHandler:
    """Ativa encomenda na data. Topic: preorder.activate"""

    topic = PREORDER_ACTIVATE

    @transaction.atomic
    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.lifecycle import _physical_work_deferred, activate_preorder, preorder_activation_at
        from shopman.shop.services import ifood_cancellation, ifood_schedule

        order_ref = message.payload.get("order_ref")
        if not order_ref:
            return

        try:
            order = Order.objects.select_for_update().get(ref=order_ref)
        except Order.DoesNotExist:
            logger.info("preorder.activate: order %s não existe mais", order_ref)
            return

        if ifood_schedule.is_scheduled(order) and ifood_cancellation.is_pending(order):
            # Waiting for the remote decision is not a failed attempt. Both
            # dispatchers preserve a handler's explicit queued state.
            message.status = "queued"
            message.available_at = timezone.now() + timedelta(minutes=1)
            message.attempts = max(0, message.attempts - 1)
            message.save(update_fields=["status", "available_at", "attempts", "updated_at"])
            return

        if _physical_work_deferred(order):
            # Tocou antes da data (fuso, relógio, ou uma data trocada por fora do
            # ``services.reschedule``). Terminar aqui deixaria a encomenda sem
            # despertador: ela nunca iria para a cozinha. A própria directive
            # volta para a fila na madrugada certa — sem criar outra.
            available_at, target = preorder_activation_at(order)
            if available_at is not None and available_at > timezone.now():
                payload = dict(message.payload or {})
                payload["delivery_date"] = target.isoformat()
                message.payload = payload
                message.status = "queued"
                message.available_at = available_at
                message.attempts = max(0, message.attempts - 1)
                message.save(update_fields=["payload", "status", "available_at", "attempts", "updated_at"])
                logger.info(
                    "preorder.activate: cedo demais order=%s — re-enfileirado para %s",
                    order_ref, available_at.isoformat(),
                )
                return

        activate_preorder(order)
