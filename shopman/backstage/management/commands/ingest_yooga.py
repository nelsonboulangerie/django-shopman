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
from shopman.backstage.bi.ingest.yooga import ingest, marcar_entrega_por_taxa


class Command(BaseCommand):
    help = "Ingere o export consolidado do Yooga (xlsx) em HistoricalSale/HistoricalSaleItem, por lote."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Caminho do yooga-consolidado.xlsx.")
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Apaga vendas, itens e lotes de source=yooga e recarrega do arquivo.",
        )
        parser.add_argument(
            "--delivery-flags-only",
            action="store_true",
            help=(
                "Só remarca entrega pela taxa, sobre o que já está no banco. "
                "Dispensa o --file: serve para corrigir histórico já carregado."
            ),
        )

    def handle(self, *args, **options):
        # A remarcação lê só o banco. Sem esta saída, corrigir histórico já
        # carregado exigiria ter o xlsx no servidor — que é justamente o que não
        # se tem depois de um ingest feito meses atrás.
        if options["delivery_flags_only"]:
            marcadas = marcar_entrega_por_taxa()
            self.stdout.write(
                self.style.SUCCESS(f"✅ {marcadas} vendas remarcadas como entrega pela taxa.")
            )
            return

        if not options["file"]:
            raise CommandError("--file é obrigatório (ou use --delivery-flags-only).")

        try:
            ingest(options["file"], rebuild=options["rebuild"], log=self.stdout.write)
        except IngestError as exc:
            raise CommandError(str(exc)) from exc
