"""Late phase crash witnesses; provider/physical work adapters are isolated."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop import lifecycle
from shopman.shop.directives import ORDER_LIFECYCLE_PHASE

pytestmark = pytest.mark.django_db


def test_transition_and_phase_enqueue_are_atomic():
    order = Order.objects.create(ref="ATOMIC-PHASE", status="accepted")
    with patch("shopman.shop.directives.create_persistently_deduped", side_effect=RuntimeError("enqueue failed")):
        with pytest.raises(RuntimeError, match="enqueue failed"):
            order.transition_status("preparing")
    order.refresh_from_db()
    assert order.status == "accepted"
    assert not order.events.exists()
    assert not Directive.objects.filter(topic=ORDER_LIFECYCLE_PHASE).exists()


def test_post_commit_callback_loss_leaves_phase_for_worker():
    order = Order.objects.create(ref="LOST-CALLBACK", status="accepted")
    order.transition_status("preparing")  # callbacks are deliberately not run in this transaction
    task = Directive.objects.get(topic=ORDER_LIFECYCLE_PHASE)
    assert task.status == "queued"
    assert not lifecycle.phase_complete(order, "on_preparing")
    with patch.dict(lifecycle._PHASE_HANDLERS, {"on_preparing": lambda *_: None}):
        _process_directive(task)
    order.refresh_from_db()
    task.refresh_from_db()
    assert lifecycle.phase_complete(order, "on_preparing")
    assert task.status == "done"


@pytest.mark.parametrize("phase", sorted(lifecycle.QUEUED_PHASES))
def test_historical_late_phase_without_marker_never_authorizes_recovery(phase):
    order = Order.objects.create(ref=f"HISTORICAL-{phase}", status=phase.removeprefix("on_"), data={"returns": [{"type": "total"}]} if phase == "on_returned" else {})
    Order.objects.filter(pk=order.pk).update(updated_at=timezone.now() - timedelta(minutes=30))
    with patch.object(lifecycle, "dispatch") as dispatch, patch.object(lifecycle, "enqueue_phase") as enqueue:
        call_command("sweep_stuck_orders", dry_run=True)
        call_command("sweep_stuck_orders")
    dispatch.assert_not_called()
    enqueue.assert_not_called()
    assert not Directive.objects.exists()
    order.refresh_from_db()
    assert not lifecycle.phase_complete(order, phase)


def test_marker_failure_is_retryable_and_does_not_repeat_original_notice():
    order = Order.objects.create(ref="MARKER-FAULT", status="dispatched", total_q=500)
    task = lifecycle.enqueue_phase(order, "on_dispatched")
    with patch.object(lifecycle, "_mark_phase_complete", side_effect=RuntimeError("marker lost")):
        _process_directive(task)
    task.refresh_from_db()
    assert task.status == "queued"
    assert not lifecycle.phase_complete(order, "on_dispatched")
    before = Directive.objects.filter(topic="notification.send").count()
    assert before == 0  # local enqueue rolled back with the failed marker
    _process_directive(task)
    task.refresh_from_db()
    assert task.status == "done"
    assert Directive.objects.filter(topic="notification.send").count() == 1
    assert IdempotencyKey.objects.filter(scope="lifecycle:phase").count() == 1


def test_obsolete_preparation_is_visible_and_never_restarts_work():
    order = Order.objects.create(ref="OBSOLETE-PHASE", status="cancelled")
    task = lifecycle.enqueue_phase(order, "on_preparing")
    with patch.object(lifecycle, "_dispatch_physical_work") as physical, patch("shopman.shop.handlers.lifecycle_phase.create_operator_alert") as alert:
        _process_directive(task)
    task.refresh_from_db()
    assert task.status == "failed"
    physical.assert_not_called()
    alert.assert_called_once()
    order.refresh_from_db()
    assert not lifecycle.phase_complete(order, "on_preparing")


def test_phase_receipt_rolls_back_with_task():
    order = Order.objects.create(ref="ROLLBACK-PHASE", status="ready")
    with pytest.raises(RuntimeError), transaction.atomic():
        lifecycle.enqueue_phase(order, "on_ready")
        raise RuntimeError("abort transaction")
    assert not Directive.objects.filter(topic=ORDER_LIFECYCLE_PHASE).exists()
    assert not IdempotencyKey.objects.filter(scope="lifecycle:phase").exists()


@pytest.mark.django_db(transaction=True)
def test_two_worker_claims_of_same_phase_create_one_fulfillment():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connection, connections
    from shopman.orderman.models import Fulfillment

    if connection.vendor != "postgresql":
        pytest.skip("Independent PostgreSQL connections required")
    order = Order.objects.create(ref="TWO-PHASE-WORKERS", status="ready")
    with patch("shopman.orderman.dispatch._on_commit_callback"):
        tasks = [Directive.objects.create(topic=ORDER_LIFECYCLE_PHASE, payload={"order_ref": order.ref, "phase": "on_ready"}) for _ in range(2)]
    barrier = Barrier(2)

    def process(pk):
        try:
            task = Directive.objects.get(pk=pk)
            barrier.wait(timeout=5)
            _process_directive(task)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(process, [task.pk for task in tasks]))
    assert Fulfillment.objects.filter(order=order).count() == 1
    assert Directive.objects.filter(pk__in=[task.pk for task in tasks], status="done").count() == 2
    assert Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref).count() == 1


def test_receipt_save_failure_after_phase_commit_does_not_repeat_effect():
    order = Order.objects.create(ref="PHASE-RECEIPT-LOSS", status="ready")
    task = lifecycle.enqueue_phase(order, "on_ready")
    original = Directive.save
    failed = False

    def save(instance, *args, **kwargs):
        nonlocal failed
        if instance.pk == task.pk and instance.status == "done" and not failed:
            failed = True
            raise RuntimeError("worker result lost")
        return original(instance, *args, **kwargs)

    with patch.object(Directive, "save", save):
        _process_directive(task)
    order.refresh_from_db()
    task.refresh_from_db()
    assert task.status == "queued"
    assert lifecycle.phase_complete(order, "on_ready")
    _process_directive(task)
    assert order.fulfillments.count() == 1
    task.refresh_from_db()
    assert task.status == "done"
