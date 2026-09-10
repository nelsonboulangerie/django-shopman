from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.handlers.production_order_sync import (
    reconcile_production_order_links,
)


class Command(BaseCommand):
    help = "Audita vínculos Order ↔ WorkOrder; use --apply para reparar pendências e referências órfãs."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava os reparos. Sem esta opção, executa somente dry-run.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Confirma a trava global necessária para reparar todos os vínculos.",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])
        if apply and not options["all"]:
            raise CommandError(
                "O reparo global trava WorkOrders e Orders; repita com --apply --all em janela de manutenção."
            )
        report = reconcile_production_order_links(apply=apply)
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
