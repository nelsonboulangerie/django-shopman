"""KDS adapter — wraps KDSInstance/KDSTicket CRUD with lazy imports.

Keeps shop/ free of direct shopman.backstage imports.
"""
from __future__ import annotations

from typing import Any


def get_active_prep_instances() -> list[Any]:
    """Active KDS instances excluding expedition (prep + picking stations)."""
    from shopman.backstage.models import KDSInstance

    return list(
        KDSInstance.objects.filter(is_active=True)
        .exclude(type="expedition")
        .prefetch_related("collections")
    )


def ticket_exists_for_order(order) -> bool:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(session_key=order.session_key).exists()


def fired_line_ids_for_session(session_key: str) -> set[str]:
    """Line ids already on a live (non-cancelled) ticket for this session_key.

    The durable fire-ledger: survives commit (tickets are keyed by session_key,
    not the Order). A cancelled line is absent — so it may re-fire (reprint).
    """
    from shopman.backstage.models import KDSTicket

    fired: set[str] = set()
    rows = (
        KDSTicket.objects.filter(session_key=session_key)
        .exclude(status="cancelled")
        .values_list("items", flat=True)
    )
    for items in rows:
        for item in items or []:
            line_id = item.get("line_id")
            if line_id:
                fired.add(line_id)
    return fired | inherited_fired_line_ids(session_key)


#: Linhas que já estão na cozinha num ticket de OUTRA sessão e passaram para esta.
#: Hoje só a venda feita sem conexão grava (``pos_offline_sale``): a comanda mudada
#: em outro dispositivo fecha só o que foi cobrado, e o resto segue numa comanda
#: nova; a linha já enviada não pode voltar à cozinha por ter trocado de sessão.
KDS_INHERITED_KEY = "kds_inherited_lines"


def inherited_fired_line_ids(session_key: str) -> set[str]:
    from shopman.orderman.models import Session

    data = Session.objects.filter(session_key=session_key).values_list("data", flat=True).first() or {}
    return {str(line_id) for line_id in (data.get(KDS_INHERITED_KEY) or []) if line_id}


def create_ticket(session_key: str, kds_instance, items: list) -> Any:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.create(
        session_key=session_key, kds_instance=kds_instance, items=items,
    )


def unfire_session_lines(
    session_key: str,
    line_ids: list[str],
    fractions: dict[str, Any] | None = None,
) -> dict:
    """Un-fire specific lines for a session: remove them from their live tickets.

    Precondition: the caller holds the source Session/Order row lock.  KDS
    writers use one global order, ``source -> ticket``, to avoid deadlocks with
    POS tab commands.

    A ticket loses only the targeted line items; when that empties the ticket it
    is cancelled (status="cancelled"), otherwise the surviving courses keep their
    prep progress. The model save re-emits the KDS SSE event either way. Removing
    a line drops it from the fire-ledger, so it may be fired again (reprint =
    un-fire + fire). Returns ``{"cancelled": n, "trimmed": n}``.

    ``fractions`` (opcional, ``{line_id: fração}`` com 0 < fração < 1): a conta
    DIMINUIU uma linha que já está na cozinha (decisão do dono, 10/10/2026: diminuir
    cancela só a diferença). A linha fica no ticket vivo com o que sobra, e o
    comprovante cancelado leva só a diferença (a mesma fração de cada item da linha,
    o que cobre o combo). A linha continua no ledger: segue enviada.
    """
    from decimal import Decimal

    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import KDSTicket
    from shopman.shop.services.order_helpers import json_quantity

    targets = {str(lid) for lid in (line_ids or []) if str(lid)}
    partial: dict[str, Decimal] = {}
    for line_id, fraction in (fractions or {}).items():
        value = Decimal(str(fraction))
        if str(line_id) in targets and Decimal(0) < value < Decimal(1):
            partial[str(line_id)] = value
    cancelled = trimmed = 0
    if not targets:
        return {"cancelled": 0, "trimmed": 0}

    with transaction.atomic():
        tickets = (
            KDSTicket.objects.select_for_update()
            .filter(session_key=session_key)
            .exclude(status="cancelled")
        )
        for ticket in tickets:
            items = ticket.items or []
            removed = []
            kept = []
            for it in items:
                line_id = it.get("line_id")
                if line_id not in targets:
                    kept.append(it)
                    continue
                fraction = partial.get(line_id)
                if fraction is None:
                    removed.append(it)
                    continue
                qty = Decimal(str(it.get("qty") or 0))
                gone = qty * fraction
                # `partial_cancel`: o comprovante é de uma DIFERENÇA, pedida pelo balcão;
                # a linha segue viva no outro ticket (o selo do PDV não vira "Cancelado").
                removed.append({**it, "qty": json_quantity(gone), "partial_cancel": True})
                kept.append({**it, "qty": json_quantity(qty - gone)})
            if not removed:
                continue
            cancelled_at = timezone.now()
            if kept:
                # Não apague o fato operacional. Antes, um cancelamento parcial
                # apenas sumia do JSON do ticket vivo: o KDS não tinha card,
                # alerta nem gesto de ciência e deixava marcar Pronto no restante em
                # silêncio. O comprovante cancelado preserva somente os itens
                # retirados e usa o fluxo canônico de "Recebi o cancelamento" do board.
                ticket.items = kept
                ticket.save(update_fields=["items"])
                KDSTicket.objects.create(
                    session_key=session_key,
                    kds_instance=ticket.kds_instance,
                    items=removed,
                    status="cancelled",
                    cancelled_at=cancelled_at,
                )
                trimmed += 1
            else:
                ticket.status = "cancelled"
                ticket.cancelled_at = cancelled_at
                ticket.save(update_fields=["status", "cancelled_at"])
                cancelled += 1
    return {"cancelled": cancelled, "trimmed": trimmed}


