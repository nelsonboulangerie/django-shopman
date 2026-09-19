"""One read-only, PII-free snapshot for every Marketing incident runbook."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Exists, OuterRef, Q, QuerySet
from django.urls import Resolver404, resolve
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
_SHADOW_REASON_ORDER = (
    "approved_without_complete_graph",
    "graph_binding_mismatch",
    "artifact_hash_mismatch",
    "directive_identity_mismatch",
    "dispatched_without_directive",
    "unlinked_existing_directive",
    "duplicate_directive_key",
    "aggregate_state_mismatch",
    "aggregate_count_mismatch",
    "target_fanout_mismatch",
)
_LEGACY_REASON_ORDER = (
    "legacy_v1_api_present",
    "legacy_permission_present",
    "legacy_platform_results_present",
    "legacy_untracked_present",
)


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
        from shopman.shop.adapters import alert as alert_adapter
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
        open_alerts = alert_adapter.open_counts(MARKETING_ALERT_TYPES)
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
            "open_alerts": open_alerts,
        }
        report["lanes"] = _lanes(targets, platform=platform)
        report["shadow"] = _shadow_snapshot(
            outboxes=outboxes,
            receipt=receipt,
            platform=platform,
        )
        report["result"] = _result(report)
        report["next"] = _next_actions(report)

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return
        self.stdout.write(
            f"result={report['result']} mode=read_only provider_calls=0 pii=false "
            f"receipt={report['scope']['receipt_ref']} platform={platform}"
        )
        for name in ("outbox", "targets", "attempts", "reconciliation", "lanes"):
            self.stdout.write(
                f"result={report['result']} {name}="
                f"{json.dumps(report[name], ensure_ascii=False, sort_keys=True)}"
            )
        self.stdout.write(
            f"result={report['result']} open_alerts="
            f"{json.dumps(report['open_alerts'], ensure_ascii=False, sort_keys=True)}"
        )
        self.stdout.write(
            f"shadow={report['shadow']['status']} reasons="
            f"{json.dumps(report['shadow']['reasons'], ensure_ascii=False)} "
            f"inventory={json.dumps(report['shadow']['inventory'], ensure_ascii=False, sort_keys=True)}"
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
        report["shadow"]["status"] == "BLOCKED"
        or report["outbox"]["stale_pending"]
        or report["targets"]["by_state"].get("unknown")
        or any(lane["state"] == "unconfigured" for lane in report["lanes"].values())
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
    if report["shadow"]["status"] == "BLOCKED":
        actions.append("hold_and_open:marketing-rollout-rollback.md")
    for platform, lane in report["lanes"].items():
        if lane["state"] == "unconfigured":
            # Flag ligada (ou sem flag) e nenhuma integração registrada: defeito.
            actions.append(
                f"check_config:delivery_integration_unregistered platform={platform} "
                f"switch={lane['switch'] or '-'}"
            )
        elif lane["state"] == "switched_off" and lane["queued_targets"]:
            # Desligada de propósito: não é alerta, mas a fila parada precisa aparecer.
            actions.append(
                f"observe:platform_switched_off_holds_queued platform={platform} "
                f"switch={lane['switch']} queued={lane['queued_targets']}"
            )
    if not actions:
        actions.append("observe:no_mutation_indicated")
    return actions


def _lanes(targets: QuerySet, *, platform: str) -> dict[str, dict]:
    """Estado de cada plataforma neste ambiente, sem chamar adapter nem provedor.

    ``switched_off`` é a flag da plataforma desligada — escolha de quem opera, com os
    destinos esperando na fila. ``unconfigured`` é a flag ligada sem integração
    registrada — configuração quebrada.
    """

    from shopman.shop.models import DeliveryTarget
    from shopman.shop.services.marketing_delivery_runtime import delivery_lanes

    queued = {
        str(row["platform"]): int(row["total"])
        for row in targets.filter(state=DeliveryTarget.State.QUEUED)
        .values("platform")
        .annotate(total=Count("pk"))
        .order_by("platform")
    }
    return {
        lane.platform: {
            "state": lane.state,
            "switch": lane.switch,
            "queued_targets": queued.get(lane.platform, 0),
        }
        for lane in delivery_lanes()
        if platform in ("all", lane.platform)
    }


def _shadow_snapshot(*, outboxes: QuerySet, receipt, platform: str) -> dict:
    """Inspect rollout invariants without locks, writes or provider boundaries."""

    from shopman.orderman.models import Directive

    from shopman.shop.models import (
        Announcement,
        AnnouncementDeliveryState,
        AudienceSnapshot,
        MarketingCommandReceipt,
        MarketingContentArtifact,
        MarketingOutbox,
    )
    from shopman.shop.services.marketing_delivery_aggregate import (
        delivery_summaries_for,
    )

    rows = list(
        outboxes.select_related(
            "announcement",
            "artifact",
            "snapshot",
            "command",
        ).order_by("command_id", "available_at", "pk")
    )
    graph_binding_mismatch = 0
    artifacts = {}
    for row in rows:
        artifacts[row.artifact_id] = row.artifact
        payload = row.artifact.payload
        approved_platforms = payload.get("platforms", ()) if isinstance(payload, dict) else ()
        if (
            row.command.state != MarketingCommandReceipt.State.COMPLETED
            or row.command.resulting_version is None
            or row.artifact.version != row.command.resulting_version
            or row.snapshot.version != row.command.resulting_version
            or row.artifact.announcement_id != row.announcement_id
            or row.snapshot.announcement_id != row.announcement_id
            or row.platform not in approved_platforms
        ):
            graph_binding_mismatch += 1

    artifact_hash_mismatch = sum(
        hashlib.sha256(artifact.canonical_bytes()).hexdigest() != artifact.artifact_hash
        for artifact in artifacts.values()
    )

    approvals = MarketingCommandReceipt.objects.filter(
        kind=MarketingCommandReceipt.Kind.APPROVE,
        state=MarketingCommandReceipt.State.COMPLETED,
    )
    if receipt is not None:
        approvals = approvals.filter(pk=receipt.pk)
    approvals = approvals.annotate(
        has_outbox=Exists(MarketingOutbox.objects.filter(command_id=OuterRef("pk"))),
        has_artifact=Exists(
            MarketingContentArtifact.objects.filter(
                announcement_id=OuterRef("announcement_id"),
                version=OuterRef("resulting_version"),
            )
        ),
        has_snapshot=Exists(
            AudienceSnapshot.objects.filter(
                announcement_id=OuterRef("announcement_id"),
                version=OuterRef("resulting_version"),
            )
        ),
    )
    approved_without_complete_graph = approvals.filter(
        Q(has_outbox=False) | Q(has_artifact=False) | Q(has_snapshot=False)
    ).count()

    directive_inventory = _directive_inventory(rows, Directive)

    announcements = {row.announcement_id: row.announcement for row in rows}
    summaries = delivery_summaries_for(announcements.values())
    aggregate_state_mismatch = 0
    aggregate_count_mismatch = 0
    target_fanout_mismatch = 0
    for announcement_id, announcement in announcements.items():
        summary = summaries[announcement_id]
        aggregate_state_mismatch += summary.state != announcement.delivery_state
        aggregate_count_mismatch += not summary.counts_close
        target_fanout_mismatch += summary.targets_total != summary.fanout_materialized

    legacy_rows = Announcement.objects.filter(
        Q(~Q(platform_results={})) | Q(delivery_state=AnnouncementDeliveryState.LEGACY_UNTRACKED)
    ).values("pk", "platforms", "platform_results", "delivery_state")
    if receipt is not None and receipt.announcement_id is not None:
        legacy_rows = legacy_rows.filter(pk=receipt.announcement_id)
    platform_results_rows = 0
    legacy_untracked_rows = 0
    for legacy in legacy_rows.iterator(chunk_size=200):
        results = legacy["platform_results"]
        platforms = legacy["platforms"]
        if platform != "all" and platform not in (results or {}) and platform not in (platforms or ()):
            continue
        platform_results_rows += bool(results)
        legacy_untracked_rows += legacy["delivery_state"] == AnnouncementDeliveryState.LEGACY_UNTRACKED

    try:
        resolve("/api/v1/backstage/marketing/")
    except Resolver404:
        v1_api_present = False
    else:
        v1_api_present = True
    legacy_permission_present = Permission.objects.filter(
        content_type__app_label="shop",
        codename="manage_campaigns",
    ).exists()

    inventory = {
        "graph": {
            "approval_scope": "receipt" if receipt is not None else "global",
            "approved_without_complete_graph": approved_without_complete_graph,
            "binding_mismatch": graph_binding_mismatch,
            "checked_outboxes": len(rows),
        },
        "hash": {
            "checked_artifacts": len(artifacts),
            "mismatch": artifact_hash_mismatch,
        },
        "directive": directive_inventory,
        "aggregate": {
            "checked_announcements": len(announcements),
            "count_mismatch": aggregate_count_mismatch,
            "state_mismatch": aggregate_state_mismatch,
            "target_fanout_mismatch": target_fanout_mismatch,
        },
        "legacy": {
            "cleanup_status": "BLOCKED"
            if any(
                (
                    v1_api_present,
                    legacy_permission_present,
                    platform_results_rows,
                    legacy_untracked_rows,
                )
            )
            else "GO",
            "platform_results_rows": platform_results_rows,
            "untracked_rows": legacy_untracked_rows,
            "v1_api_present": v1_api_present,
            "wide_permission_present": legacy_permission_present,
        },
    }
    reason_counts = {
        "approved_without_complete_graph": approved_without_complete_graph,
        "graph_binding_mismatch": graph_binding_mismatch,
        "artifact_hash_mismatch": artifact_hash_mismatch,
        "directive_identity_mismatch": directive_inventory["identity_mismatch"],
        "dispatched_without_directive": directive_inventory["dispatched_without_directive"],
        "unlinked_existing_directive": directive_inventory["unlinked_existing"],
        "duplicate_directive_key": directive_inventory["duplicate_keys"],
        "aggregate_state_mismatch": aggregate_state_mismatch,
        "aggregate_count_mismatch": aggregate_count_mismatch,
        "target_fanout_mismatch": target_fanout_mismatch,
    }
    reasons = [reason for reason in _SHADOW_REASON_ORDER if reason_counts[reason]]
    legacy_reason_counts = {
        "legacy_v1_api_present": v1_api_present,
        "legacy_permission_present": legacy_permission_present,
        "legacy_platform_results_present": platform_results_rows,
        "legacy_untracked_present": legacy_untracked_rows,
    }
    inventory["legacy"]["reasons"] = [reason for reason in _LEGACY_REASON_ORDER if legacy_reason_counts[reason]]
    return {
        "status": "BLOCKED" if reasons else "GO",
        "reasons": reasons,
        "inventory": inventory,
    }


def _directive_inventory(rows: list, Directive) -> dict[str, int]:
    """Compare durable hand-offs using only technical, server-owned fields."""

    dispatch_pks = {directive_pk for row in rows if (directive_pk := _directive_pk(row.dispatch_ref)) is not None}
    query = Directive.objects.filter(dedupe_key__startswith="marketing-outbox:")
    if dispatch_pks:
        query = Directive.objects.filter(Q(dedupe_key__startswith="marketing-outbox:") | Q(pk__in=dispatch_pks))
    directives = list(query.only("pk", "topic", "payload", "dedupe_key").order_by("pk"))
    by_pk = {directive.pk: directive for directive in directives}
    by_key = defaultdict(list)
    for directive in directives:
        by_key[directive.dedupe_key].append(directive)

    wave_keys_by_command = defaultdict(list)
    for row in rows:
        if row.platform == "whatsapp":
            wave_keys_by_command[row.command_id].append(row.wave_key or "all")

    matched = 0
    identity_mismatch = 0
    dispatched_without_directive = 0
    unlinked_existing = 0
    duplicate_keys = 0
    for row in rows:
        key = f"marketing-outbox:{row.ref}"
        candidates = by_key.get(key, ())
        duplicate_keys += len(candidates) > 1
        if row.state == row.State.DISPATCHED:
            directive_pk = _directive_pk(row.dispatch_ref)
            directive = by_pk.get(directive_pk)
            if directive is None:
                dispatched_without_directive += 1
            elif directive.dedupe_key != key or not _directive_matches(
                row,
                directive,
                wave_keys=wave_keys_by_command[row.command_id],
            ):
                identity_mismatch += 1
            else:
                matched += 1
        elif candidates:
            directive = candidates[0]
            if _directive_matches(
                row,
                directive,
                wave_keys=wave_keys_by_command[row.command_id],
            ):
                unlinked_existing += 1
            else:
                identity_mismatch += 1

    return {
        "checked_outboxes": len(rows),
        "dispatched_without_directive": dispatched_without_directive,
        "duplicate_keys": duplicate_keys,
        "identity_mismatch": identity_mismatch,
        "matched": matched,
        "unlinked_existing": unlinked_existing,
    }


def _directive_matches(row, directive, *, wave_keys: list[str]) -> bool:
    from shopman.shop.directives import ANNOUNCEMENT_NOTIFY, ANNOUNCEMENT_PUBLISH

    expected = {
        "announcement_id": row.announcement_id,
        "artifact_hash": row.artifact.artifact_hash,
        "artifact_ref": str(row.artifact.ref),
        "content_version": row.artifact.version,
        "outbox_ref": str(row.ref),
        "platform": row.platform,
        "snapshot_ref": str(row.snapshot.ref),
    }
    if row.platform == "whatsapp":
        expected.update(
            {
                "wave": row.wave_key or "all",
                "wave_keys": wave_keys,
                "waves_expected": len(wave_keys),
            }
        )
    expected_topic = ANNOUNCEMENT_NOTIFY if row.platform == "whatsapp" else ANNOUNCEMENT_PUBLISH
    payload = directive.payload if isinstance(directive.payload, dict) else {}
    return directive.topic == expected_topic and all(payload.get(key) == value for key, value in expected.items())


def _directive_pk(dispatch_ref: str) -> int | None:
    prefix, separator, raw_pk = str(dispatch_ref or "").partition(":")
    if prefix != "directive" or not separator or not raw_pk.isdigit():
        return None
    return int(raw_pk)
