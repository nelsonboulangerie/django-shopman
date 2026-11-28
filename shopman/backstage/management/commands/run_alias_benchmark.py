"""Mede o de-para de produto e guarda o placar no Admin. Só à mão: ``--now`` mede já.

Invólucro de ``bi.matcher_benchmark.maybe_measure``. Fora do ``maintenance_worker``
desde 11/11/2026: no ciclo automático ele recomeçava do zero a cada deploy e gastou
cerca de US$ 1.180 de API. Sem ``--now`` respeita o prazo semanal. As travas são
flags deste comando, nunca settings, para que nenhuma variável de ambiente religue o
gasto: concorrente pago (Haiku, Opus, Jev) só com ``--paid``; no máximo
``--max-cases`` casos (default 60) e teto de gasto estimado ``--budget-usd``
(default US$ 1). Sem ``--paid``, mede fuzzy e embeddings (custo zero).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mede o de-para de produto (semanal) e guarda o placar em B.I. → Placar do de-para."

    def add_arguments(self, parser):
        from shopman.backstage.bi.matcher_benchmark import BUDGET_USD, MAX_CASES

        parser.add_argument("--source", default="yooga", help="Origem do histórico (default: yooga).")
        parser.add_argument("--now", action="store_true", help="Mede já, sem esperar a semana.")
        parser.add_argument(
            "--paid", action="store_true", help="Inclui os concorrentes pagos (LLM, Jev). Sem isto, custo zero."
        )
        parser.add_argument("--max-cases", type=int, default=MAX_CASES, help=f"Teto de casos (default {MAX_CASES}).")
        parser.add_argument(
            "--budget-usd", type=float, default=BUDGET_USD, help=f"Teto de gasto estimado em US$ (default {BUDGET_USD})."
        )

    def handle(self, *args, **options):
        from shopman.backstage.bi.matcher_benchmark import maybe_measure

        report, reason = maybe_measure(
            source=options["source"],
            force=options["now"],
            paid=options["paid"],
            max_cases=options["max_cases"],
            budget_usd=options["budget_usd"],
        )
        if report is not None or options["now"]:
            self.stdout.write(f"placar do de-para: {reason}")
