"""Repescagem do acionador de incidentes (roda no ``maintenance_worker``).

O acionador nasce com o alerta (Directive ``incident.act``). Aqui: alerta com
remédio que ficou sem directive viva ganha uma, e a conferência que passou do
prazo vira "não resolveu". Sem chamada de rede, sem modelo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Repescagem do acionador de incidentes: directive perdida e conferência vencida."

    def handle(self, *args, **options):
        from shopman.backstage.incidents.act import sweep

        counts = sweep()
        if counts["enqueued"] or counts["expired"]:
            self.stdout.write(f"incidentes: {counts['enqueued']} acionador(es) refeito(s), {counts['expired']} conferência(s) vencida(s)")
