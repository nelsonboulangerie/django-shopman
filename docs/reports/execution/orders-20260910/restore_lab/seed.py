"""Synthetic boundary states; execute only through the loopback lab launcher."""
from unittest.mock import patch

from shopman.orderman.models import Directive, IdempotencyKey, Order

with patch("shopman.orderman.dispatch._on_commit_callback"):
    order, _ = Order.objects.get_or_create(ref="LAB-RESTORE-UNCERTAIN", defaults={
        "status": "ready", "total_q": 1500, "data": {"fulfillment_type": "pickup"},
    })
    for state in ("started", "unknown", "accepted"):
        Directive.objects.get_or_create(topic="notification.send", dedupe_key=f"LAB-RESTORE-{state}", defaults={
            "status": "failed" if state != "accepted" else "done", "attempts": 1,
            "payload": {"order_ref": order.ref, "template": "order_ready", "notification_delivery": {"status": state}},
        })
    IdempotencyKey.objects.get_or_create(scope="orders-lab-restore", key="in-progress", defaults={
        "status": "in_progress", "expires_at": None,
    })
    IdempotencyKey.objects.get_or_create(scope="orders-lab-restore", key="done", defaults={
        "status": "done", "expires_at": None, "response_code": 200,
        "response_body": {"contract": "local-mutation-v1", "fingerprint": "synthetic-proof", "result": {"outcome": "applied"}},
    })
print("Synthetic started/unknown/accepted and permanent in_progress/done seeded; no worker invoked.")
