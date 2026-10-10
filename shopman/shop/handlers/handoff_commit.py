"""Grava a saída (Entregar/Despachar) quando a janela de desfazer vence.

O toque do Gestor ou da Saída da Cozinha registra ``order.data["pending_handoff"]``
e agenda esta directive para o fim da janela. Aqui a transição acontece de
verdade, pela mesma ``operator_orders.advance_order`` do toque. Token que não
bate (o operador desfez) é no-op. Ver ``services/order_undo.py``.
"""

from __future__ import annotations

from shopman.orderman.models import Directive

from shopman.shop.directives import ORDER_HANDOFF_COMMIT


class HandoffCommitHandler:
    topic = ORDER_HANDOFF_COMMIT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.services import order_undo

        payload = message.payload or {}
        order_undo.commit_handoff(str(payload.get("order_ref") or ""), str(payload.get("token") or ""))


__all__ = ["HandoffCommitHandler"]
