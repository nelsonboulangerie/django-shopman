"""Sobe o cofre de dados curados para o Google Drive como Sheets nativo.

Sempre o MESMO arquivo, atualizado no lugar — quem cura guarda uma URL só.
Exige a ponte configurada (service account + pasta); sem ela, falha fechado
com a instrução de setup. Ver ``docs/guides/backup-and-restore.md``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.backup import drive, registry, workbook


class Command(BaseCommand):
    help = "Sobe o cofre para o Google Drive como planilha Google Sheets (atualiza no lugar)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            default="shopman-backup",
            help="Nome da planilha no Drive (padrão: shopman-backup).",
        )
        parser.add_argument(
            "--only", default="", help="Entidades específicas, separadas por vírgula."
        )
        parser.add_argument(
            "--with-transactional",
            action="store_true",
            help="Inclui as abas somente-leitura de conferência.",
        )

    def handle(self, *args, **options):
        names = [n.strip() for n in options["only"].split(",") if n.strip()]
        unknown = [n for n in names if registry.get(n) is None]
        if unknown:
            raise CommandError(f"Entidade desconhecida: {', '.join(unknown)}")
        with_read_only = options["with_transactional"] or any(
            registry.get(n).read_only for n in names
        )
        datasets = workbook.export_datasets(with_read_only=with_read_only)
        if names:
            datasets = {n: d for n, d in datasets.items() if n in names}

        url = drive.push_workbook(options["name"], workbook.write_xlsx(datasets))
        for name, dataset in datasets.items():
            self.stdout.write(f"  {name}: {len(dataset)} linha(s)")
        self.stdout.write(self.style.SUCCESS(f"Planilha atualizada: {url}"))
