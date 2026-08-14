"""Abandon stale open oven runs (BI-PLAN §4.3).

Run aberto sem Concluir dentro do teto não mede: vira ``abandoned``. O teto
default é o mesmo da janela de produção em andamento
(``ProductionConfig.alerts.default_max_started_minutes``).
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.backstage.models import OvenRun
from shopman.shop.production_config import ProductionConfig


class Command(BaseCommand):
    help = "Marca como 'sem medição' runs de forno abertos além do teto (default: janela de produção)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-minutes",
            type=int,
            default=0,
            help="Teto em minutos. 0 = usar ProductionConfig.alerts.default_max_started_minutes.",
        )

    def handle(self, *args, **options):
        max_minutes = options["max_minutes"] or ProductionConfig.load().alerts.default_max_started_minutes
        cutoff = timezone.now() - timedelta(minutes=max_minutes)
        abandoned = OvenRun.objects.filter(status="open", armed_at__lt=cutoff).update(
            status="abandoned"
        )
        if abandoned:
            self.stdout.write(f"{abandoned} run(s) de forno sem resposta viraram 'sem medição'.")
        else:
            self.stdout.write("Nenhum run de forno vencido. Nada a fazer.")
