"""Alinha as faltas registradas com a disponibilidade de agora.

Os eventos de estoque e reserva cobrem quase tudo, menos um caso: reserva que
expira é liberada por varredura em massa, sem emitir signal. Sem esta
reconciliação, a volta do produto ficaria registrada só no próximo movimento —
que pode ser no dia seguinte, inflando a falta medida.

Idempotente: roda no ciclo do maintenance_worker, e rodar duas vezes seguidas
não abre nem fecha nada a mais.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.backstage.services.shelf_outages import reconcile_outages


class Command(BaseCommand):
    help = "Abre/fecha faltas de produto conforme a disponibilidade atual."

    def handle(self, *args, **options):
        result = reconcile_outages()
        self.stdout.write(
            f"faltas: {result['opened']} abertas, {result['closed']} fechadas "
            f"({result['checked']} verificações)"
        )
