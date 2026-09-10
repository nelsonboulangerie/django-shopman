"""
Management command: sweep_waitlist_windows

Fecha as janelas de confirmação vencidas da fila de espera (WP-P2E §5).

A janela é a única parte da fila que tem relógio: a fermata espera a fornada
sem prazo, mas depois que a fornada sai o cliente tem ``confirmation_minutes``
para confirmar. Sem esta varredura o prazo seria decorativo — a vaga ficaria
presa a quem não respondeu e o próximo da fila nunca seria chamado.

Vencida a janela, a reserva é liberada e a vaga vai ao próximo (FCFS,
``release_policy=serve_next``). Liberação nunca é silenciosa: o cliente é
avisado de que saiu da fila e a loja recebe OperatorAlert.

Idempotente: pedido já liberado sai do filtro (``state`` deixa de ser
``confirming``).

Usage::

    python manage.py sweep_waitlist_windows
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Libera as janelas de confirmação vencidas da fila de espera."

    def handle(self, *args, **options):
        from shopman.shop.services import waitlist

        released = waitlist.sweep_expired()
        self.stdout.write(f"Janelas de confirmação vencidas liberadas: {released}")
        return None
