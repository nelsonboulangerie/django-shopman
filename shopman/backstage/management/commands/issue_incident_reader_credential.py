"""Emite a credencial de LEITURA da ponte de incidentes (GitHub Actions).

Imprime o token uma única vez. Ele vira o segredo ``INCIDENTS_TOKEN`` do
repositório; o banco guarda só o HMAC. Revoga-se no Admin (Credenciais da ponte
de incidentes, desmarcando "ativa"). A credencial só lê o resumo de incidentes.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Emite a credencial de leitura da ponte de incidentes e imprime o token uma vez."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="GitHub Actions · ponte de incidentes")
        parser.add_argument("--ttl-days", type=int, default=365)

    def handle(self, *args, **options):
        from shopman.backstage.models import IncidentReaderCredential

        if options["ttl_days"] < 1:
            raise CommandError("--ttl-days precisa ser maior que zero.")
        expires_at = timezone.now() + timedelta(days=options["ttl_days"])
        credential, bearer = IncidentReaderCredential.issue(label=options["label"], expires_at=expires_at)
        self.stdout.write(bearer)
        self.stderr.write(
            f"Credencial …{credential.token_hint} válida até {expires_at:%d/%m/%Y}. "
            "Guarde o token como segredo INCIDENTS_TOKEN do repositório; ele não aparece de novo."
        )
