"""Audit explicit Day-1 production outputs and their material dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.data_readiness.operational import (
    OperationalAuditError,
    audit_operational_day1,
    database_operational_snapshot,
    read_sku_scope,
)


class Command(BaseCommand):
    help = "Audita receitas, insumos, fornecedores, conversões e custos Day-1; nunca grava dados."

    def add_arguments(self, parser):
        parser.add_argument("--sku", action="append", default=[], help="SKU de produção Day-1. Repetível.")
        parser.add_argument("--sku-file", help="Arquivo UTF-8 com um SKU por linha; # inicia comentário.")
        parser.add_argument("--output", help="Arquivo JSON novo. Sem esta opção, escreve no stdout.")

    def handle(self, *args, **options):
        try:
            scope = read_sku_scope(options["sku"], options["sku_file"])
            report = audit_operational_day1(scope, database_operational_snapshot())
        except OperationalAuditError as exc:
            raise CommandError(str(exc)) from exc

        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output = options["output"]
        if not output:
            self.stdout.write(rendered, ending="")
            return
        destination = Path(output)
        if destination.exists():
            raise CommandError("O relatório já existe; escolha um novo caminho para preservar a auditoria.")
        if options["sku_file"] and destination.resolve() == Path(options["sku_file"]).resolve():
            raise CommandError("O relatório não pode sobrescrever o arquivo de escopo.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Auditoria somente leitura criada em {destination}."))
