"""Recover late local phase work through the canonical Directive claim and retry."""
import logging

from django.db import transaction
from shopman.orderman.dispatch import MAX_ATTEMPTS
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Order

from shopman.shop import lifecycle
from shopman.shop.directives import ORDER_LIFECYCLE_PHASE
from shopman.shop.services.observability import create_operator_alert

logger = logging.getLogger(__name__)

# Fase que chegou atrasada com o pedido já adiante dela (alerta do dono, 18/11:
# IFOOD-261118-3030 "Phase on_ready cannot resume in dispatched"). No iFood o
# "Saiu" vem logo depois do "Pronto", e a fase do pronto, que roda em segundo
# plano, encontra o pedido já despachado. O que ela faz (nota da sacola,
# atendimento, aviso, entregador automático) continua devido e é idempotente; o
# mesmo vale para o despacho que encontra o pedido entregue. O preparo NÃO entra:
# rodar tarde abriria trabalho na cozinha para um pedido que já saiu.
_LATE_RESUME = {
    "on_ready": ("dispatched", "delivered", "completed"),
    "on_dispatched": ("delivered", "completed"),
    "on_delivered": ("completed",),  # crash after the canonical automatic close
}


class LifecyclePhaseHandler:
    topic = ORDER_LIFECYCLE_PHASE

    def handle(self, *, message, ctx):
        payload = message.payload or {}
        phase = payload.get("phase")
        if phase not in lifecycle.QUEUED_PHASES:
            raise DirectiveTerminalError("Unsupported lifecycle phase")
        ref = payload.get("order_ref")
        order = None
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(ref=ref).first()
                if order is None:
                    raise DirectiveTerminalError("Lifecycle order missing")
                if lifecycle.phase_complete(order, phase):
                    return
                hold_token = payload.get("hold_token")
                if hold_token:
                    from shopman.shop.services import order_undo

                    # Fase segurada pela janela do pronto automático. Desfeito
                    # (token trocado ou apagado) ou de volta ao preparo: nada
                    # sai. Já entregue sem passar pelo release: roda agora.
                    if order_undo.hold_superseded(order, hold_token):
                        return
                    if order.status not in ("ready", "dispatched", "delivered", "completed"):
                        return
                    lifecycle.dispatch(order, phase)
                    return
                allowed = set(_LATE_RESUME.get(phase, ())) | {phase.removeprefix("on_")}
                if order.status not in allowed:
                    if lifecycle.phase_superseded(order, phase):
                        # Nada devido: o pedido fechou antes (ou é de teste). A tarefa
                        # termina sem erro e sem alerta (#3029).
                        logger.info(
                            "lifecycle.phase_superseded order=%s phase=%s status=%s", ref, phase, order.status,
                        )
                        return
                    raise DirectiveTerminalError(f"Phase {phase} cannot resume in {order.status}")
                if phase == "on_returned" and not (order.data or {}).get("returns"):
                    raise DirectiveTerminalError("Legacy returned order has no authorized item record; reconcile before retry")
                # These phases write local facts and enqueue existing children.
                # Recorded returned orders delegate stock/refund to ReturnHandler.
                # No provider call is made while holding the order lock.
                lifecycle.dispatch(order, phase)
        except Exception as exc:
            logger.warning("lifecycle.phase_pending order=%s phase=%s directive=%s", ref, phase, message.pk, exc_info=True)
            superseded = order is not None and lifecycle.phase_superseded(order, phase)
            if not superseded and (isinstance(exc, DirectiveTerminalError) or message.attempts >= MAX_ATTEMPTS):
                create_operator_alert(
                    type="lifecycle_phase_stuck", severity="critical", order_ref=ref,
                    message=lifecycle.phase_stuck_message(ref, phase, str(exc)),
                    dedupe_key=f"lifecycle_phase_stuck:{ref}:{phase}",
                )
            raise
