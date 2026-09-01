"""Importa a curadoria direto do Google Drive — baixa E roda o import.

O nome diz a direção inteira do fluxo: Drive → banco. Por baixo são os dois
passos de sempre, emendados: exporta a planilha curada como XLSX (fica em
``var/backups/``, auditável) e entrega ao ``import_backup`` — que continua
mandando: dry-run por padrão, ``--apply`` numa transação única, ``--force``
obrigatório em produção. Baixar é inofensivo; escrever fica atrás dos guardas.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.shop.backup import drive


class Command(BaseCommand):
    help = "Baixa a planilha curada do Drive e importa (dry-run por padrão; --apply escreve)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            default="shopman-backup",
            help="Nome da planilha na pasta do Drive, ou um id de arquivo.",
        )
        parser.add_argument(
            "--out", default="var/backups", help="Onde guardar o XLSX baixado (auditoria)."
        )
        parser.add_argument(
            "--apply", action="store_true", help="Escreve de verdade (sem isso, só relata)."
        )
        parser.add_argument(
            "--only", default="", help="Entidades específicas, separadas por vírgula."
        )
        parser.add_argument(
            "--force", action="store_true", help="Obrigatório para --apply em produção."
        )

    def handle(self, *args, **options):
        payload = drive.download_workbook(options["name"])
        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"drive-{stamp}.xlsx"
        path.write_bytes(payload)
        self.stdout.write(f"Planilha baixada em {path}")

        flags = []
        if options["apply"]:
            flags.append("--apply")
        if options["force"]:
            flags.append("--force")
        if options["only"]:
            flags.extend(["--only", options["only"]])
        call_command("import_backup", str(path), *flags, stdout=self.stdout, stderr=self.stderr)
