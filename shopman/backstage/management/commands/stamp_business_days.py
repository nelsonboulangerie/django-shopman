"""Congela o expediente praticado nos dias que já terminaram.

O horário da loja é configuração viva: muda quando a casa decide, e feriados
entram e saem do calendário. Sem congelar, a métrica de ontem mudaria de valor
porque alguém mexeu no cadastro hoje — e um feriado em que a casa nem abriu
contaria como expediente cheio.

Idempotente. Só olha para trás: o dia de hoje ainda não terminou.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.backstage.services.business_day import stamp_recent_days


class Command(BaseCommand):
    help = "Congela o expediente dos últimos dias no contexto do dia."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **options):
        stamped = stamp_recent_days(days=options["days"])
        self.stdout.write(f"expediente carimbado em {stamped} dias")
