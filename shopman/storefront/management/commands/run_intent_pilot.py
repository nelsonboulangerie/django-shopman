"""Um ciclo do piloto de intenções: sorteia, pré-marca, mede. Roda no ``maintenance_worker``.

Invólucro de ``shopman.storefront.concierge.intent_pilot.run_cycle``: cada passo
tem teto próprio (40 sorteios por dia, fila aberta de até 200, placar no máximo
semanal), então rodar a cada 5 minutos custa nada quando não há o que fazer.
``SHOPMAN_INTENT_PILOT_ENABLED=false`` desliga; sem mensagem observada, não faz
nada. ``--measure-now`` força um placar fora da semana (útil depois de uma leva
de conferência).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Um ciclo do piloto de intenções (sorteia, pré-marca com IA, mede quando dá). Seguro em loop."

    def add_arguments(self, parser):
        parser.add_argument("--measure-now", action="store_true", help="Mede já, sem esperar a semana.")

    def handle(self, *args, **options):
        from shopman.storefront.concierge.intent_pilot import maybe_measure, run_cycle

        if not getattr(settings, "SHOPMAN_INTENT_PILOT_ENABLED", False):
            return
        if options["measure_now"]:
            measurement = maybe_measure(force=True)
            self.stdout.write(f"placar: {measurement.reason}")
            return
        result = run_cycle()
        if result.sampled or result.proposed or result.measurement == "medido":
            self.stdout.write(
                f"intenções: {result.sampled} sorteada(s), {result.proposed} pré-marcada(s), "
                f"placar: {result.measurement}"
            )
