"""Pedidos em aberto marcados para um dia que a loja acabou de fechar.

Fechar uma data no calendário (feriado, férias, imprevisto) não mexe em pedido
nenhum: a encomenda paga continua apontando para o dia fechado. Este módulo só
ENCONTRA esses pedidos e AVISA o Gestor, um aviso por pedido, para que alguém
remarque ou fale com o cliente. Nunca cancela nem remarca sozinho: a conversa com
o cliente é decisão de gente.
"""

from __future__ import annotations

from datetime import date

from shopman.shop.services.observability import create_operator_alert
from shopman.shop.services.order_helpers import get_commitment_date

ALERT_TYPE = "order_on_closed_day"

#: Pedido que ainda vai sair da loja. Despachado ou entregue já saiu; o dia
#: fechado não o alcança mais.
OPEN_STATUSES = ("new", "accepted", "preparing", "ready")


def open_orders_committed_between(starts_on: date, ends_on: date | None = None) -> list:
    """Pedidos em aberto cuja data combinada cai em ``starts_on..ends_on``."""
    from shopman.orderman.models import Order

    last = ends_on or starts_on
    candidates = Order.objects.filter(
        status__in=OPEN_STATUSES,
        data__delivery_date__gte=starts_on.isoformat(),
        data__delivery_date__lte=last.isoformat(),
    ).order_by("ref")
    # O SQL compara texto; quem decide é a data lida pelo helper canônico.
    return [
        order
        for order in candidates
        if (committed := get_commitment_date(order)) is not None and starts_on <= committed <= last
    ]


def alert_orders_on_closed_day(orders, *, reason: str = "") -> int:
    """Um aviso ao Gestor por pedido; devolve quantos avisos saíram."""
    created = 0
    for order in orders:
        committed = get_commitment_date(order)
        if committed is None:
            continue
        day = committed.strftime("%d/%m/%Y")
        motive = f" ({reason})" if reason else ""
        message = (
            f"Pedido {order.ref} está marcado para {day}, e a loja fechou esse dia "
            f"no calendário{motive}. Remarque com o cliente ou combine outra solução."
        )
        alert = create_operator_alert(
            type=ALERT_TYPE,
            severity="warning",
            message=message,
            order_ref=order.ref,
            # Contido na mensagem: o debounce casa por pedido + data sem pendurar
            # um "Dedupe:" no texto que o operador lê.
            dedupe_key=f"marcado para {day}",
            debounce_minutes=24 * 60,
        )
        if alert is not None:
            created += 1
    return created
