"""O Jev decidindo a intenção, em sombra: onde ele e a regra local discordam.

O ``run_intent_pilot`` grava a sombra sozinho a cada ciclo; este comando lê o
resultado (``intent_pilot.shadow_report``) e, com ``--run``, grava um lote já.
Nada muda para o cliente: a Concierge continua decidindo pela regra local até
``CONCIERGE_TRIAGE_CLASSIFIER=jev``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Relatório da sombra do Jev na triagem da Concierge (regra local × Jev)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Janela do relatório (padrão 7 dias).")
        parser.add_argument("--run", type=int, default=0, help="Antes do relatório, grava a sombra de até N mensagens.")
        parser.add_argument("--examples", type=int, default=15, help="Quantas discordâncias mostrar.")

    def handle(self, *args, **options):
        from shopman.storefront.concierge.intent_benchmark import ContenderNotConfigured
        from shopman.storefront.concierge.intent_pilot import shadow_report, shadow_triage

        if options["run"]:
            try:
                done = shadow_triage(limit=options["run"], days=options["days"])
            except ContenderNotConfigured as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"sombra gravada em {done} mensagem(ns).\n")
        self.stdout.write(shadow_report(days=options["days"], examples=options["examples"]))
