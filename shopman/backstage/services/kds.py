"""Backstage KDS mutation facade."""

from __future__ import annotations

from shopman.backstage.services.exceptions import KDSError, KDSOrderNotFound, KDSTicketNotFound
from shopman.shop.services import kds as kds_core


def _get_ticket(ticket_pk: int):
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSTicketNotFound("Ticket não encontrado.")
    return ticket


def _ensure_ticket_due(ticket) -> None:
    try:
        kds_core.ensure_ticket_due(ticket)
    except kds_core.FutureWorkBlocked as exc:
        raise KDSError(str(exc)) from exc


def start_ticket(*, ticket_pk: int, actor: str):
    """Põe o ticket em preparo. Replay (dois tablets no mesmo card) é sucesso."""
    ticket = _get_ticket(ticket_pk)
    _ensure_ticket_due(ticket)
    try:
        started = kds_core.start_ticket(ticket, actor=actor)
    except kds_core.FutureWorkBlocked as exc:
        raise KDSError(str(exc)) from exc
    if not started:
        raise KDSError("Ticket não está aberto.")
    ticket.refresh_from_db()
    return ticket


def mark_ticket_done(*, ticket_pk: int, actor: str):
    ticket = _get_ticket(ticket_pk)
    _ensure_ticket_due(ticket)
    if ticket.status == "done":
        # Replay (duas estações bumpando o mesmo ticket) = sucesso no-op,
        # mesma semântica do replay da expedição.
        return ticket
    try:
        completed = kds_core.complete_ticket(ticket, actor=actor)
    except (kds_core.TicketCompletionBlocked, kds_core.FutureWorkBlocked) as exc:
        # Gate do lifecycle (pagamento não capturado, pedido não confirmado):
        # a razão real chega ao operador — não é "ticket não está aberto".
        raise KDSError(str(exc)) from exc
    if not completed:
        raise KDSError("Ticket não está aberto.")
    ticket.refresh_from_db()
    return ticket


def recall_ticket(*, ticket_pk: int, actor: str):
    ticket = _get_ticket(ticket_pk)
    _ensure_ticket_due(ticket)
    try:
        reopened = kds_core.reopen_ticket(ticket, actor=actor)
    except kds_core.FutureWorkBlocked as exc:
        raise KDSError(str(exc)) from exc
    if not reopened:
        raise KDSError("Ticket não está concluído.")
    ticket.refresh_from_db()
    return ticket


def acknowledge_ticket(*, ticket_pk: int, actor: str):
    ticket = _get_ticket(ticket_pk)
    _ensure_ticket_due(ticket)
    try:
        acknowledged = kds_core.acknowledge_ticket(ticket, actor=actor)
    except kds_core.FutureWorkBlocked as exc:
        raise KDSError(str(exc)) from exc
    if not acknowledged:
        raise KDSError("Ticket não está cancelado.")
    ticket.refresh_from_db()
    return ticket


def expedition_action(*, order_id: int, action: str, actor: str):
    """Apply an expedition action; idempotent replay resolved under the core lock.

    O core (``expedition_action_by_order_id``) trava a linha do pedido, decide o
    replay (status já no alvo = no-op) e valida a transição na linha travada.
    Aqui só se traduz exceção de domínio para o vocabulário do backstage —
    preservando a mensagem específica do core (ex.: "Pedido de retirada não
    pode ser despachado"), nunca um genérico.
    """
    try:
        return kds_core.expedition_action_by_order_id(order_id, action=action, actor=actor)
    except kds_core.ExpeditionOrderNotFound as exc:
        raise KDSOrderNotFound("Pedido não encontrado.") from exc
    except ValueError as exc:
        raise KDSError(str(exc) or "Ação inválida.") from exc
