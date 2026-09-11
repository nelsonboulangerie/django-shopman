"""Minimiza IP bruto vencido nas provas de consentimento."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.guestman.contrib.consent.service import ConsentService


class Command(BaseCommand):
    help = "Remove IP bruto mais antigo que a retenção, preservando a prova de consentimento."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retenção em dias (default configurado; teto absoluto de 90).",
        )

    def handle(self, *args, **options):
        counts = ConsentService.redact_expired_ip(days=options["days"])
        total = counts["current"] + counts["events"]
        self.stdout.write(
            f"{total} IP(s) vencido(s) removido(s) "
            f"({counts['current']} projeções; {counts['events']} eventos)."
        )
