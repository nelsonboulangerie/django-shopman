"""Actual process exit after a synthetic provider acceptance; loopback DB only."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LAB = ROOT / ".orders-lab"
DB = "orders_notification_crash_lab_v2"
JOURNAL = LAB / "notification-provider-journal-v2.jsonl"
os.environ.update(DATABASE_URL=f"postgres://orders_lab@127.0.0.1:55439/{DB}",
    REDIS_URL="", DATABASE_CONN_MAX_AGE="0", DJANGO_SETTINGS_MODULE="config.settings_test", SHOPMAN_JSON_LOGS="1")


def parent():
    import psycopg
    from psycopg import sql

    assert not JOURNAL.exists(), "Refuse to overwrite prior synthetic provider evidence"
    with psycopg.connect(host="127.0.0.1", port=55439, user="orders_lab", dbname="postgres", autocommit=True) as conn:
        assert not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB,)).fetchone()
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER orders_lab").format(sql.Identifier(DB)))
    command = [sys.executable, str(Path(__file__).resolve())]
    subprocess.run([*command, "setup"], check=True, cwd=ROOT)
    crashed = subprocess.run([*command, "crash"], cwd=ROOT)
    assert crashed.returncode == 17, crashed.returncode
    subprocess.run([*command, "recover"], check=True, cwd=ROOT)
    print("Actual os._exit(17), fresh-process reaper and worker replay completed; one synthetic acceptance.")


def child(mode):
    from datetime import timedelta
    from unittest.mock import patch

    sys.path[:0] = [str(ROOT), *[str(path) for path in sorted((ROOT / "packages").iterdir()) if path.is_dir()]]
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.utils import timezone
    from shopman.orderman.dispatch import _process_directive
    from shopman.orderman.management.commands.process_directives import _reap_stuck_directives
    from shopman.orderman.models import Directive, Order

    from shopman.shop.models import Shop

    if mode == "setup":
        call_command("migrate", interactive=False, verbosity=0)
        Shop.objects.create(name="Synthetic process crash lab")
        with patch("shopman.orderman.dispatch._on_commit_callback"):
            order = Order.objects.create(ref="LAB-NOTICE-PROCESS", status="ready", total_q=500,
                data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
            Directive.objects.create(topic="notification.send", dedupe_key="LAB-NOTICE-PROCESS",
                payload={"order_ref": order.ref, "template": "order_ready"})
        return
    task = Directive.objects.get(dedupe_key="LAB-NOTICE-PROCESS")
    before = {"status": task.status, "attempts": task.attempts, "delivery": task.payload.get("notification_delivery")}
    def provider(*args):
        assert not connection.in_atomic_block
        with JOURNAL.open("a") as journal:
            journal.write(json.dumps({"accepted": True, "remote_id": "synthetic-remote-one"}) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        os._exit(17)
    with patch("shopman.shop.handlers.notification.notification_svc.deliver_order_notification", provider):
        if mode == "recover":
            assert before["status"] == "running" and before["delivery"]["status"] == "started"
            future = timezone.now() + timedelta(minutes=10)
            with patch("shopman.orderman.management.commands.process_directives.timezone.now", return_value=future):
                assert _reap_stuck_directives(timeout_minutes=5, max_attempts=5) == 1
                task.refresh_from_db()
                _process_directive(task)
        else:
            _process_directive(task)
    assert mode == "recover", "Crash injection was not reached"
    task.refresh_from_db()
    accepted = JOURNAL.read_text().splitlines()
    assert len(accepted) == 1
    assert task.status == "failed" and task.attempts == 2
    assert task.payload["notification_delivery"]["status"] == "started"
    from shopman.backstage.models import OperatorAlert
    alerts = OperatorAlert.objects.filter(type="notification_failed", order_ref="LAB-NOTICE-PROCESS")
    assert alerts.count() == 1
    assert "não confirmado" in alerts.get().message
    assert "5 tentativas" not in alerts.get().message
    report = {"exit_code": 17, "fresh_process": True, "canonical_reaper": True, "clock_advanced_minutes": 10,
        "before_recovery": before, "after_recovery": {"status": task.status, "attempts": task.attempts},
        "synthetic_external_acceptances": len(accepted), "blind_retries": 0, "existing_operational_alerts": alerts.count()}
    (LAB / "notification-process-crash-v2.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        parent()
    else:
        assert sys.argv[1] in {"setup", "crash", "recover"}
        child(sys.argv[1])
