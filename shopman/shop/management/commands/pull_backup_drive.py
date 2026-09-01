"""Baixa a planilha curada do Google Drive como XLSX, pronta para o import.

O download NÃO importa nada: ele materializa o arquivo em ``var/backups/`` e
aponta o próximo passo — ``import_backup`` (dry-run primeiro, sempre). A
separação é deliberada: puxar é inofensivo; escrever no banco continua atrás
do dry-run, da transação única e do ``--force`` de produção.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.shop.backup import drive


class Command(BaseCommand):
    help = "Baixa a planilha do cofre do Google Drive como XLSX (não importa nada)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            default="shopman-backup",
            help="Nome da planilha na pasta do Drive, ou um id de arquivo.",
        )
        parser.add_argument(
            "--out", default="var/backups", help="Diretório de saída (padrão: var/backups/)."
        )

    def handle(self, *args, **options):
        payload = drive.pull_workbook(options["name"])
        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"drive-{stamp}.xlsx"
        path.write_bytes(payload)
        self.stdout.write(self.style.SUCCESS(f"Planilha baixada em {path}"))
        self.stdout.write(f"Próximo passo: manage.py import_backup {path}  (dry-run)")
