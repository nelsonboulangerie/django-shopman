"""Audit a normalized catalog candidate against the operational database."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.data_readiness.catalog import (
    CatalogAuditError,
    audit_catalog_candidate,
    database_catalog_snapshot,
    read_catalog_candidate,
)


class Command(BaseCommand):
    help = "Audita CSV normalizado do catálogo Day-1 em modo somente leitura; nunca importa nem publica."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="CSV normalizado privado do catálogo consolidado.")
        parser.add_argument("--output", help="Arquivo JSON novo. Sem esta opção, escreve no stdout.")

    def handle(self, *args, **options):
        try:
            rows, source = read_catalog_candidate(options["file"])
            report = audit_catalog_candidate(rows, database_catalog_snapshot(), source=source)
        except CatalogAuditError as exc:
            raise CommandError(str(exc)) from exc

        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output = options["output"]
        if not output:
            self.stdout.write(rendered, ending="")
            return
        destination = Path(output)
        if destination.exists():
            raise CommandError("O relatório já existe; escolha um novo caminho para preservar a auditoria.")
        if destination.resolve() == Path(options["file"]).resolve():
            raise CommandError("O relatório não pode sobrescrever o candidato de origem.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Auditoria somente leitura criada em {destination}."))
