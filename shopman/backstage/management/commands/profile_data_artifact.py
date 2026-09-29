"""Profile one private data artifact without importing or exposing row values."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.data_readiness import ArtifactProfileError, profile_artifact


class Command(BaseCommand):
    help = "Gera manifest sanitizado e somente leitura de CSV/XLSX/XML/JSON/SQLite; não importa dados."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Artefato privado a perfilar.")
        parser.add_argument("--source", required=True, help="Origem lógica (ex.: catalogo_nelson_consolidado).")
        parser.add_argument("--purpose", required=True, help="Finalidade permitida (ex.: catalog_candidate).")
        parser.add_argument("--logical-name", help="Nome lógico seguro; por padrão usa apenas o basename.")
        parser.add_argument(
            "--key",
            action="append",
            default=[],
            help="Campo de chave; em XLSX pode usar ABA:CAMPO. Repetível para chave composta.",
        )
        parser.add_argument(
            "--date",
            action="append",
            default=[],
            help="Campo de data; em XLSX pode usar ABA:CAMPO. Repetível.",
        )
        parser.add_argument("--output", help="Arquivo JSON novo. Sem esta opção, escreve no stdout.")

    def handle(self, *args, **options):
        try:
            manifest = profile_artifact(
                options["file"],
                source=options["source"],
                purpose=options["purpose"],
                logical_name=options["logical_name"],
                key_fields=options["key"],
                date_fields=options["date"],
            )
        except ArtifactProfileError as exc:
            raise CommandError(str(exc)) from exc

        rendered = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output = options["output"]
        if output:
            destination = Path(output)
            if destination.exists():
                raise CommandError("O relatório já existe; escolha um novo caminho para preservar a auditoria.")
            if destination.resolve() == Path(options["file"]).resolve():
                raise CommandError("O relatório não pode sobrescrever o artefato de origem.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Manifest sanitizado criado em {destination}."))
            return
        self.stdout.write(rendered, ending="")
