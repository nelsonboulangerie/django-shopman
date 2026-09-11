"""Current/previous-code probe against the restored synthetic database only."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

checkout = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
database = sys.argv[3] if len(sys.argv) > 3 else "orders_restore_lab"
assert database in {"orders_restore_lab", "orders_restore_lab_stock"}
assert checkout.name in {"django-shopman-orders-execution-20260910", "orders-audit-base-5a3383c9"}
assert mode in {"current", "previous"}
sys.path[:0] = [str(checkout), *[str(path) for path in sorted((checkout / "packages").iterdir()) if path.is_dir()]]
os.environ.update(DJANGO_SETTINGS_MODULE="config.settings_test",
    DATABASE_URL=f"postgres://orders_lab@127.0.0.1:55439/{database}", REDIS_URL="", DATABASE_CONN_MAX_AGE="0")
import django

django.setup()
from django.db import transaction
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop.handlers.notification import NotificationSendHandler

order = Order.objects.get(ref="LAB-RESTORE-UNCERTAIN")
keys = IdempotencyKey.objects.filter(scope="orders-lab-restore")
assert keys.count() == 2
assert keys.filter(expires_at__isnull=True).count() == 2
assert keys.get(key="done").response_body["result"]["outcome"] == "applied"
unknown = Directive.objects.get(dedupe_key="LAB-RESTORE-unknown")
assert unknown.payload["notification_delivery"]["status"] == "unknown"
external = Mock(return_value=(True, None))
with transaction.atomic(), patch("shopman.shop.handlers.notification.notification_svc.deliver_order_notification", external):
    if mode == "current":
        try:
            NotificationSendHandler().handle(message=unknown, ctx={})
        except DirectiveTerminalError:
            pass
        else:
            raise AssertionError("Current worker did not fence unknown")
    else:
        NotificationSendHandler().handle(message=unknown, ctx={})
    transaction.set_rollback(True)
assert external.call_count == (0 if mode == "current" else 1)
if mode == "current":
    from shopman.shop.services.remote_mutations import RemoteMutationInProgress, lookup_local_mutation
    receipt = lookup_local_mutation(scope="orders-lab-restore", key="done", fingerprint="synthetic-proof")
    assert receipt.replayed and receipt.response_body == {"outcome": "applied"}
    try:
        lookup_local_mutation(scope="orders-lab-restore", key="in-progress")
    except RemoteMutationInProgress:
        pass
    else:
        raise AssertionError("Pending key was lost or treated as permission")
if database == "orders_restore_lab_stock":
    from decimal import Decimal

    from django.db.models import Sum
    from shopman.stockman.models import Move, Quant

    quant = Quant.objects.get(sku="LAB-RESTORE-STOCK")
    assert quant._quantity == Decimal("2.000")
    assert Move.objects.filter(quant=quant).aggregate(total=Sum("delta"))["total"] == quant._quantity
    assert Move.objects.filter(quant=quant, delta=Decimal("-0.500")).count() == 1
print(json.dumps({"mode": mode, "database": database, "old_schema_reads_new_json": True,
    "synthetic_remote_calls": external.call_count, "unknown_safe_to_consume": mode == "current",
    "all_probe_writes_rolled_back": True}))
