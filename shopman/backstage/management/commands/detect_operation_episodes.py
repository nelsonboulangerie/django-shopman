"""Procura sinais de que o dia teve algo estranho — sem chutar o motivo.

Roda no ciclo de manutenção, sobre o dia que já terminou. O que ele levanta vira
a pergunta do fechamento: *o que houve?* — e o motivo só existe se alguém
responder. Idempotente: o mesmo sinal não vira duas perguntas.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.backstage.services.episodes import detect_for_day


class Command(BaseCommand):
    help = "Detecta episódios que atrapalharam a operação (silêncio de vendas, fornada não realizada)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2)

    def handle(self, *args, **options):
        today = timezone.localdate()
        levantados = 0
        for offset in range(0, options["days"] + 1):
            levantados += len(detect_for_day(today - timedelta(days=offset)))
        self.stdout.write(f"{levantados} episódios levantados para explicação")
