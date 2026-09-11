"""C08: recheck a subscription loaded before concurrent revocation commits."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection, transaction

from shopman.storefront.services import stock_alerts
from shopman.storefront.tests.test_concierge_commercial_races import Worker, assert_database_wait

pytestmark = pytest.mark.django_db(transaction=True)


def test_revocation_lock_wins_over_previously_loaded_notification(monkeypatch):
    assert connection.vendor == "postgresql"
    phone = "+5543999990001"
    sub = stock_alerts.subscribe("SYNTHETIC-CONSENT-RACE", phone=phone)
    original_proof = sub.evidence_hash
    locked, release = Event(), Event()
    sends = []
    monkeypatch.setattr(stock_alerts, "_deliver", lambda *a, **kw: sends.append(kw) or True)

    def revoke():
        with transaction.atomic():
            assert stock_alerts.revoke(sub.ref, sku=sub.sku, phone=phone)
            locked.set()
            assert release.wait(10)
        return True

    revoke_worker = Worker(revoke)
    send_worker = Worker(lambda: stock_alerts._deliver_group_if_still_active(
        [sub.pk], product_name="Pão sintético", event="stock_arrived", available_qty=1,
    ))
    with ThreadPoolExecutor(max_workers=2) as pool:
        revoked = pool.submit(revoke_worker)
        assert locked.wait(10)
        notification = pool.submit(send_worker)
        try:
            assert_database_wait(send_worker)
            assert revoke_worker.pid != send_worker.pid
        finally:
            release.set()
        assert revoked.result(timeout=15) is True
        assert notification.result(timeout=15) is False
    sub.refresh_from_db()
    assert sub.revoked_at is not None and sub.notified_at is None
    assert sub.evidence_hash == original_proof
    assert sub.revocation_evidence_hash
    assert sends == []
