"""Handler do piloto automático de staging — dá o próximo passo do operador.

Fica inerte fora de staging/dev: se a directive sobreviver a um deployment que
desligou o piloto (ou for plantada à mão), o handler recusa como falha terminal
em vez de mexer no pedido.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, InvalidTransition
from shopman.orderman.models import Directive

from shopman.shop.directives import STAGING_AUTOPILOT

logger = logging.getLogger(__name__)


class StagingAutopilotHandler:
    """Avança um pedido de staging um passo. Topic: staging.autopilot"""

    topic = STAGING_AUTOPILOT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from datetime import timedelta

        from shopman.orderman.models import Order

        from shopman.shop.services import staging_autopilot

        if not staging_autopilot.is_enabled():
            raise DirectiveTerminalError(
                "piloto automático de staging não está habilitado neste ambiente"
            )

        payload = message.payload or {}
        order_ref = payload.get("order_ref")
        recorded_status = payload.get("status", "")
        deferrals = int(payload.get("deferrals") or 0)
        if not order_ref:
            raise DirectiveTerminalError("payload sem order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            return

        try:
            new_status = staging_autopilot.step(order, recorded_status=recorded_status)
        except (ValueError, InvalidTransition) as exc:
            # Guarda do gestor recusou (PIX ainda não pago, encomenda fora da
            # data). Não é erro: é "ainda não". Reagenda o MESMO passo, com
            # teto — a transição, quando vier, agenda o passo dela sozinha.
            if deferrals + 1 >= staging_autopilot.MAX_DEFERRALS:
                logger.warning(
                    "staging_autopilot: desistindo do pedido %s em %s — %s",
                    order_ref, recorded_status, exc,
                )
                return
            message.status = "queued"
            message.payload = {**payload, "deferrals": deferrals + 1}
            message.available_at = timezone.now() + timedelta(
                seconds=staging_autopilot.delay_seconds()
            )
            message.save(update_fields=["status", "payload", "available_at", "updated_at"])
            return

        if new_status:
            logger.info(
                "staging_autopilot: pedido %s %s → %s", order_ref, recorded_status, new_status
            )


__all__ = ["StagingAutopilotHandler"]
