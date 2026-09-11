"""Prepare/run only the fixed localhost synthetic database and HTTP port 8015.

Examples (original read-only Python environment): run_http_lab.py migrate;
run_http_lab.py seed 500; run_http_lab.py serve; run_http_lab.py measure 500.
No production URLs, account secrets, providers or real records are accepted.
"""
import json
import os
import platform
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
assert (ROOT / ".orders-lab").is_dir(), "Use the isolated execution worktree"
sys.path[:0] = [str(ROOT), *[str(p) for p in sorted((ROOT / "packages").iterdir()) if p.is_dir()]]
# Existing deploy guide: a direct PostgreSQL connection without a pool uses age 0.
os.environ["DATABASE_CONN_MAX_AGE"] = "0"
os.environ["DATABASE_URL"] = "postgres://orders_lab@127.0.0.1:55439/orders_perf_lab"
os.environ["REDIS_URL"] = "redis://127.0.0.1:56389/2"
os.environ["DJANGO_SETTINGS_MODULE"] = "http_lab_settings"
os.environ["SENTRY_DSN"] = ""


def setup():
    import django
    django.setup()
    from django.db import connection
    assert connection.settings_dict["NAME"] == "orders_perf_lab"
    from shopman.orderman import dispatch
    dispatch._on_commit_callback = lambda *args: None


def seed(n):
    from decimal import Decimal

    from django.contrib.auth.models import Permission, User
    from django.core.cache import cache
    from django.db import transaction
    from django.test import Client
    from shopman.orderman.models import Order, OrderEvent, OrderItem
    from shopman.payman.models import PaymentIntent, PaymentTransaction
    from shopman.stockman.models import Hold, HoldStatus

    from shopman.shop.models import Channel, Shop
    from shopman.shop.tests.test_waitlist_lifecycle import _planned_quant

    assert n in {1, 10, 100, 500}
    # This database is created only for this assay. Refuse foreign records.
    assert not Order.objects.exclude(ref__startswith="HTTP-LAB-").exists()
    assert not PaymentIntent.objects.exclude(ref__startswith="HTTP-PAY-").exists()
    with transaction.atomic():
        Order.objects.all().delete()
        Hold.objects.all().delete()
        # Payman history is immutable even in the lab; retain earlier fixtures.
    cache.clear()
    Shop.objects.get_or_create(name="Synthetic HTTP performance lab")
    Channel.objects.update_or_create(ref="http-lab", defaults={"name": "HTTP lab", "config": {"payment": {"timing": "external"}}})
    user, _ = User.objects.get_or_create(username="http-lab", defaults={"is_staff": True})
    user.set_password("synthetic-http-lab-only")
    user.save()
    user.user_permissions.set(Permission.objects.filter(content_type__app_label="shop", codename__in=["manage_orders", "manage_catalog"]))
    orders = Order.objects.bulk_create([
        Order(ref=f"HTTP-LAB-{n}-{i}", channel_ref="http-lab", status=["new", "accepted", "preparing", "ready", "dispatched"][i % 5], total_q=1500,
            data={"customer": {"name": f"Pessoa sintética {i}", "phone": ""}, "fulfillment_type": "delivery" if i % 2 else "pickup",
                "kitchen_note": "Contexto sintético", "assignment": {"operator_id": user.pk, "operator_name": "Lab"},
                "payment": {"method": "pix", "intent_ref": f"HTTP-PAY-{n}-{i}"},
                "courier": {"id_mch": f"HTTP-RIDE-{i}", "status": "A"} if i % 2 else {},
                "availability_decision": {"approved": True, "decisions": []}}) for i in range(n)])
    OrderItem.objects.bulk_create([OrderItem(order=o, line_id=str(i), sku=f"HTTP-BREAD-{i}", name=f"Pão sintético {i}", qty=Decimal("0.500"), unit_price_q=1000, line_total_q=500) for o in orders for i in range(3)])
    OrderEvent.objects.bulk_create([OrderEvent(order=o, seq=i, type="operator_comment", actor="lab", payload={"note": "Histórico sintético"}) for o in orders for i in range(1, 7)])
    for i, order in enumerate(orders):
        intent, _ = PaymentIntent.objects.get_or_create(ref=f"HTTP-PAY-{n}-{i}", defaults={"order_ref": order.ref, "method": "pix", "amount_q": 1500, "status": "captured"})
        PaymentTransaction.objects.get_or_create(intent=intent, type="capture", defaults={"amount_q": 1500})
    quant = _planned_quant(str(n * 3))
    Hold.objects.bulk_create([Hold(sku="PAO-DE-FILA", quant=quant, target_date=quant.target_date, quantity=Decimal("1"), status=HoldStatus.PENDING, metadata={"reference": f"order:{o.ref}", "planned": True}) for o in orders])
    client = Client()
    client.force_login(user)
    auth = ROOT / ".orders-lab/http-lab-auth.json"
    auth.write_text(json.dumps({"cookies": {key: value.value for key, value in client.cookies.items()}}))
    auth.chmod(0o600)
    print(json.dumps({"seeded": n, "database": "orders_perf_lab", "remote_effects": False}))


