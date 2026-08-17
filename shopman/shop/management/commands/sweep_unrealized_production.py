"""Re-realiza fornadas ``finished`` cujo ledger de estoque não fechou.

O espelho do ``sweep_stuck_orders``, para produção. O ``production_changed`` é
emitido FORA do ``transaction.atomic`` do ``CraftExecution.finish``, então uma
queda de banco, um deploy no meio ou um bug no ``realize`` deixa a WorkOrder
``finished`` e commitada com o estoque pela metade: os insumos baixaram, a
vitrine ficou zero, e o retry do operador morre em ``TERMINAL_STATUS``.

Ninguém percebia porque as unidades ficam no quant ``started``, que a
availability classifica como ``in_production`` e o ``planned_ok`` promete
normalmente — a loja segue vendendo, e o fechamento do dia soma
``WorkOrder.finished`` no disponível, então ``sold > available`` nunca dispara.

Cada perna do ledger carimba seu marcador em ``WorkOrder.meta``
(``stock_consumed_at`` / ``stock_realized_at``). Este sweeper acha as fornadas
concluídas há mais que o limiar **sem** os dois marcadores e reexecuta só o que
faltou. **O marcador é o guarda**: o handler não é idempotente (o ``realize``
credita o ``actual`` cheio, independente do saldo planejado), então re-rodar
sem ele creditaria a vitrine em dobro.

Fornada que continua sem marcador depois do re-dispatch (ex.: nenhuma posição
de venda cadastrada) vira ``OperatorAlert`` de discrepância de estoque — o que
o automático não resolve tem que chegar em alguém.

Uso:
    python manage.py sweep_unrealized_production              # limiar 15 min
    python manage.py sweep_unrealized_production --minutes 30
    python manage.py sweep_unrealized_production --dry-run
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-realiza fornadas concluídas cujo ledger de estoque não fechou."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=15, help="Idade mínima concluída (default 15)."
        )
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não re-realiza.")

    def handle(self, *args, **options):
        from shopman.craftsman.contrib.stockman.handlers import (
            STOCK_CONSUMED_KEY,
            STOCK_REALIZED_KEY,
            realize_finished_production,
            stock_legs_complete,
        )
        from shopman.craftsman.models import WorkOrder

        cutoff = timezone.now() - timedelta(minutes=max(1, int(options["minutes"])))
        dry_run = bool(options["dry_run"])

        stuck = (
            WorkOrder.objects.filter(status=WorkOrder.Status.FINISHED, finished_at__lt=cutoff)
            .exclude(meta__has_keys=[STOCK_CONSUMED_KEY, STOCK_REALIZED_KEY])
            .select_related("recipe")
            .order_by("pk")
        )

        recovered = 0
        for work_order in stuck.iterator():
            logger.warning(
                "sweep_unrealized_production: fornada %s concluída com o ledger "
                "incompleto (consumo=%s, realize=%s)",
                work_order.ref,
                bool((work_order.meta or {}).get(STOCK_CONSUMED_KEY)),
                bool((work_order.meta or {}).get(STOCK_REALIZED_KEY)),
            )
            if dry_run:
                recovered += 1
                continue

            try:
                realize_finished_production(work_order)
            except Exception as exc:
                logger.exception(
                    "sweep_unrealized_production: re-realize de %s falhou", work_order.ref
                )
                self._alert(work_order, str(exc) or type(exc).__name__)
                continue

            if stock_legs_complete(work_order):
                recovered += 1
            else:
                self._alert(
                    work_order,
                    "o re-dispatch rodou sem erro e o ledger continua aberto "
                    "(sem posição de venda cadastrada?)",
                )

        if recovered:
            self.stdout.write(
                self.style.WARNING(
                    f"sweep_unrealized_production: {recovered} fornada(s) "
                    f"{'detectada(s)' if dry_run else 're-realizada(s)'}."
                )
            )

    def _alert(self, work_order, error: str) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="stock_discrepancy",
            severity="critical",
            message=(
                f"A fornada {work_order.ref} ({work_order.output_sku}) foi concluída "
                f"mas não entrou no estoque, e a recuperação automática falhou: {error}. "
                "Confira a posição de venda e ajuste o estoque na mão."
            ),
            dedupe_key=f"stock_discrepancy:{work_order.ref}",
        )
