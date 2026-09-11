"""Read-only summary of existing structured operational logs, without refs/PII."""
import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OUTCOMES = {"applied", "not_applied", "unknown", "in_progress", "transport_unknown", "read", "unclassified"}
OPERATIONS = {
    "CatalogAiAssistView",
    "CatalogBulkPriceView",
    "CatalogBulkView",
    "CatalogCellView",
    "CatalogMatrixView",
    "CatalogProductDetailView",
    "CatalogProductView",
    "CatalogPromiseView",
    "CatalogReorderCollectionsView",
    "CatalogReorderItemsView",
    "CatalogResyncView",
    "CatalogSocialView",
    "CatalogSyncStatusView",
    "FeedActiveView",
    "FeedBoardView",
    "FeedCollectionsView",
    "FeedRotationView",
    "OperatorLockView",
    "OperatorLoginView",
    "OperatorSessionView",
    "OperatorUnlockView",
    "OrderAdvanceView",
    "OrderAssignView",
    "OrderCancelView",
    "OrderCancellationReasonsView",
    "OrderCommentView",
    "OrderConfirmView",
    "OrderCourierCancelView",
    "OrderCourierDispatchView",
    "OrderCourierQuoteView",
    "OrderDetailView",
    "OrderEquipmentBackView",
    "OrderNotesView",
    "OrderQueueView",
    "OrderRejectView",
    "OrderRequeueFiscalView",
    "OrderResendPaymentLinkView",
    "OrderSettleDeliveryCashView",
    "OrderTicketBatchEscposView",
    "OrderTicketBatchView",
    "OrderTicketEscposView",
    "OrderUnassignView",
    "ProductPromiseView",
}
METHODS = {"GET", "POST", "PATCH", "PUT", "DELETE"}
STATES = {"started", "unknown", "accepted", "skipped", "failed", "not_applied"}


def distribution(samples):
    ordered = sorted(samples)
    if not ordered:
        return None
    return {"n": len(ordered), "p50": ordered[math.ceil(len(ordered) * .5) - 1],
            "p95": ordered[math.ceil(len(ordered) * .95) - 1], "max": ordered[-1]}


def summarize(lines):
    counters = Counter()
    latency = defaultdict(list)
    effects = {}
    applications = {}
    receipt_intervals = []
    last_time = None
    for line in lines:
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            counters["non_json_lines"] += 1
            continue
        if not isinstance(row, dict) or not str(row.get("event", "")).startswith("operator."):
            continue
        try:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            counters["events_without_timestamp"] += 1
            continue
        last_time = max(last_time, timestamp) if last_time else timestamp
        event = row["event"]
        outcome = row.get("outcome") if row.get("outcome") in OUTCOMES else "unclassified"
        method = row.get("method") if row.get("method") in METHODS else "other"
        if event == "operator.request.finished":
            counters[f"request.{method}.{outcome}"] += 1
            status = row.get("response_status")
            bucket = str(status) if status in {401, 403, 409, 422, 500, 503} else "other"
            counters[f"status.{bucket}"] += 1
            operation = row.get("operation") if row.get("operation") in OPERATIONS else "other"
            counters[f"endpoint.{operation}.{method}.{bucket}"] += 1
            counters[f"trace.{('present' if row.get('request_id') else 'missing')}"] += 1
            value = row.get("view_elapsed_ms")
            if isinstance(value, int | float) and math.isfinite(value) and value >= 0:
                latency[method].append(value)
        elif event == "operator.command.local_result":
            counters[f"command.{('replayed' if row.get('replayed') else outcome)}"] += 1
            if outcome == "applied" and not row.get("replayed") and row.get("intention_digest"):
                applications[row["intention_digest"]] = timestamp
        elif event == "operator.command.receipt":
            counters[f"receipt.{outcome}"] += 1
            previous = applications.get(row.get("intention_digest"))
            if previous and timestamp >= previous:
                receipt_intervals.append((timestamp - previous).total_seconds() * 1000)
        elif event == "operator.command.blocked":
            reason = row.get("reason")
            counters[f"command.{reason if reason in {'RemoteMutationConflict', 'RemoteMutationInProgress'} else 'blocked'}"] += 1
        elif event == "operator.effect.state" and row.get("effect_state") in STATES:
            counters[f"effect.{row['effect_state']}"] += 1
            if isinstance(row.get("directive_id"), int):
                effects[row["directive_id"]] = (row["effect_state"], timestamp)
        elif event == "operator.cash.settled":
            counters["cash.settled"] += 1
    pending = [(state, timestamp) for state, timestamp in effects.values() if state in {"started", "unknown", "failed", "not_applied"}]
    return {"counters": dict(sorted(counters.items())),
        "view_elapsed_ms_excludes_render_and_network": {key: distribution(values) for key, values in sorted(latency.items())},
        "server_receipt_read_after_apply_ms": distribution(receipt_intervals),
        "last_observed_unresolved_effects": len(pending) if effects else None,
        "last_observed_pending_age_seconds": distribution([(last_time - timestamp).total_seconds() for _, timestamp in pending]) if last_time else None,
        "unmeasured": ["canonical_due_effect_backlog", "ledger_mismatch", "draft_restored_or_lost",
                       "stale_refresh_or_discard", "screen_reader_understanding", "field_recovery_activations_or_time"],
        "scope": "Recorded events only; missing families are unmeasured, not zero. No refs or entered text exported."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    with args.log.open() as source:
        result = summarize(source)
    print(json.dumps({"cohort": args.cohort, "version": args.version, **result}, indent=2))


if __name__ == "__main__":
    main()
