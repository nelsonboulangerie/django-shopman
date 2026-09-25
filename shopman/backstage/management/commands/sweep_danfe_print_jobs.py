"""DANFE da entrega que a impressora do despacho não buscou vira alerta.

O card do Gestor já diz "DANFE não impressa" assim que a fila passa de
``order_danfe.RELAY_GRACE`` sem o agente buscar o trabalho. Este comando é o
aviso que chega a quem não está olhando o card: reconcilia leases e filas
vencidas e abre ``danfe_print_failed`` para cada pedido cuja DANFE não virou
papel. Roda no ``maintenance_worker``; o dedupe do alerta segura a repetição.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Alerta a DANFE da entrega que a impressora do despacho não imprimiu."

    def handle(self, *args, **options):
        from shopman.backstage.services.order_danfe import sweep_stale_jobs

        alerted = sweep_stale_jobs()
        if alerted:
            self.stdout.write(f"{alerted} DANFE(s) de entrega sem papel viraram alerta.")
