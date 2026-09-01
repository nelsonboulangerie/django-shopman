"""Exporta o cofre de dados curados para XLSX (ou diretório de CSVs).

O arquivo sai com uma aba por entidade registrada no cofre (catálogo, receitas,
fornecedores, regras, canais, copy, de-paras...), com identidade por chave
natural — pronto para abrir no Google Sheets, editar e voltar pelo
``import_backup``. Guia: ``docs/guides/backup-and-restore.md``.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from shopman.shop.backup import registry, workbook


class Command(BaseCommand):
    help = "Exporta as entidades curadas para um arquivo de backup (XLSX ou CSVs)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default="var/backups",
            help="Diretório de saída (padrão: var/backups/).",
        )
        parser.add_argument(
            "--format",
            choices=("xlsx", "csv"),
            default="xlsx",
            help="xlsx = um arquivo, uma aba por entidade. csv = um arquivo por entidade.",
        )
        parser.add_argument(
            "--only",
            default="",
            help="Entidades específicas, separadas por vírgula (ex.: products,recipes).",
        )

    def handle(self, *args, **options):
        names = [n.strip() for n in options["only"].split(",") if n.strip()]
        unknown = [n for n in names if registry.get(n) is None]
        if unknown:
            known = ", ".join(e.name for e in registry.entries())
            raise CommandError(
                f"Entidade desconhecida: {', '.join(unknown)}. Registradas: {known}"
            )

        datasets = workbook.export_datasets()
        if names:
            datasets = {n: d for n, d in datasets.items() if n in names}

        out_dir = Path(options["out"])
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        if options["format"] == "xlsx":
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"backup-{stamp}.xlsx"
            path.write_bytes(workbook.write_xlsx(datasets))
            target = path
        else:
            target = out_dir / f"backup-{stamp}"
            workbook.write_csv_dir(datasets, target)

        for name, dataset in datasets.items():
            self.stdout.write(f"  {name}: {len(dataset)} linha(s)")
        self.stdout.write(self.style.SUCCESS(f"Backup escrito em {target}"))
