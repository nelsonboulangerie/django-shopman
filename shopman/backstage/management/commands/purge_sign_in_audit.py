"""Envelhece a trilha de acessos de operador.

Uma trilha só é confiável enquanto ninguém pode apagar uma linha escolhida a
dedo. Então ela não se apaga pela tela: envelhece por prazo, igual para todo
mundo, e é este comando que faz isso — dentro do ciclo do ``maintenance_worker``,
sem cron novo.

180 dias por padrão (``SHOPMAN_SIGN_IN_AUDIT_RETENTION_DAYS``): longo o bastante
para investigar "mês passado", curto o bastante para a tabela nunca virar
problema — a ordem de grandeza é dezenas de linhas por dia, não milhares.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.backstage.services.sign_in_audit import purge


class Command(BaseCommand):
    help = "Apaga acessos de operador mais velhos que a retenção configurada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Retenção em dias (default: SHOPMAN_SIGN_IN_AUDIT_RETENTION_DAYS).",
        )

    def handle(self, *args, **options):
        removidas = purge(days=options["days"])
        self.stdout.write(f"{removidas} acesso(s) fora da retenção removido(s)")
