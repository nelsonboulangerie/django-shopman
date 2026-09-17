"""Real row-lock proof for POS cancellation racing KDS writers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.services import kds

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


@pytest.mark.parametrize(
    ("status", "command", "expected"),
    [
        ("pending", "start", False),
        ("pending", "complete", False),
        ("pending", "ack", True),
    ],
)
def test_pos_cancel_and_kds_writer_share_source_then_ticket_order(
    monkeypatch, status, command, expected
):
    source = Session.objects.create(
        session_key=f"kds-lock-{command}",
        channel_ref="pdv",
        state="open",
    )
    station = KDSInstance.objects.create(
        ref=f"kds-lock-{command}",
        name="Preparo",
        type="prep",
    )
    ticket = KDSTicket.objects.create(
        session_key=source.session_key,
        kds_instance=station,
        status=status,
        items=[{
            "line_id": "linha-1",
            "sku": "PAO",
            "name": "Pão",
            "qty": 1,
        }],
    )

    worker_started = Event()
    ticket_locked = Event()
    real_locked_ticket = kds._lock_ticket_after_source

    def observed_ticket_lock(current):
        locked = real_locked_ticket(current)
        ticket_locked.set()
        return locked

    monkeypatch.setattr(kds, "_lock_ticket_after_source", observed_ticket_lock)

    def mutate_from_kds():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            current = KDSTicket.objects.get(pk=ticket.pk)
            worker_started.set()
            if command == "start":
                return kds.start_ticket(current, actor="kds:test")
            if command == "complete":
                return kds.complete_ticket(current, actor="kds:test")
            return kds.acknowledge_ticket(current, actor="kds:test")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=source.pk)
            future = pool.submit(mutate_from_kds)
            assert worker_started.wait(timeout=5)

            # The KDS connection must be waiting on Session, not holding the
            # KDSTicket while it waits. That is the deadlock discriminator.
            assert not ticket_locked.wait(timeout=0.2)
            kds.unfire_lines(session_key=source.session_key, line_ids=["linha-1"])

        assert future.result(timeout=5) is expected

    assert ticket_locked.is_set()
