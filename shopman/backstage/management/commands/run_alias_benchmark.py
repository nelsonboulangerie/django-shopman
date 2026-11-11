"""Mede o de-para de produto e guarda o placar no Admin. Só à mão: ``--now`` mede já.

Invólucro de ``bi.matcher_benchmark.maybe_measure``. Fora do ``maintenance_worker``
desde 11/11/2026: no ciclo automático ele recomeçava do zero a cada deploy e gastou
cerca de US$ 1.180 de API. Sem ``--now`` respeita o prazo semanal. Com ou sem
``--now``, valem as travas de settings: concorrente pago (Haiku, Opus, Jev) só com
``SHOPMAN_ALIAS_BENCHMARK_PAID_ENABLED=true``, no máximo
``SHOPMAN_ALIAS_BENCHMARK_MAX_CASES`` casos e teto de gasto
``SHOPMAN_ALIAS_BENCHMARK_BUDGET_USD``. Sem os pagos, mede fuzzy e embeddings
(custo zero).
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
