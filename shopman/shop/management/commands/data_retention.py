"""Dry-run único e sem PII da política de retenção R01–R15."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.services.data_retention import build_retention_dry_run


class Command(BaseCommand):
    help = "Conta candidatos da política R01–R15 sem alterar dados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mantido por legibilidade; o comando já é sempre não destrutivo.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emite JSON estável para anexar ao gate humano.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Reservado para uma etapa futura; permanece bloqueado.",
        )

    def handle(self, *args, **options):
        if options["apply"]:
            raise CommandError(
                "Aplicação bloqueada: descarte e jobs exigem implementação, dry-run "
                "revisado e gate humano separado. Nenhum dado foi alterado."
            )

        rows = build_retention_dry_run()
        payload = {
            "mode": "dry-run",
            "pii": False,
            "mutations": 0,
            "rules": [row.as_dict() for row in rows],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return

        self.stdout.write(self.style.WARNING("DRY-RUN — nenhuma alteração; saída sem PII."))
        for row in rows:
            breakdown = ", ".join(f"{key}={value}" for key, value in row.counts.items())
            self.stdout.write(
                f"{row.rule} candidatos={row.candidates} estado={row.status} ({breakdown})"
            )
