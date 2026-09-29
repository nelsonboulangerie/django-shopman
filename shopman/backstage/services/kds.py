"""Backstage KDS mutation facade."""

from __future__ import annotations

from shopman.backstage.services.exceptions import (
    KDSError,
    KDSInstanceNotFound,
    KDSOrderNotFound,
    KDSTicketNotFound,
)
from shopman.shop.services import kds as kds_core

OPEN_STATUSES = ("pending", "in_progress")


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
        # mesma semântica do replay da Saída.
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
    except (kds_core.FutureWorkBlocked, kds_core.TicketRecallBlocked) as exc:
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


# ── Estação sem tela: quem dá a baixa é outra porta ─────────────────────
#
# Decisão do dono (26/09/2026): a estação que não tem tela recebe o pedido em
# papel (``KDSInstance.print_terminal``) e imprimir não conclui nada. A baixa
# vem da Saída (o "Pronto" do chip da estação no card do pedido), do PDV (o
# card do ticket) ou do leitor de código na bancada.
#
# Os endpoints de ticket do KDS (``done``/``start``) aceitam qualquer ticket de
# quem opera o KDS. Estes aqui têm critério: só concluem ticket de estação SEM
# tela — a de tela conclui o próprio trabalho, e o balcão não fecha o card de
# um cozinheiro que está olhando para ele. O leitor de código é a exceção
# natural: o QR só existe no papel, e ler o papel é a prova de que ele existe.


def _require_printed_station(station) -> None:
    if not station.print_terminal_id:
        raise KDSError(f"{station.name} tem tela: o pronto é dado lá.")


def _acknowledge_printed_cancellations(ticket, *, actor: str) -> None:
    """O CANCELADO já saiu em papel na bancada: é a ciência da estação sem tela.

    Na estação de tela, o ticket com item cancelado só se finaliza depois do
    "Recebi o cancelamento" do cozinheiro (``_complete_ticket_locked``). A
    estação sem tela não tem esse botão — o aviso dela é o papel CANCELADO que
    saiu na impressora. Sem isto, qualquer pedido com item retirado travaria o
    "Pronto" da Saída para sempre.
    """
    from shopman.backstage.models import KDSTicket

    for cancelled in KDSTicket.objects.filter(
        session_key=ticket.session_key,
        kds_instance_id=ticket.kds_instance_id,
        status="cancelled",
        acknowledged_at__isnull=True,
    ):
        kds_core.acknowledge_ticket(cancelled, actor=actor)


def _complete_printed(ticket, *, actor: str, via: str) -> bool:
    """Conclui um ticket de estação sem tela. False = já estava concluído."""
    if ticket.status == "done":
        return False
    if ticket.status == "cancelled":
        raise KDSError(f"Este pedido foi cancelado em {ticket.kds_instance.name}: não prepare.")
    _ensure_ticket_due(ticket)
    _acknowledge_printed_cancellations(ticket, actor=actor)
    try:
        completed = kds_core.complete_ticket(ticket, actor=actor, via=via)
    except (kds_core.TicketCompletionBlocked, kds_core.FutureWorkBlocked) as exc:
        raise KDSError(str(exc)) from exc
    if not completed:
        ticket.refresh_from_db()
        if ticket.status == "done":
            return False  # outra porta concluiu no meio: replay
        raise KDSError("Ticket não está aberto.")
    return True


def mark_printed_ticket_done(*, ticket_pk: int, actor: str, via: str):
    """O "Pronto" do PDV no card do ticket. Replay (já concluído) é sucesso.

    Devolve ``(ticket, completed_now)``.
    """
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.select_related("kds_instance").filter(pk=ticket_pk).first()
    if ticket is None:
        raise KDSTicketNotFound("Ticket não encontrado.")
    _require_printed_station(ticket.kds_instance)
    completed = _complete_printed(ticket, actor=actor, via=via)
    ticket.refresh_from_db()
    return ticket, completed


def mark_printed_station_done_for_order(*, order_id: int, station_ref: str, actor: str) -> int:
    """O "Pronto" da Saída: a estação sem tela terminou a parte dela neste pedido.

    Conclui os tickets abertos DAQUELA estação DAQUELE pedido — e só eles: a
    ação diz qual pedido e qual estação, e o servidor confere as duas coisas
    antes de tocar em qualquer ticket. Devolve quantos concluiu (0 = replay:
    outra porta já tinha concluído).
    """
    from shopman.orderman.models import Order

    from shopman.backstage.models import KDSInstance, KDSTicket

    # ``values_list``, não ``only``: o Order guarda a linha de base no
    # ``__init__`` e um campo adiado vira recarga recursiva.
    session_key = Order.objects.filter(pk=order_id).values_list("session_key", flat=True).first()
    if not session_key:
        raise KDSOrderNotFound("Pedido não encontrado.")
    station = KDSInstance.objects.filter(ref=station_ref, is_active=True).first()
    if station is None:
        raise KDSInstanceNotFound("Estação não encontrada.")
    _require_printed_station(station)
    tickets = list(
        KDSTicket.objects.select_related("kds_instance")
        .filter(session_key=session_key, kds_instance=station, status__in=OPEN_STATUSES)
        .order_by("created_at", "pk")
    )
    done = 0
    for ticket in tickets:
        if _complete_printed(ticket, actor=actor, via=KDSTicket.COMPLETED_VIA_EXIT):
            done += 1
    return done


def mark_scanned_ticket_done(*, code: str, actor: str):
    """O leitor de código da bancada leu o QR da Via Cozinha: o ticket fica pronto.

    O código assinado é a credencial do gesto (``ticket_pk_from_code``): quem o
    tem está com o papel na mão. Por isso não se exige aqui que a estação
    continue sem tela — se o gestor trocou a impressora por um tablet depois
    do papel sair, o papel ainda vale. Devolve ``(ticket, completed_now)``.
    """
    from shopman.backstage.models import KDSTicket
    from shopman.backstage.services.kitchen_ticket_print import ticket_pk_from_code

    ticket_pk = ticket_pk_from_code(code)
    ticket = (
        KDSTicket.objects.select_related("kds_instance").filter(pk=ticket_pk).first()
        if ticket_pk is not None
        else None
    )
    if ticket is None:
        raise KDSTicketNotFound("Código não reconhecido: não é de uma Via Cozinha desta loja.")
    completed = _complete_printed(ticket, actor=actor, via=KDSTicket.COMPLETED_VIA_SCANNER)
    ticket.refresh_from_db()
    return ticket, completed
