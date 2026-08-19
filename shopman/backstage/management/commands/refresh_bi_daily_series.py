"""Recomputa a série diária materializada do B.I. (P3 da fundação de dados).

Invólucro de ``shopman.backstage.bi.daily_series``: sem argumento recomputa os
últimos dias (o que o ``maintenance_worker`` roda a cada ciclo); ``--all`` zera
e recomputa do primeiro dia com venda até hoje (depois de importar histórico,
ou para conferir que a tabela bate com o cálculo ao vivo — é barato).
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.bi.daily_series import DEFAULT_RECENT_DAYS, refresh, refresh_all, refresh_recent


class Command(BaseCommand):
    help = "Recomputa a série diária materializada do B.I. (últimos dias por padrão; --all do início)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=DEFAULT_RECENT_DAYS,
            help=f"Quantos dias até hoje recomputar (default {DEFAULT_RECENT_DAYS}).",
        )
        parser.add_argument("--all", action="store_true", help="Zera e recomputa do primeiro dia com venda até hoje.")
        parser.add_argument("--from", dest="date_from", help="Início do intervalo (YYYY-MM-DD). Exige --to.")
        parser.add_argument("--to", dest="date_to", help="Fim do intervalo (YYYY-MM-DD). Exige --from.")

    def handle(self, *args, **options):
        if options["all"]:
            written = refresh_all()
            self.stdout.write(f"✅ série diária recomputada do início: {written} dias.")
            return
        if options["date_from"] or options["date_to"]:
            if not (options["date_from"] and options["date_to"]):
                raise CommandError("--from e --to andam juntos.")
            date_from, date_to = date.fromisoformat(options["date_from"]), date.fromisoformat(options["date_to"])
            written = refresh(date_from, date_to)
            self.stdout.write(f"✅ série diária recomputada em {date_from}..{date_to}: {written} dias.")
            return
        if options["days"] < 1:
            raise CommandError("--days precisa ser pelo menos 1.")
        written = refresh_recent(options["days"])
        self.stdout.write(f"✅ série diária recomputada nos últimos {written} dias.")
