"""Read-only synthetic scoreboard from canonical tasks, receipts and reconciliation.

Fixed lab DB only. Does not run workers, repair data, persist a closing, or alert.
"""
import io
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
assert ROOT.name == "django-shopman-orders-execution-20260910"
sys.path[:0] = [str(ROOT), *[str(p) for p in sorted((ROOT / "packages").iterdir()) if p.is_dir()]]
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings_test", DATABASE_URL="postgres://orders_lab@127.0.0.1:55439/orders_lab", DATABASE_CONN_MAX_AGE="0", REDIS_URL="", SENTRY_DSN="")

import django

django.setup()

from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Count, Min, Sum
from django.utils import timezone
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation
from shopman.shop.management.commands.sweep_stuck_orders import Command as SweepCommand

assert connection.settings_dict["NAME"] == "orders_lab"
reconciliation_date = date.fromisoformat(sys.argv[1])
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    now = timezone.now()
    pending = IdempotencyKey.objects.filter(status="in_progress").aggregate(count=Count("id"), oldest=Min("created_at"))
    due = Directive.objects.filter(status="queued", available_at__lte=now).aggregate(count=Count("id"), oldest=Min("available_at"))
    task_states = dict(Directive.objects.values_list("status").annotate(count=Count("id")))
    receipt_states = dict(IdempotencyKey.objects.values_list("status").annotate(count=Count("id")))
    attempts = Directive.objects.aggregate(total=Sum("attempts"))["total"] or 0
    report = build_financial_reconciliation(reconciliation_date=reconciliation_date, require_closing=False)
    assert not report.persisted and not report.alert_created
    sweep = SweepCommand()
    call_command(sweep, dry_run=True, stdout=io.StringIO())
    result = {
        "cohort": "synthetic-lab-all-history", "as_of": now.isoformat(), "date": reconciliation_date.isoformat(),
        "database_read_only": True, "directive_states": task_states, "receipt_states": receipt_states,
        "recorded_task_attempts": attempts,
        "queued_due_tasks": due["count"],
        "incomplete_phases_canonical_dry_run": sweep._recovered,
        "phase_scan_minimum_minutes": 15,
        "oldest_due_task_seconds": (now - due["oldest"]).total_seconds() if due["oldest"] else None,
        "in_progress_receipts": pending["count"],
        "oldest_in_progress_receipt_seconds": (now - pending["oldest"]).total_seconds() if pending["oldest"] else None,
        "financial_issue_counts": dict(sorted(Counter(issue.code for issue in report.issues).items())),
        "financial_severity_counts": report.issue_counts, "cash_ledger": report.cash_ledger.as_dict(),
        "financial_orders": report.order_count, "financial_intents": report.intent_count,
        "financial_transactions": report.transaction_count,
        "scope": "All synthetic history on one date. Queued due tasks are canonical queue backlog, not proof of every due lifecycle effect. No repair or real reconciliation.",
        "unmeasured": ["effects_due_without_a_directive", "draft_restored_or_lost", "stale_refresh_or_discard", "field_recovery_time", "human_understanding"],
    }
print(json.dumps(result, indent=2))
