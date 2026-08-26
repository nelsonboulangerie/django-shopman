"""Zera pelo ledger o resíduo de produção cuja WorkOrder está morta.

O buraco que este sweeper fecha: uma fornada planejada/iniciada materializa
quants em posições de PROCESSO (``producao``, ``massa``...) e no lote
``batch='started'``, com ``target_date``. Se a WO morre (void) e o ajuste do
handler ``_handle_voided`` falha — ou o quant nunca teve WO (seed, recebimento
manual) — o resíduo fica lá, e a availability o classifica como
``in_production``, que ENTRA no ``total_promisable`` (desenho intencional: o
que está no forno é prometível). Resultado: estoque fantasma prometido ao
cliente até a shelf-life vencer. No alpha havia 170 quants assim, de dias.

Por que um comando NOVO e não uma extensão do ``cleanup_stale_planning``: o
cleanup DELETA linhas que nunca materializaram (sem posição e sem nenhum
move — não há ledger a preservar). Aqui o quant tem posição, tem história de
moves, e a remoção tem que ser um lançamento ``ADJUST`` no ledger (nunca
delete, nunca SQL) com motivo legível — outro perfil de segurança, outros
guardas. A casa já separa uma vassoura por modo de falha
(``sweep_orphan_holds``, ``sweep_stuck_orders``, ``sweep_unrealized_production``);
esta é a do resíduo de produção morta.

**A janela é "só quando a WO está morta", não uma idade.** Zerar por idade
decidiria pelo operador: o quant ``started`` de ONTEM de uma WO ainda
``started`` é a fornada esquecida que a expedição aceita concluir tarde hoje —
e o ``realize`` do finish precisa do quant lá para creditar a vitrine. Zerar
antes quebraria o finish tardio e cancelaria a fornada por baixo do pano,
deixando a WO ``started`` para sempre com estoque zero. O par desenhado:

* WO viva (planned/started) com data vencida → **alerta** ``production_unfinished``
  (``production_alerts.check_unfinished_started_orders``), um por WO, e o
  OPERADOR decide (concluir tarde ou void);
* o void do operador dispara a baixa normal via ``production_changed``; este
  sweeper é a REDE para o que sobrou — ajuste do void que falhou (o handler é
  best-effort, engole exceção), WO morta antiga, quant órfão sem WO.

Guardas, por quant elegível (processo/started, ``target_date < hoje``, qty > 0):

* qualquer WO planned/started no par (sku, target_date) → NÃO toca (vivo);
* WO finished com o ledger aberto (sem os carimbos ``stock_consumed_at``/
  ``stock_realized_at``) → NÃO toca: dentro de 48h o
  ``sweep_unrealized_production`` ainda realiza esse quant na vitrine (e por
  isso este comando roda DEPOIS dele no ciclo); além disso é conferência
  humana já alertada — zerar brigaria com quem confere;
* hold ativo (pending/confirmed) → NÃO toca: o hold é promessa de cliente em
  voo; ``release_expired_holds``/``sweep_orphan_holds`` soltam primeiro e o
  próximo ciclo limpa;
* posição saleable → fora do escopo (não é resíduo de processo).

Idempotente: zerado não tem ``_quantity > 0`` e sai da seleção.

Uso::

    python manage.py sweep_dead_production_stock
    python manage.py sweep_dead_production_stock --dry-run
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Zera pelo ledger quants de processo com target_date vencida e sem WO viva."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista os quants que seriam zerados, sem escrever no ledger.",
        )

    def handle(self, *args, **options):
        from shopman.craftsman import STARTED_BATCH, stock_legs_complete
        from shopman.craftsman.models import WorkOrder
        from shopman.stockman import Hold, HoldStatus
        from shopman.stockman.models import PositionKind, Quant
        from shopman.stockman.services.movements import StockMovements

        today = timezone.localdate()
        dry_run = bool(options["dry_run"])

        active_holds = Hold.objects.filter(
            quant_id=OuterRef("pk"),
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )

        candidates = list(
            Quant.objects.filter(_quantity__gt=0, target_date__lt=today)
            .filter(
                Q(batch=STARTED_BATCH) | Q(position__kind=PositionKind.PROCESS)
            )
            .exclude(position__is_saleable=True)
            .annotate(has_holds=Exists(active_holds))
            .filter(has_holds=False)
            .select_related("position")
            .order_by("pk")
        )
        if not candidates:
            return

        # WOs dos pares (sku, target_date) candidatos, num query só.
        work_orders = WorkOrder.objects.filter(
            output_sku__in={q.sku for q in candidates},
            target_date__in={q.target_date for q in candidates},
        ).only("status", "output_sku", "target_date", "meta")
        by_pair: dict[tuple, list] = defaultdict(list)
        for wo in work_orders:
            by_pair[(wo.output_sku, wo.target_date)].append(wo)

        live_statuses = {WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED}
        zeroed = 0
        skipped_live = 0
        skipped_open_ledger = 0
        for quant in candidates:
            pair_wos = by_pair.get((quant.sku, quant.target_date), [])
            if any(wo.status in live_statuses for wo in pair_wos):
                # WO viva: o operador ainda pode concluir tarde — o alerta
                # production_unfinished é quem cobra, nunca a vassoura.
                skipped_live += 1
                continue
            if any(
                wo.status == WorkOrder.Status.FINISHED and not stock_legs_complete(wo)
                for wo in pair_wos
            ):
                # Ledger aberto: território do sweep_unrealized_production
                # (ou de conferência humana já alertada). Zerar aqui perderia
                # estoque real ainda por realizar.
                skipped_open_ledger += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  - Quant#{quant.pk} sku={quant.sku} pos="
                    f"{quant.position.ref if quant.position else '(nenhuma)'} "
                    f"batch={quant.batch or '(diário)'} target={quant.target_date} "
                    f"qty={quant._quantity}"
                )
                zeroed += 1
                continue

            StockMovements.adjust(
                quant,
                Decimal("0"),
                reason=(
                    f"Resíduo de produção sem WO ativa "
                    f"(fornada de {quant.target_date:%d/%m/%Y})"
                ),
            )
            zeroed += 1

        if skipped_live or skipped_open_ledger:
            logger.info(
                "sweep_dead_production_stock: %d quant(s) preservado(s) por WO viva, "
                "%d por ledger de produção aberto",
                skipped_live,
                skipped_open_ledger,
            )
        if zeroed:
            logger.info(
                "sweep_dead_production_stock: %d quant(s) de produção morta zerado(s)",
                zeroed,
            )
            self.stdout.write(
                self.style.WARNING(
                    f"sweep_dead_production_stock: {zeroed} quant(s) "
                    f"{'listado(s) [dry-run]' if dry_run else 'zerado(s) pelo ledger'}."
                )
            )
