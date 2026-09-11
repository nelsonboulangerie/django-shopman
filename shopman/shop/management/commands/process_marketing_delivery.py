"""Run the durable per-target Marketing delivery worker."""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Processa targets aprovados de Marketing pelo ledger durável."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--lease-seconds", type=int, default=60)
        parser.add_argument("--worker-id", default="")
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=2.0)
        parser.add_argument(
            "--with-outbox",
            action="store_true",
            help="Também processa a hand-off da outbox antes dos targets.",
        )
        parser.add_argument(
            "--with-reconciliation",
            action="store_true",
            help="Também processa consultas read-only de resultados incertos.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignora apenas a flag do worker em ambiente local/de teste.",
        )
        parser.add_argument("--quiet-idle", action="store_true", help="SUPPRESS")

    def handle(self, *args, **options):
        enabled = bool(settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED)
        if not (enabled or options["force"]):
            self.stdout.write(
                self.style.WARNING(
                    "Delivery worker de Marketing desativado; nenhum target foi chamado."
                )
            )
            return None
        if options["force"] and settings.SHOPMAN_ENVIRONMENT not in {
            "development",
            "test",
        }:
            raise CommandError("--force só é permitido em ambiente local/de teste.")

        worker_id = str(options["worker_id"] or f"marketing-delivery:{uuid.uuid4().hex[:12]}")
        limit = max(1, min(int(options["limit"]), 1_000))
        lease_seconds = max(10, min(int(options["lease_seconds"]), 15 * 60))
        interval = max(0.5, float(options["interval"]))
        watch = bool(options["watch"])
        with_outbox = bool(options["with_outbox"])
        with_reconciliation = bool(options["with_reconciliation"])
        quiet_idle = bool(options["quiet_idle"])

        while True:
            close_old_connections()
            try:
                active = self._cycle(
                    worker_id=worker_id,
                    limit=limit,
                    lease_seconds=lease_seconds,
                    with_outbox=with_outbox,
                    with_reconciliation=with_reconciliation,
                    force=bool(options["force"]),
                )
                if not active and not quiet_idle and not watch:
                    self.stdout.write("Marketing delivery: nenhum trabalho elegível.")
            except Exception:
                if not watch:
                    raise
                logger.exception("process_marketing_delivery: ciclo falhou (worker continua)")
            if not watch:
                return None
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Delivery worker encerrado."))
                return None

    def _cycle(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        with_outbox: bool,
        with_reconciliation: bool,
        force: bool,
    ) -> bool:
        from shopman.shop.services.marketing_contracts import MarketingContractError
        from shopman.shop.services.marketing_delivery_attempts import (
            deterministic_attempt_token,
            execute_approved_target,
            reconcile_calling,
        )
        from shopman.shop.services.marketing_delivery_runtime import (
            SUPPORTED_PLATFORMS,
            delivery_provider,
        )
        from shopman.shop.services.marketing_delivery_worker import (
            claim_due_targets,
            release_target_claim,
        )

        clock = timezone.now()
        outbox_activity = 0
        if with_outbox:
            if not (settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED or force):
                raise CommandError(
                    "--with-outbox exige o consumer da outbox ou --force local."
                )
            from shopman.shop.services import marketing_outbox

            reconciliation = marketing_outbox.reconcile(now=clock, limit=limit)
            processed = marketing_outbox.process_due(
                worker_id=f"{worker_id}:outbox",
                now=clock,
                limit=limit,
                lease_seconds=lease_seconds,
            )
            outbox_activity = sum((
                reconciliation.linked_existing,
                reconciliation.stale_requeued,
                reconciliation.stale_failed,
                processed.claimed,
            ))

        # The signal-driven Directive can have queued targets a few milliseconds
        # after this cycle began.  Refresh the eligibility clock so a one-shot
        # operator rehearsal does not require an unexplained second invocation.
        clock = timezone.now()

        providers = {}
        for platform in SUPPORTED_PLATFORMS:
            try:
                provider = delivery_provider(platform)
            except Exception:
                logger.warning(
                    "marketing.delivery_provider_probe_failed platform=%s", platform
                )
                continue
            if provider is not None:
                providers[platform] = provider
        if not providers:
            if outbox_activity:
                self.stdout.write(
                    "Marketing delivery: outbox processada; nenhum provider elegível."
                )
            return bool(outbox_activity)

        stale_calling = reconcile_calling(now=clock, limit=limit)
        claims = claim_due_targets(
            worker_id=worker_id,
            now=clock,
            limit=limit,
            lease_seconds=lease_seconds,
            platforms=providers,
        )
        outcomes: Counter[str] = Counter()
        for target in claims.targets:
            try:
                token = deterministic_attempt_token(
                    target.ref,
                    worker_id=worker_id,
                    now=clock,
                )
                execution = execute_approved_target(
                    target.ref,
                    provider=providers[target.platform],
                    idempotency_token=token,
                    worker_id=worker_id,
                    now=clock,
                )
                outcomes[execution.attempt.outcome_kind or "in_progress"] += 1
            except MarketingContractError as exc:
                release_target_claim(
                    target.ref,
                    worker_id=worker_id,
                    code=exc.code,
                    now=clock,
                )
                outcomes["deferred"] += 1
            except Exception:
                logger.exception(
                    "marketing.delivery_target_cycle_failed platform=%s target=%s",
                    target.platform,
                    str(target.ref),
                )
                release_target_claim(
                    target.ref,
                    worker_id=worker_id,
                    code="delivery_worker_failed_before_call",
                    now=clock,
                )
                outcomes["worker_error"] += 1

        reconciliation_claimed = 0
        reconciliation_outcomes: Counter[str] = Counter()
        if with_reconciliation:
            from shopman.shop.services.marketing_delivery_recovery import (
                claim_reconciliations,
                execute_reconciliation,
            )

            reconciliation_claims = claim_reconciliations(
                worker_id=f"{worker_id}:lookup",
                now=clock,
                limit=limit,
                lease_seconds=lease_seconds,
            )
            reconciliation_claimed = len(reconciliation_claims.reconciliations)
            for reconciliation in reconciliation_claims.reconciliations:
                provider = providers.get(reconciliation.target.platform)
                execution = execute_reconciliation(
                    reconciliation.ref,
                    provider=provider,
                    worker_id=f"{worker_id}:lookup",
                    now=clock,
                )
                reconciliation_outcomes[
                    "deferred" if execution.deferred else execution.target.state
                ] += 1

        active = bool(
            outbox_activity
            or stale_calling
            or claims.examined
            or outcomes
            or reconciliation_claimed
            or reconciliation_outcomes
        )
        if active:
            outcome_text = ",".join(
                f"{name}={count}" for name, count in sorted(outcomes.items())
            ) or "none"
            reconciliation_text = ",".join(
                f"{name}={count}"
                for name, count in sorted(reconciliation_outcomes.items())
            ) or "none"
            self.stdout.write(
                "Marketing delivery: "
                f"outbox_activity={outbox_activity} examined={claims.examined} "
                f"claimed={len(claims.targets)} suppressed={claims.suppressed} "
                f"deferred={claims.deferred} stale_calling={stale_calling} "
                f"outcomes={outcome_text} "
                f"reconciliations_claimed={reconciliation_claimed} "
                f"reconciliations={reconciliation_text}."
            )
        return active
