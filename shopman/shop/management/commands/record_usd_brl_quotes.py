"""Grava a PTAX de venda final dos dias com gasto de IA (o B.I. diz o gasto em reais).

O B.I. só lê a cotação; quem grava é este comando, no ``maintenance_worker``. Pega os dias
com gasto de IA dos últimos ``--days`` dias que ainda não têm cotação gravada e pede ao BCB
numa chamada só. Só grava a cotação final: dia passado, ou o próprio dia depois de publicada.
Sem dia faltando, não chama a API.

    python manage.py record_usd_brl_quotes
    python manage.py record_usd_brl_quotes --days 90
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Grava a PTAX de venda final dos dias com gasto de IA (o real do B.I. não muda depois)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=40, help="Quantos dias para trás olhar (padrão 40).")

    def handle(self, *args, **options):
        from django.db.models.functions import TruncDate

        from shopman.shop.models import AiInvocation
        from shopman.shop.services.usd_brl import record_quotes

        # A mesma fonte do B.I. (o medidor, uma linha por chamada), no fuso da loja.
        since = timezone.localdate() - timedelta(days=max(1, options["days"]))
        days = set(
            AiInvocation.objects.filter(created_at__date__gte=since, cost_usd_micros__gt=0)
            .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values_list("day", flat=True)
        )
        recorded = record_quotes(days)
        self.stdout.write(f"record_usd_brl_quotes: {recorded} cotações gravadas ({len(days)} dias com gasto)")
