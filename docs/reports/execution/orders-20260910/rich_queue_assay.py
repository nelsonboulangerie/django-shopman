"""Synthetic rich PostgreSQL read assay; no remote/physical effects or real records."""
import json
import platform
import re
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from shopman.orderman.models import Order, OrderEvent, OrderItem
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.stockman.models import Hold, HoldStatus

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.order_queue import build_two_zone_queue
from shopman.shop.models import Channel, Shop
from shopman.shop.tests.test_waitlist_lifecycle import _planned_quant


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("n", [1, 10, 100, 500])
def test_rich_queue(n):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL independent read connections required")
    Shop.objects.create(name="Synthetic orders load lab")
    Channel.objects.create(ref="web", name="Lab", config={"payment": {"timing": "external"}})
    user = User.objects.create_user(username="load-reader", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    user.has_perm("shop.manage_orders")
    orders = Order.objects.bulk_create([
        Order(ref=f"RICH-{n}-{i}", channel_ref="web", status=["new", "accepted", "preparing", "ready", "dispatched"][i % 5], total_q=1500,
            data={"customer": {"name": f"Pessoa sintética {i}", "phone": ""},
                "fulfillment_type": "delivery" if i % 2 else "pickup",
                "kitchen_note": "Preservar contexto sintético sem redigitação.",
                "assignment": {"operator_id": user.pk, "operator_name": "Lab"},
                "payment": {"method": "pix", "intent_ref": f"RICH-PAY-{n}-{i}"},
                "courier": {"id_mch": f"SYNTHETIC-RIDE-{i}", "status": "A"} if i % 2 else {},
                "availability_decision": {"approved": True, "decisions": []}})
        for i in range(n)
    ])
    OrderItem.objects.bulk_create([
        OrderItem(order=order, line_id=str(line), sku=f"PAO-{line}", name=f"Pão sintético {line}", qty=Decimal("0.500"), unit_price_q=1000, line_total_q=500)
        for order in orders for line in range(3)
    ])
    OrderEvent.objects.bulk_create([
        OrderEvent(order=order, seq=seq, type="operator_comment", actor="lab", payload={"note": "Histórico sintético"})
        for order in orders for seq in range(1, 7)
    ])
    intents = PaymentIntent.objects.bulk_create([
        PaymentIntent(ref=f"RICH-PAY-{n}-{i}", order_ref=order.ref, method="pix", amount_q=1500, status="captured")
        for i, order in enumerate(orders)
    ])
    PaymentTransaction.objects.bulk_create([
        PaymentTransaction(intent=intent, type="capture", amount_q=1500) for intent in intents
    ])
    quant = _planned_quant(str(n * 3))
    Hold.objects.bulk_create([
        Hold(sku="PAO-DE-FILA", quant=quant, target_date=quant.target_date, quantity=Decimal("1"), status=HoldStatus.PENDING,
            metadata={"reference": f"order:{order.ref}", "planned": True}) for order in orders
    ])

    def read_once(_=None):
        start = time.perf_counter()
        with CaptureQueriesContext(connection) as queries:
            body = json.dumps(projection_data(build_two_zone_queue(user=user))).encode()
        return {"ms": (time.perf_counter() - start) * 1000, "queries": len(queries), "bytes": len(body),
            "payman_queries": sum("payman_" in q["sql"] for q in queries),
            "hold_queries": sum("stockman_hold" in q["sql"] for q in queries),
            "tables": dict(Counter(match.group(1) for q in queries if (match := re.search(r'FROM "([^" ]+)"', q["sql"]))))}

    first = read_once()
    results = [read_once() for _ in range(20)]
    observations = {"single": results}
    if n == 500:
        def worker(samples):
            try:
                return [read_once() for _ in range(samples)]
            finally:
                connections.close_all()
        for clients in (2, 10):
            with ThreadPoolExecutor(max_workers=clients) as pool:
                observations[f"clients_{clients}"] = [item for group in pool.map(worker, [20 // clients] * clients) for item in group]
    print("RICH_QUEUE=" + json.dumps({"n": n, "platform": platform.platform(), "database": connection.vendor,
        "transport": "projection+JSON (not HTTP)", "first_read": first,
        "results": {key: {"samples": values, "p50_ms": statistics.median(v["ms"] for v in values),
            "p95_ms": sorted(v["ms"] for v in values)[18]} for key, values in observations.items()}}))
