"""Minimiza o IP bruto vencido nas provas de consentimento (R11).

Manual e, por padrão, só simulação. Não entra no ``maintenance_worker``: a
página pública de privacidade diz que hoje nada é apagado sozinho, e o primeiro
``--apply`` em produção é gate humano do dono.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.guestman.contrib.consent.service import ConsentService


class Command(BaseCommand):
    help = (
        "Conta (padrão) ou, com --apply, remove o IP bruto mais antigo que a retenção "
        "(teto de 90 dias), preservando a prova de consentimento."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retenção em dias (padrão: SHOPMAN_CONSENT_IP_RETENTION_DAYS; sempre entre 1 e 90).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apaga de fato. Sem esta flag o comando só conta e não altera nada.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        days = ConsentService.consent_ip_retention_days(options["days"])
        counts = ConsentService.redact_expired_ip(days=days, apply=apply)
        total = counts["current"] + counts["events"]
        detail = f"({counts['current']} na situação atual; {counts['events']} na trilha de eventos)"
        if apply:
            self.stdout.write(
                f"{total} IP(s) com mais de {days} dias removido(s) {detail}. "
                "A prova de consentimento continua inteira."
            )
            return
        self.stdout.write(
            f"Simulação: {total} IP(s) com mais de {days} dias seriam removidos {detail}. "
            "Nada foi alterado; para apagar, rode com --apply."
        )
