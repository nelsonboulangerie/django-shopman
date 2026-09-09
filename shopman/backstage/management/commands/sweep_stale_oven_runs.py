"""Abandon stale open oven runs (BI-PLAN §4.3).

Run aberto sem Concluir dentro do teto não mede: vira ``abandoned``. O teto
default é o mesmo da janela de produção em andamento
(``ProductionConfig.alerts.default_max_started_minutes``).
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from shopman.craftsman.models import WorkOrder

from shopman.backstage.models import OvenRun
from shopman.backstage.services.production import _abandon_open_oven_run
from shopman.shop.production_config import ProductionConfig


class Command(BaseCommand):
    help = "Marca como 'sem medição' runs de forno abertos além do teto (default: janela de produção)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-minutes",
            type=int,
            default=0,
            help="Teto em minutos. 0 = usar ProductionConfig.alerts.default_max_started_minutes.",
        )

    def handle(self, *args, **options):
        max_minutes = options["max_minutes"] or ProductionConfig.load().alerts.default_max_started_minutes
        cutoff = timezone.now() - timedelta(minutes=max_minutes)
        stale_run_ids = list(
            OvenRun.objects.filter(status="open", armed_at__lt=cutoff).order_by("pk").values_list("pk", flat=True)
        )
        abandoned = 0
        for run_id in stale_run_ids:
            snapshot = OvenRun.objects.only("work_order_ref").get(pk=run_id)
            with transaction.atomic():
                try:
                    work_order = WorkOrder.objects.select_for_update().get(ref=snapshot.work_order_ref)
                except WorkOrder.DoesNotExist:
                    # Legacy orphan: no aggregate exists for an append-only
                    # WorkOrderEvent, but preserve the reason on the run.
                    run = (
                        OvenRun.objects.select_for_update()
                        .filter(pk=run_id, status="open", armed_at__lt=cutoff)
                        .first()
                    )
                    if run is None:
                        continue
                    run.status = "abandoned"
                    run.metadata = {
                        **(run.metadata or {}),
                        "abandoned_at": timezone.now().isoformat(),
                        "abandoned_by": "system:oven-sweep",
                        "abandoned_reason": "stale_timeout_orphan",
                        "terminal_transition": "sweep",
                    }
                    run.save(update_fields=["status", "metadata"])
                    abandoned += 1
                    continue

                still_stale = (
                    OvenRun.objects.select_for_update()
                    .filter(
                        pk=run_id,
                        work_order_ref=work_order.ref,
                        status="open",
                        armed_at__lt=cutoff,
                    )
                    .exists()
                )
                if not still_stale:
                    continue
                if (
                    _abandon_open_oven_run(
                        work_order,
                        actor="system:oven-sweep",
                        transition="sweep",
                        reason="stale_timeout",
                        run_id=run_id,
                    )
                    is not None
                ):
                    abandoned += 1
        if abandoned:
            self.stdout.write(f"{abandoned} run(s) de forno sem resposta viraram 'sem medição'.")
        else:
            self.stdout.write("Nenhum run de forno vencido. Nada a fazer.")
