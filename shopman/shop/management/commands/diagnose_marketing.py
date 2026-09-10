"""One read-only, PII-free snapshot for every Marketing incident runbook."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, QuerySet
from django.utils import timezone

MARKETING_ALERT_TYPES = (
    "marketing_consent_violation",
    "marketing_duplicate_confirmed",
    "marketing_outbox_stuck",
    "marketing_reconciliation_mismatch",
    "marketing_unknown_stale",
    "marketing_partial_without_action",
    "marketing_readiness_stale",
)
PLATFORMS = ("instagram", "facebook", "google_business", "whatsapp", "other")


class Command(BaseCommand):
    help = (
        "Resume fila/ledger/alertas de Marketing sem alterar estado, chamar "
        "provider ou exibir conteúdo/recipient."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--receipt",
            default="",
            help="Ref técnica opcional do command receipt.",
        )
        parser.add_argument(
            "--platform",
            choices=("all", *PLATFORMS),
            default="all",
            help="Limita agregados a uma plataforma (default: all).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emite um único JSON copiável para o registro do incidente.",
        )

    def handle(self, *args, **options):
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.models import (
            DeliveryAttempt,
            DeliveryReconciliation,
            DeliveryTarget,
            MarketingCommandReceipt,
            MarketingOutbox,
        )

        receipt_ref = str(options["receipt"] or "").strip()
        platform = str(options["platform"] or "all")
        receipt = None
        if receipt_ref:
            try:
                parsed_ref = uuid.UUID(receipt_ref)
            except ValueError as exc:
                raise CommandError("--receipt deve ser uma UUID técnica válida.") from exc
            try:
                receipt = MarketingCommandReceipt.objects.only(
                    "ref", "kind", "state", "created_at"
                ).get(ref=parsed_ref)
            except MarketingCommandReceipt.DoesNotExist as exc:
                raise CommandError("Command receipt não encontrado.") from exc

        outboxes: QuerySet = MarketingOutbox.objects.all()
        targets: QuerySet = DeliveryTarget.objects.all()
        attempts: QuerySet = DeliveryAttempt.objects.all()
        reconciliations: QuerySet = DeliveryReconciliation.objects.all()
        if receipt is not None:
            outboxes = outboxes.filter(command=receipt)
            targets = targets.filter(outbox__command=receipt)
            attempts = attempts.filter(target__outbox__command=receipt)
            reconciliations = reconciliations.filter(command=receipt)
        if platform != "all":
            outboxes = outboxes.filter(platform=platform)
            targets = targets.filter(platform=platform)
            attempts = attempts.filter(target__platform=platform)
            reconciliations = reconciliations.filter(target__platform=platform)

        cutoff = timezone.now() - timedelta(seconds=30)
        stale_outbox = outboxes.filter(
            state=MarketingOutbox.State.PENDING,
            available_at__lte=cutoff,
        ).count()
        open_alerts = OperatorAlert.objects.filter(
            type__in=MARKETING_ALERT_TYPES,
            acknowledged=False,
        )
        report = {
            "schema": "shopman.marketing.diagnostic.v1",
            "mode": "read_only",
            "provider_calls": 0,
            "pii": False,
            "scope": {
                "receipt_ref": str(receipt.ref) if receipt else "all",
                "platform": platform,
            },
            "receipt": (
                {
                    "kind": receipt.kind,
                    "state": receipt.state,
                    "created_at": receipt.created_at.isoformat(),
                }
                if receipt
                else None
            ),
            "outbox": {
                "by_state": _counts(outboxes, "state"),
                "stale_pending": stale_outbox,
            },
            "targets": {"by_state": _counts(targets, "state")},
            "attempts": {"by_outcome": _counts(attempts, "outcome_kind")},
            "reconciliation": {"by_state": _counts(reconciliations, "state")},
            "open_alerts": _counts(open_alerts, "type"),
        }
        report["result"] = _result(report)
        report["next"] = _next_actions(report)

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return
        self.stdout.write(
            f"result={report['result']} mode=read_only provider_calls=0 pii=false "
            f"receipt={report['scope']['receipt_ref']} platform={platform}"
        )
        for name in ("outbox", "targets", "attempts", "reconciliation"):
            self.stdout.write(
                f"result={report['result']} {name}="
                f"{json.dumps(report[name], ensure_ascii=False, sort_keys=True)}"
            )
        self.stdout.write(
            f"result={report['result']} open_alerts="
            f"{json.dumps(report['open_alerts'], ensure_ascii=False, sort_keys=True)}"
        )
        for action in report["next"]:
            self.stdout.write(f"next={action}")


def _counts(queryset: QuerySet, field: str) -> dict[str, int]:
    return {
        str(row[field] or "pending"): int(row["total"])
        for row in queryset.values(field).annotate(total=Count("pk")).order_by(field)
    }


def _result(report: dict) -> str:
    alerts = report["open_alerts"]
    if alerts.get("marketing_consent_violation") or alerts.get(
        "marketing_duplicate_confirmed"
    ):
        return "FAIL"
    if (
        report["outbox"]["stale_pending"]
        or report["targets"]["by_state"].get("unknown")
        or any(alerts.values())
    ):
        return "WARN"
    return "OK"


def _next_actions(report: dict) -> list[str]:
    alerts = report["open_alerts"]
    actions: list[str] = []
    if alerts.get("marketing_consent_violation"):
        actions.append("freeze_and_open:marketing-consent-or-privacy-incident.md")
    if alerts.get("marketing_duplicate_confirmed"):
        actions.append("freeze_and_open:marketing-cancel-and-reconcile.md")
    if report["outbox"]["stale_pending"]:
        actions.append("open:marketing-stuck-command.md")
    if report["targets"]["by_state"].get("unknown"):
        actions.append("open:marketing-unknown-provider-effect.md")
    if not actions:
        actions.append("observe:no_mutation_indicated")
    return actions
