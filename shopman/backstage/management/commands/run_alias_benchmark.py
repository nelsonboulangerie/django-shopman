"""Mede o de-para de produto e guarda o placar no Admin. Roda no ``maintenance_worker``.

Invólucro de ``bi.matcher_benchmark.maybe_measure``: com pelo menos 20 de-paras
confirmados e o último placar com mais de 7 dias, mede fuzzy, LLMs (Haiku e
Opus) e, quando disponíveis, embeddings e Jev, e grava ``AliasBenchmarkReport``
(B.I. → Placar do de-para). Fora disso volta calado — rodar a cada 5 minutos não
custa nada. ``--now`` força a medição.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mede o de-para de produto (semanal) e guarda o placar em B.I. → Placar do de-para."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="yooga", help="Origem do histórico (default: yooga).")
        parser.add_argument("--now", action="store_true", help="Mede já, sem esperar a semana.")

    def handle(self, *args, **options):
        from shopman.backstage.bi.matcher_benchmark import maybe_measure

        report, reason = maybe_measure(source=options["source"], force=options["now"])
        if report is not None or options["now"]:
            self.stdout.write(f"placar do de-para: {reason}")
