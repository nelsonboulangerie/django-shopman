"""Real row-lock proof for post-deletion OrderEvent writes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.orderman.models import Order

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


class Worker:
    def __init__(self, command):
        self.command = command
        self.started = Event()
        self.pid = None

    def __call__(self):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                self.pid = cursor.fetchone()[0]
                cursor.execute("SET lock_timeout = '15s'")
            self.started.set()
            try:
                return self.command()
            except Exception as exc:
                return {"exception": type(exc).__name__, "code": getattr(exc, "code", "")}
        finally:
            connections.close_all()


def _assert_blocked_by(worker: Worker, blocker_pid: int) -> None:
    assert worker.started.wait(10)
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", [worker.pid])
            if blocker_pid in cursor.fetchone()[0]:
                return
        Event().wait(0.01)
    pytest.fail(f"backend {worker.pid} did not wait for backend {blocker_pid}")


def test_delete_first_makes_stale_personal_event_wait_then_fail_closed():
    order = Order.objects.create(
        ref="ORDER-EVENT-PRIVACY-PG",
        channel_ref="web",
        handle_type="phone",
        handle_ref="+5543999999999",
        status="completed",
    )
    stale = Order.objects.get(pk=order.pk)
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            Order.objects.filter(pk=locked.pk).update(
                handle_type="anonymized",
                handle_ref="ANON-order-event-pg",
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    def stale_write():
        return stale.emit_event(
            "operator_comment",
            actor="operator:test",
            payload={"note": "PII-MUST-NOT-RETURN"},
        )

    deletion = Worker(delete_subject)
    writer = Worker(stale_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        written = pool.submit(writer)
        try:
            _assert_blocked_by(writer, deletion.pid)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        write_result = written.result(20)

    assert write_result == {"exception": "ValidationError", "code": "order_anonymized"}
    assert not order.events.filter(type="operator_comment").exists()
