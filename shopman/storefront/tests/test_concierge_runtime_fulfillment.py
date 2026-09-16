"""H12: efeitos locais de fulfillment e retry pela Directive canônica."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive, Fulfillment, Order

from shopman.shop.handlers.fulfillment import FulfillmentUpdateHandler
from shopman.shop.services import fulfillment

pytestmark = pytest.mark.django_db(transaction=True)


def make_order():
    return Order.objects.create(ref="H12-ORDER", channel_ref="web", session_key="h12-session", status="ready", data={"fulfillment_type": "delivery"})


def queue(topic, **payload):
    return Directive.objects.create(topic=topic, payload=payload, available_at=timezone.now()+timedelta(hours=1))


def test_h12_create_crash_rolls_back_record_and_retry_creates_once(monkeypatch):
    order = make_order()
    work = queue("fulfillment.create", order_ref=order.ref)
    original = Order.save
    def fail_marker(self, *args, **kwargs):
        if self.data.get("fulfillment_created"):
            raise RuntimeError("synthetic marker write failure")
        return original(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Order, "save", fail_marker)
        _process_directive(work)
    work.refresh_from_db()
    order.refresh_from_db()
    assert work.status == "queued"
    assert not order.data.get("fulfillment_created")
    assert not Fulfillment.objects.filter(order=order).exists()
    _process_directive(work)
    work.refresh_from_db()
    order.refresh_from_db()
    assert work.status == "done"
    assert order.data["fulfillment_created"] is True
    assert Fulfillment.objects.filter(order=order).count() == 1


def test_h12_update_crash_does_not_skip_sync_and_notification_on_retry(monkeypatch):
    order = make_order()
    record = Fulfillment.objects.create(order=order, status="in_progress")
    work = queue("fulfillment.update", order_ref=order.ref, fulfillment_id=record.pk, new_status="dispatched")
    def fail(*args):
        raise RuntimeError("synthetic sync boundary failure")
    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentUpdateHandler, "_sync_order_status", fail)
        _process_directive(work)
    record.refresh_from_db()
    order.refresh_from_db()
    work.refresh_from_db()
    assert work.status == "queued"
    assert record.status == "in_progress"
    assert order.status == "ready"
    _process_directive(work)
    record.refresh_from_db()
    order.refresh_from_db()
    work.refresh_from_db()
    assert work.status == "done"
    assert record.status == "dispatched"
    assert order.status == "dispatched"
    assert Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref, payload__template="order_dispatched").count() == 1


def test_h12_concurrent_creation_has_one_fulfillment():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required for independent row locks")
    order = make_order()
    barrier = Barrier(2)
    def create_one():
        try:
            snapshot = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=10)
            fulfillment.create(snapshot)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(create_one) for _ in range(2)]
        for job in jobs:
            job.result(timeout=20)
    order.refresh_from_db()
    assert order.data["fulfillment_created"] is True
    assert Fulfillment.objects.filter(order=order).count() == 1


def test_h12_notification_failure_rolls_back_order_sync_and_events(monkeypatch):
    order = make_order()
    record = Fulfillment.objects.create(order=order, status="in_progress")
    work = queue("fulfillment.update", order_ref=order.ref, fulfillment_id=record.pk, new_status="dispatched")
    def fail(*args):
        raise RuntimeError("synthetic notification scheduling failure")
    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentUpdateHandler, "_create_notifications", fail)
        _process_directive(work)
    record.refresh_from_db()
    order.refresh_from_db()
    assert record.status == "in_progress"
    assert order.status == "ready"
    assert not Directive.objects.filter(topic="order.lifecycle_phase", payload__order_ref=order.ref).exists()
    assert not order.events.filter(type="status_changed").exists()
    _process_directive(work)
    order.refresh_from_db()
    assert order.status == "dispatched"
    assert order.events.filter(type="status_changed").count() == 1


def test_h12_adopts_existing_record_when_marker_is_missing():
    order = make_order()
    record = Fulfillment.objects.create(order=order)
    assert fulfillment.create(order).pk == record.pk
    assert Fulfillment.objects.filter(order=order).count() == 1
    order.refresh_from_db()
    assert order.data["fulfillment_created"] is True


def test_h12_concurrent_updates_create_one_transition_and_notification():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required for independent row locks")
    order = make_order()
    record = Fulfillment.objects.create(order=order, status="in_progress")
    jobs = [queue("fulfillment.update", order_ref=order.ref, fulfillment_id=record.pk, new_status="dispatched") for _ in range(2)]
    barrier = Barrier(2)
    def update_one(pk):
        try:
            message = Directive.objects.get(pk=pk)
            barrier.wait(timeout=10)
            _process_directive(message)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update_one, job.pk) for job in jobs]
        for future in futures:
            future.result(timeout=20)
    order.refresh_from_db()
    record.refresh_from_db()
    assert order.status == record.status == "dispatched"
    assert order.events.filter(type="status_changed").count() == 1
    assert Directive.objects.filter(pk__in=[job.pk for job in jobs], status="done").count() == 2
    assert Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref, payload__template="order_dispatched").count() == 1
