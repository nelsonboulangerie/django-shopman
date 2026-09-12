"""C08: recheck a subscription loaded before concurrent revocation commits."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection, transaction

from shopman.shop.models import Channel
from shopman.storefront import stock_alert_delivery
from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence
from shopman.storefront.services import stock_alerts
from shopman.storefront.tests.test_concierge_commercial_races import Worker, assert_database_wait

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("phase", ["queued", "claimed"])
def test_revocation_lock_wins_over_previously_loaded_notification(monkeypatch, phase):
    assert connection.vendor == "postgresql"
    Channel.objects.create(ref="web", name="Web", is_active=True)
    phone = "+5543999990001"
    sub = stock_alerts.subscribe("SYNTHETIC-CONSENT-RACE", phone=phone)
    original_proof = sub.evidence_hash
    occurrence = StockAlertOccurrence.objects.create(
        sku=sub.sku, channel_ref=sub.channel_ref, event_type="stock_back",
        semantic_key="synthetic-consent-race", status="eligible", available_qty=1,
    )
    delivery = StockAlertDelivery.objects.create(
        subscription=sub, occurrence=occurrence, status=phase,
    )
    # Main now delivers one durable occurrence, not an in-memory subscriber group.
    # Both the initial claim and the provider boundary must reload revocation.
    boundary = stock_alert_delivery._claim if phase == "queued" else stock_alert_delivery._send_claimed
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
    send_worker = Worker(lambda: boundary(delivery.pk))
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
        assert notification.result(timeout=15) == "suppressed"
    sub.refresh_from_db()
    assert sub.revoked_at is not None and sub.notified_at is None
    assert sub.evidence_hash == original_proof
    assert sub.revocation_evidence_hash
    delivery.refresh_from_db()
    assert delivery.status == "suppressed"
    assert delivery.last_error_code == "subscription_cancelled"
    assert delivery.accepted_at is None and not delivery.provider_receipt_ref
    assert stock_alert_delivery._claim(delivery.pk) == "suppressed"
    assert stock_alert_delivery._send_claimed(delivery.pk) == "suppressed"
    assert sends == []