def measure(n, port=8015):
    assert port in {8015, 3005}
    import psutil
    import requests

    cookies = json.loads((ROOT / ".orders-lab/http-lab-auth.json").read_text())["cookies"]
    def once(path):
        start = time.perf_counter()
        response = requests.get(f"http://127.0.0.1:{port}" + path, cookies=cookies, timeout=60)
        elapsed = (time.perf_counter() - start) * 1000
        assert response.status_code == 200, response.status_code
        body = response.json()
        if "queue" in body:
            assert body["queue"]["total_count"] == n, body["queue"]["total_count"]
        return {"http_ms": elapsed, "backend_ms": float(response.headers["X-Lab-Backend-Ms"]) if "X-Lab-Backend-Ms" in response.headers else None,
            "process_cpu_window_ms": float(response.headers["X-Lab-Cpu-Ms"]) if "X-Lab-Cpu-Ms" in response.headers else None, "queries": int(response.headers["X-Lab-Queries"]) if "X-Lab-Queries" in response.headers else None,
            "hold_queries": int(response.headers["X-Lab-Hold-Queries"]) if "X-Lab-Hold-Queries" in response.headers else None, "rss_bytes": int(response.headers["X-Lab-Rss-Bytes"]) if "X-Lab-Rss-Bytes" in response.headers else None, "bytes": len(response.content)}
    observations = {}
    for kind, path in (("queue", "/api/v1/backstage/orders/"), ("detail", f"/api/v1/backstage/orders/HTTP-LAB-{n}-0/")):
        cold = once(path)
        for clients in (1, 2, 10):
            with ThreadPoolExecutor(max_workers=clients) as pool:
                values = list(pool.map(lambda _, path=path: once(path), range(20)))
            observations[f"{kind}_{clients}"] = {"first_request": cold, "samples": values,
                "http_p50_ms": statistics.median(v["http_ms"] for v in values),
                "http_p95_ms": sorted(v["http_ms"] for v in values)[18],
                "backend_p95_ms": sorted(v["backend_ms"] for v in values)[18] if port == 8015 else None}
    result = {"n": n, "platform": platform.platform(), "logical_cpus": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total,
        "transport": "HTTP to one Daphne process, localhost PostgreSQL/Redis, no renderer", "via_bff": port == 3005, "observations": observations}
    (ROOT / f".orders-lab/http-read-{n}-{port}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"n": n, "summary": {key: {k: v for k, v in value.items() if k in {"http_p50_ms", "http_p95_ms", "backend_p95_ms"}} for key, value in observations.items()}}))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "serve":
        from daphne.cli import CommandLineInterface
        CommandLineInterface().run(["-b", "127.0.0.1", "-p", "8015", "--access-log", "/dev/null", "config.asgi:application"])
    else:
        setup()
        if mode == "migrate":
            from django.core.management import call_command
            call_command("migrate", interactive=False, verbosity=0)
        elif mode == "seed":
            seed(int(sys.argv[2]))
        elif mode == "measure":
            measure(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 8015)
        else:
            raise ValueError("Unknown lab command")
