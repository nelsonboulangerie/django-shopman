"""Via Cozinha que a impressora do posto não buscou vira alerta.

O posto sem tela não tem como descobrir que o papel não chegou: o lanche
simplesmente não é feito. Este comando reconcilia leases e filas vencidas dos
papéis da cozinha e abre ``kitchen_print_failed`` para cada ticket cujo papel
não saiu. Roda no ``maintenance_worker``; o dedupe do alerta segura a repetição.
Ver ``services/kitchen_ticket_print.py``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Alerta a Via Cozinha que a impressora do posto não imprimiu."

    def handle(self, *args, **options):
        from shopman.backstage.services.kitchen_ticket_print import sweep_stale_jobs

        alerted = sweep_stale_jobs()
        if alerted:
            self.stdout.write(f"{alerted} Via(s) Cozinha sem papel viraram alerta.")
