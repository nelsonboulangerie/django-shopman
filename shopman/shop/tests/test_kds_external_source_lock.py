"""External orders serialize kitchen dispatch without inventing checkout sessions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, transaction
from shopman.orderman.models import Order, Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.services import kds

LINES = [{"line_id": "external-1", "sku": "TEST", "name": "Item", "qty": 1, "meta": {}}]


@pytest.mark.django_db
@pytest.mark.parametrize("checkout_session", [False, True])
def test_lock_is_acquired_on_existing_source_before_creating_ticket(checkout_session):
    key = "source-lock"
    if checkout_session:
        Session.objects.create(session_key=key, channel_ref="web")
    else:
        Order.objects.create(ref="EXT-LOCK", channel_ref="ifood", session_key=key)
    KDSInstance.objects.create(ref="source-lock", name="Picking", type="picking")
    session_select = Session.objects.select_for_update
    order_select = Order.objects.select_for_update
    with patch.object(Session.objects, "select_for_update", wraps=session_select) as session_lock, patch.object(Order.objects, "select_for_update", wraps=order_select) as order_lock:
        tickets = kds.fire_lines(session_key=key, lines=LINES)
    session_lock.assert_called_once()
    assert order_lock.call_count == (0 if checkout_session else 1)
    assert len(tickets) == 1
    assert kds.fire_lines(session_key=key, lines=LINES) == []
    assert KDSTicket.objects.filter(session_key=key).count() == 1
    assert Session.objects.filter(session_key=key).exists() is checkout_session


@pytest.mark.django_db
def test_missing_source_is_rejected_without_creating_orphan_ticket():
    KDSInstance.objects.create(ref="missing-source", name="Picking", type="picking")
    with pytest.raises(ValueError, match="origem não encontrado"):
        kds.fire_lines(session_key="does-not-exist", lines=LINES)
    assert not KDSTicket.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_external_order_lock_blocks_concurrent_fire_before_ticket_ledger(monkeypatch):
    if not connection.features.has_select_for_update:
        pytest.skip("Requires database row locks (PostgreSQL); SQLite cannot prove blocking.")
    order = Order.objects.create(ref="EXT-CONCURRENT", channel_ref="ifood", session_key="ifood-lock-proof")
    entered_ledger = Event()
    started = Event()

    def ledger(**kwargs):
        entered_ledger.set()
        return []

    monkeypatch.setattr(kds, "_fire_lines_locked", ledger)

    def fire():
        close_old_connections()
        try:
            started.set()
            return kds.fire_lines(session_key=order.session_key, lines=LINES)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Order.objects.select_for_update().get(pk=order.pk)
            future = pool.submit(fire)
            assert started.wait(timeout=5)
            assert not entered_ledger.wait(timeout=0.2)
        assert future.result(timeout=5) == []
    assert entered_ledger.is_set()
