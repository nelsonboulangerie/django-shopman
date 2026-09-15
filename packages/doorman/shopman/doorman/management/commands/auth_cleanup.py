"""Remove credenciais efêmeras já vencidas, sem misturar as três rotinas.

Usage:
    python manage.py auth_cleanup
    python manage.py auth_cleanup --days=7
    python manage.py auth_cleanup --dry-run
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError
from shopman.doorman.services.access_link import AccessLinkService
from shopman.doorman.services.device_trust import DeviceTrustService
from shopman.doorman.services.verification import AuthService

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 7


class Command(BaseCommand):
    help = "Remove links, códigos e aparelhos confiáveis após a retenção de segurança."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=_RETENTION_DAYS,
            help="Compatibilidade de CLI; a política fixa exige exatamente 7 dias.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra somente contagens, sem alterar dados.",
        )

    def handle(self, *args, **options):
        days = int(options["days"])
        dry_run = options["dry_run"]
        if days != _RETENTION_DAYS:
            raise CommandError(
                f"R10 fixa a retenção em {_RETENTION_DAYS} dias após a expiração; "
                "nenhum dado foi alterado."
            )

        if dry_run:
            from datetime import timedelta

            from django.utils import timezone
            from shopman.doorman.models import AccessLink, TrustedDevice, VerificationCode

            cutoff = timezone.now() - timedelta(days=days)
            tokens_count = AccessLink.objects.filter(expires_at__lt=cutoff).count()
            codes_count = VerificationCode.objects.filter(expires_at__lt=cutoff).count()
            devices_count = TrustedDevice.objects.filter(expires_at__lt=cutoff).count()

            self.stdout.write("DRY-RUN — nenhuma alteração; saída sem dados pessoais.")
            self.stdout.write(f"links_de_acesso={tokens_count}")
            self.stdout.write(f"codigos_de_verificacao={codes_count}")
            self.stdout.write(f"aparelhos_confiaveis={devices_count}")
            return

        tasks = (
            ("links_de_acesso", AccessLinkService.cleanup_expired_tokens),
            ("codigos_de_verificacao", AuthService.cleanup_expired_codes),
            ("aparelhos_confiaveis", DeviceTrustService.cleanup),
        )
        counts: dict[str, int] = {}
        failures: list[str] = []
        for name, cleanup in tasks:
            try:
                counts[name] = int(cleanup(days=days))
            except Exception:
                failures.append(name)
                # O traceback pode carregar token, contato ou payload do banco.
                # A etapa já identifica o suficiente para o alerta operacional.
                logger.error("auth_cleanup: etapa %s falhou; detalhe protegido", name)

        if counts:
            self.stdout.write(
                self.style.SUCCESS(
                    "Limpeza concluída nas etapas disponíveis: "
                    + ", ".join(f"{name}={count}" for name, count in counts.items())
                    + f"; retenção após expiração={days} dia(s)."
                )
            )
        if failures:
            raise CommandError(
                "Limpeza parcial: falharam "
                + ", ".join(failures)
                + "; as demais etapas foram executadas e nenhum identificador foi exibido."
            )