def cancel_open_tickets(order) -> int:
    """Cancel all open tickets for order. Returns count cancelled."""
    return cancel_open_tickets_for_session(order.session_key)


def cancel_open_tickets_for_session(session_key: str) -> int:
    """Cancel open tickets after the caller locked their Session/Order source."""
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import KDSTicket

    with transaction.atomic():
        tickets = list(
            KDSTicket.objects
            .select_for_update()
            .filter(session_key=session_key, status__in=["pending", "in_progress"])
        )
        cancelled_at = timezone.now()
        for ticket in tickets:
            ticket.status = "cancelled"
            ticket.cancelled_at = cancelled_at
            ticket.save(update_fields=["status", "cancelled_at"])
        return len(tickets)


def complete_open_tickets_for_session(session_key: str, *, actor: str, via: str) -> int:
    """Conclui os tickets abertos, depois de o chamador travar a origem.

    Salva um a um (não ``update``): o ``post_save`` é o que avisa as telas por
    SSE e o que o balcão usa para tirar o selo "Na cozinha".
    """
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import KDSTicket

    with transaction.atomic():
        tickets = list(
            KDSTicket.objects
            .select_for_update()
            .filter(session_key=session_key, status__in=["pending", "in_progress"])
        )
        completed_at = timezone.now()
        for ticket in tickets:
            ticket.status = "done"
            ticket.completed_at = completed_at
            ticket.completed_by = str(actor or "")[:150]
            ticket.completed_via = via
            ticket.save(update_fields=["status", "completed_at", "completed_by", "completed_via"])
        return len(tickets)


def reopen_done_tickets(session_key: str, ticket_ids) -> list[int]:
    """Volta ao preparo os tickets concluídos indicados (desfazer do pronto automático).

    O chamador já travou a origem. Salva um a um, pelo mesmo motivo de
    ``complete_open_tickets_for_session``: o ``post_save`` avisa as telas.
    """
    from django.db import transaction

    from shopman.backstage.models import KDSTicket

    reopened = []
    with transaction.atomic():
        for ticket in KDSTicket.objects.select_for_update().filter(
            pk__in=list(ticket_ids or []), session_key=session_key, status="done",
        ):
            ticket.status = "in_progress"
            ticket.completed_at = None
            ticket.completed_by = ""
            ticket.completed_via = ""
            ticket.save(update_fields=["status", "completed_at", "completed_by", "completed_via"])
            reopened.append(ticket.pk)
    return reopened


def get_tickets(order):
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(session_key=order.session_key)


def get_completed_ticket_timestamps(order) -> list[tuple[int, Any]]:
    """Return [(pk, completed_at)] for tickets with a completed_at timestamp."""
    from shopman.backstage.models import KDSTicket

    return list(
        KDSTicket.objects.filter(session_key=order.session_key, completed_at__isnull=False)
        .values_list("pk", "completed_at")
    )


def shift_ticket_completed_at(pk: int, completed_at) -> None:
    from shopman.backstage.models import KDSTicket

    KDSTicket.objects.filter(pk=pk).update(completed_at=completed_at)


def get_ticket_model():
    """Return KDSTicket model for signal wiring without direct surface imports."""
    from shopman.backstage.models import KDSTicket

    return KDSTicket


def active_ticket_count(kds_instance_id) -> int:
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.filter(
        kds_instance_id=kds_instance_id,
        status__in=["pending", "in_progress"],
    ).count()


def get_ticket(ticket_pk) -> Any:
    """O ticket com a estação, ou ``None`` (avisos da Cozinha, ``kds_alerts``)."""
    from shopman.backstage.models import KDSTicket

    return KDSTicket.objects.select_related("kds_instance").filter(pk=ticket_pk).first()


def get_instance(instance_pk) -> Any:
    from shopman.backstage.models import KDSInstance

    return KDSInstance.objects.filter(pk=instance_pk).first()


def instances_followed_by(user_id: int) -> list[Any]:
    """Estações que guardam este operador entre quem as leva no bolso."""
    from shopman.backstage.models import KDSInstance

    key = str(int(user_id))
    return [
        instance
        for instance in KDSInstance.objects.filter(is_active=True).exclude(type="expedition")
        if key in ((instance.config or {}).get("followers") or {})
    ]
