"""Ingere o export consolidado do Yooga em HistoricalSale/Item, por lote.

Invólucro do ``shopman.backstage.bi.ingest.yooga.ingest``: o comando só traduz
argumentos e erros para o console. As regras (lote com hash, validação na
fronteira, uma transação, completar sem sobrescrever) moram no módulo, com o
motivo de cada uma.

O arquivo NÃO entra no git (``var/`` está no .gitignore); o original no Drive
nunca é editado — o xlsx abre em modo somente leitura.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.bi.ingest import IngestError
from shopman.backstage.bi.ingest.yooga import ingest


class Command(BaseCommand):
    help = "Ingere o export consolidado do Yooga (xlsx) em HistoricalSale/HistoricalSaleItem, por lote."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Caminho do yooga-consolidado.xlsx.")
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Apaga vendas, itens e lotes de source=yooga e recarrega do arquivo.",
        )

    def handle(self, *args, **options):
        try:
            ingest(options["file"], rebuild=options["rebuild"], log=self.stdout.write)
        except IngestError as exc:
            raise CommandError(str(exc)) from exc
