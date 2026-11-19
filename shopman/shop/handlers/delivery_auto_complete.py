"""Delivery auto-complete handler — fecha um pedido em entrega após ETA + folga.

Rede de segurança do trecho sem rastreio: se nem o cliente ("Recebi") nem o
operador ("Marcar entregue") fecharem o loop, o pedido não fica preso em "saiu
para entrega". Revalida o estado, então é um no-op se o pedido já foi fechado.

Com corrida da central viva (coletada, não finalizada) e leitura em dia, o
relógio não sabe mais que a central: a tarefa se adia para a entrega prevista
por ela mais a folga (``courier.auto_complete_hold_until``), em vez de marcar
entregue com o entregador ainda na rua (revisão das Entregas, ENT-14). Com o
dado parado, conclui pelo prazo e avisa o operador.
"""

from __future__ import annotations

from shopman.orderman.models import Directive

from shopman.shop.directives import DELIVERY_AUTO_COMPLETE


class DeliveryAutoCompleteHandler:
    """Marca como entregue um pedido ainda em entrega quando o prazo vence."""

    topic = DELIVERY_AUTO_COMPLETE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.models import Shop
        from shopman.shop.services import courier, operator_orders
        from shopman.shop.services.order_helpers import delivery_auto_complete_grace_minutes

        payload = message.payload or {}
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        if order.status == Order.Status.DISPATCHED:
            hold = courier.auto_complete_hold_until(
                order, grace_minutes=delivery_auto_complete_grace_minutes(Shop.load()))
            if hold is not None:
                # O entregador da central ainda está na rua e a leitura está em
                # dia: a mesma tarefa volta à fila para depois da entrega prevista.
                message.status = Directive.Status.QUEUED
                message.available_at = hold
                message.save(update_fields=["status", "available_at", "updated_at"])
                return

        blind = courier.has_active_ride(order)
        # confirm_received é idempotente: só age se ainda está em entrega
        # (dispatched + delivery). Mesma transição do operador → notifica 1×.
        done = operator_orders.confirm_received(order, actor="delivery.auto_complete")
        if done and blind:
            courier.alert_auto_completed_blind(order)


__all__ = ["DeliveryAutoCompleteHandler"]
