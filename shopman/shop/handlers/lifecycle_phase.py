"""Recover late local phase work through the canonical Directive claim and retry."""
from django.db import transaction
from shopman.orderman.dispatch import MAX_ATTEMPTS
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Order

from shopman.shop import lifecycle
from shopman.shop.directives import ORDER_LIFECYCLE_PHASE
from shopman.shop.services.observability import create_operator_alert


class LifecyclePhaseHandler:
    topic = ORDER_LIFECYCLE_PHASE

    def handle(self, *, message, ctx):
        payload = message.payload or {}
        phase = payload.get("phase")
        if phase not in lifecycle.QUEUED_PHASES:
            raise DirectiveTerminalError("Unsupported lifecycle phase")
        ref = payload.get("order_ref")
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(ref=ref).first()
                if order is None:
                    raise DirectiveTerminalError("Lifecycle order missing")
                if lifecycle.phase_complete(order, phase):
                    return
                allowed = {phase.removeprefix("on_")}
                if phase == "on_delivered":
                    allowed.add("completed")  # crash after the canonical automatic close
                if order.status not in allowed:
                    raise DirectiveTerminalError(f"Phase {phase} cannot resume in {order.status}")
                if phase == "on_returned" and not (order.data or {}).get("returns"):
                    raise DirectiveTerminalError("Legacy returned order has no authorized item record; reconcile before retry")
                # These phases write local facts and enqueue existing children.
                # Recorded returned orders delegate stock/refund to ReturnHandler.
                # No provider call is made while holding the order lock.
                lifecycle.dispatch(order, phase)
        except Exception as exc:
            if isinstance(exc, DirectiveTerminalError) or message.attempts >= MAX_ATTEMPTS:
                create_operator_alert(
                    type="lifecycle_phase_stuck", severity="critical", order_ref=ref,
                    message=f"Pedido {ref}: fase {phase} pendente. Confira os efeitos antes de retomar. {exc}",
                    dedupe_key=f"lifecycle_phase_stuck:{ref}:{phase}",
                )
            raise
