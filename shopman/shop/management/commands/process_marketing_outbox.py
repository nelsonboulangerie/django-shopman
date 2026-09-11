"""Claim and publish committed Marketing outbox rows with stale recovery."""

from __future__ import annotations

import logging
import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcilia e processa a outbox transacional de Marketing."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--lease-seconds", type=int, default=60)
        parser.add_argument("--worker-id", default="")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=2.0)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Executa localmente mesmo com a flag segura desligada.",
        )
        parser.add_argument("--quiet-disabled", action="store_true", help="SUPPRESS")

    def handle(self, *args, **options):
        if not (
            settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED
            or options["force"]
        ):
            if not options["quiet_disabled"]:
                self.stdout.write(
                    self.style.WARNING(
                        "Outbox de Marketing desativada; nenhuma intent foi publicada."
                    )
                )
            return None
        if options["force"] and settings.SHOPMAN_ENVIRONMENT not in {
            "development",
            "test",
        }:
            raise CommandError("--force só é permitido em ambiente local/de teste.")

        worker_id = str(options["worker_id"] or f"marketing:{uuid.uuid4().hex[:12]}")
        limit = max(1, min(int(options["limit"]), 1_000))
        lease_seconds = max(10, min(int(options["lease_seconds"]), 15 * 60))
        watch = bool(options["watch"])
        interval = max(0.5, float(options["interval"]))

        while True:
            close_old_connections()
            try:
                self._cycle(
                    worker_id=worker_id,
                    limit=limit,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                if not watch:
                    raise
                logger.exception(
                    "process_marketing_outbox: ciclo falhou (worker continua)"
                )
            if not watch:
                return None
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Worker encerrado."))
                return None

    def _cycle(self, *, worker_id: str, limit: int, lease_seconds: int) -> None:
        from shopman.shop.services import marketing_outbox
        from shopman.shop.services.marketing_observability import (
            collect_reconciler_signals,
            record_outbox_cycle,
        )

        reconciliation = marketing_outbox.reconcile(limit=limit)
        report = marketing_outbox.process_due(
            worker_id=worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
        )
        record_outbox_cycle(reconciliation=reconciliation, process=report)
        collect_reconciler_signals()
        if reconciliation.dispatched_without_directive:
            logger.error(
                "marketing.outbox_dispatched_without_directive count=%d",
                reconciliation.dispatched_without_directive,
            )
        if reconciliation.directive_mismatch:
            logger.error(
                "marketing.outbox_directive_mismatch count=%d",
                reconciliation.directive_mismatch,
            )
        if reconciliation.approved_without_graph:
            logger.error(
                "marketing.approved_without_graph count=%d",
                reconciliation.approved_without_graph,
            )
        if any((
            reconciliation.linked_existing,
            reconciliation.stale_requeued,
            reconciliation.stale_failed,
            report.claimed,
        )):
            logger.info(
                "marketing.outbox_cycle claimed=%d dispatched=%d requeued=%d "
                "failed=%d lease_recovered=%d lease_failed=%d linked=%d "
                "oldest_due_age_seconds=%d",
                report.claimed,
                report.dispatched,
                report.requeued,
                report.failed,
                reconciliation.stale_requeued,
                reconciliation.stale_failed,
                reconciliation.linked_existing,
                report.oldest_due_age_seconds,
            )
            self.stdout.write(
                "Marketing outbox: "
                f"claimed={report.claimed} dispatched={report.dispatched} "
                f"requeued={report.requeued} failed={report.failed} "
                f"lease_recovered={reconciliation.stale_requeued} "
                f"linked={reconciliation.linked_existing}."
            )
