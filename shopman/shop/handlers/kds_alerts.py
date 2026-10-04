"""Receivers e o despertador dos avisos da Cozinha (``services/kds_alerts.py``).

* Ticket novo → avisa quem leva a estação no bolso e arma o despertador do
  atraso (``kds.ticket_late``, ``available_at`` = criação + meta da estação).
* Ticket que anda → o aviso de pedido novo some (iniciado); ticket que sai da
  estação (pronto, cancelado) leva os dois avisos embora.

Aviso é cauda NÃO-crítica: falhar aqui vira log, nunca derruba o disparo do
ticket nem o toque da cozinha (por isso o ``transaction.on_commit`` e o corpo
blindado).
"""

from __future__ import annotations

import logging

from django.db import transaction
from shopman.orderman.models import Directive

from shopman.shop.adapters import kds as kds_adapter
from shopman.shop.directives import KDS_TICKET_LATE

logger = logging.getLogger(__name__)


def connect() -> None:
    from django.db.models.signals import post_save

    post_save.connect(
        on_ticket_saved,
        sender=kds_adapter.get_ticket_model(),
        dispatch_uid="shopman.shop.handlers.kds_alerts.on_ticket_saved",
        weak=False,
    )


def on_ticket_saved(sender, instance, created, **kwargs) -> None:
    ticket_pk = instance.pk
    status = instance.status

    def _after_commit() -> None:
        try:
            _react(ticket_pk, created=created, status=status)
        except Exception:
            logger.exception("kds_alerts.receiver_failed ticket=%s", ticket_pk)

    transaction.on_commit(_after_commit, robust=True)


def _react(ticket_pk: int, *, created: bool, status: str) -> None:
    from shopman.shop.services import kds_alerts

    ticket = kds_adapter.get_ticket(ticket_pk)
    if ticket is None:
        return
    if created:
        if ticket.status == "pending":
            kds_alerts.notify_new_ticket(ticket)
        due = kds_alerts.late_check_at(ticket)
        if due is not None:
            Directive.objects.create(
                topic=KDS_TICKET_LATE,
                payload={"ticket_pk": ticket.pk},
                available_at=due,
            )
        return
    if ticket.status in kds_alerts.OPEN_STATUSES:
        if ticket.status == "in_progress":
            kds_alerts.resolve_new_ticket(ticket, outcome_code="kds_ticket_started")
        return
    kds_alerts.resolve_ticket(ticket, outcome_code=f"kds_ticket_{ticket.status}")


class KDSTicketLateHandler:
    """Despertador do atraso de um ticket. Topic: kds.ticket_late

    Roda uma vez, quando o ticket estoura a meta da estação. Ticket que já saiu
    (pronto, cancelado, sumiu) não avisa ninguém: o worker marca done.
    """

    topic = KDS_TICKET_LATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.services import kds_alerts

        ticket_pk = (message.payload or {}).get("ticket_pk")
        if not isinstance(ticket_pk, int) or isinstance(ticket_pk, bool):
            return
        ticket = kds_adapter.get_ticket(ticket_pk)
        if ticket is None or ticket.status not in kds_alerts.OPEN_STATUSES:
            return
        kds_alerts.notify_late_ticket(ticket)
