"""Helper de teste: grava agora a saída tocada no Gestor/Saída (UX-G2).

Entregar/Despachar pelo Gestor ou pela Saída da Cozinha registra a saída e só
grava a transição quando a janela de desfazer vence (``order_undo``). O teste
que quer o pedido já do outro lado chama ``settle(order)``: é o que a directive
``order.handoff_commit`` faria quando o prazo acaba.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from shopman.shop.services import order_undo


def settle(order) -> str:
    """Vence a janela e grava a saída pendente. Devolve o status final ('' se nada havia)."""
    order.refresh_from_db()
    pending = order_undo.pending_handoff(order)
    if not pending:
        return ""
    status = order_undo.commit_handoff(order.ref, pending["token"], now=timezone.now() + timedelta(minutes=5))
    order.refresh_from_db()
    return status
