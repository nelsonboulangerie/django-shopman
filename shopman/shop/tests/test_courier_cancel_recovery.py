"""Synthetic courier cancellation: a queue receipt does not claim remote success."""
from unittest.mock import Mock

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(settings, monkeypatch):
    settings.SHOPMAN_COURIER_ADAPTER = "shopman.shop.adapters.courier_mock"
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    Shop.objects.create(name="Synthetic cancellation recovery lab")
    order = Order.objects.create(ref="CANCEL-RIDE-LAB", status="ready", data={
        "fulfillment_type": "delivery", "courier": {"id_mch": "RIDE-LAB", "status": "A"}})
    adapter = Mock()
    adapter.cancel.return_value = True
    monkeypatch.setattr(courier, "get_adapter", lambda name: adapter)
    monkeypatch.setattr("shopman.shop.adapters.get_adapter", lambda name: adapter)
    monkeypatch.setattr("shopman.shop.handlers.courier_cancel.get_adapter", lambda name: adapter)
    return order, adapter


def test_cancel_queues_without_network_or_false_success(context):
    order, adapter = context
    task = courier.cancel_ride(order, actor="synthetic-operator")
    adapter.cancel.assert_not_called()
    assert isinstance(task, Directive)
    assert task.status == "queued"
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "A"


def run(task):
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler

    CourierCancelHandler().handle(message=task, ctx={})


def test_remote_timeout_never_reposts(context):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.shop.adapters.courier_machine import CourierError

    order, adapter = context
    adapter.cancel.side_effect = CourierError("timeout", transient=True)
    task = courier.cancel_ride(order, actor="operator")
    for _ in range(2):
        with pytest.raises(DirectiveTerminalError, match="sem resultado confirmado"):
            run(task)
    with pytest.raises(ValueError, match="já iniciado"):
        courier.cancel_ride(order, actor="operator")
    adapter.cancel.assert_called_once_with("RIDE-LAB", reason_id=None)
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "A"


def test_accepted_cancel_recovers_after_local_failure(context, monkeypatch):
    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    original = courier.apply_status
    monkeypatch.setattr(courier, "apply_status", Mock(side_effect=RuntimeError("local save failed")))
    with pytest.raises(RuntimeError):
        run(task)
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "accepted"
    monkeypatch.setattr(courier, "apply_status", original)
    run(task)
    order.refresh_from_db()
    assert courier.get_block(order)["attempts"][-1]["status"] == "C"
    adapter.cancel.assert_called_once()


def test_changed_ride_before_worker_does_not_cancel_replacement(context):
    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    order.data["courier"]["id_mch"] = "REPLACEMENT"
    order.save(update_fields=["data"])
    run(task)
    adapter.cancel.assert_not_called()
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "not_applied"


def test_accepted_response_cannot_cancel_replacement(context):
    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")

    def replace(*args, **kwargs):
        other = Order.objects.get(pk=order.pk)
        other.data["courier"]["id_mch"] = "REPLACEMENT"
        other.save(update_fields=["data"])
        return True

    adapter.cancel.side_effect = replace
    run(task)
    order.refresh_from_db()
    assert courier.get_block(order) == {"id_mch": "REPLACEMENT", "status": "A"}


@pytest.mark.django_db(transaction=True)
def test_remote_call_releases_transaction_and_attempt_is_durable(context):
    from django.db import connection

    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")

    def accept(*args, **kwargs):
        assert not connection.in_atomic_block
        current = Directive.objects.get(pk=task.pk)
        assert current.payload["cancel_attempt"]["state"] == "started"
        return True

    adapter.cancel.side_effect = accept
    run(task)
    adapter.cancel.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_two_workers_claim_one_remote_attempt(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections
    from shopman.orderman.exceptions import DirectiveTerminalError

    if connection.vendor != "postgresql":
        pytest.skip("Independent row locks require PostgreSQL")
    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    entered, release = Event(), Event()

    def remote(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return True

    def worker():
        try:
            run(Directive.objects.get(pk=task.pk))
        finally:
            connections.close_all()

    adapter.cancel.side_effect = remote
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker)
        try:
            if not entered.wait(5):
                first.result(timeout=1)
                pytest.fail("worker did not reach isolated adapter")
            second = pool.submit(worker)
            with pytest.raises(DirectiveTerminalError, match="sem resultado confirmado"):
                second.result(timeout=5)
        finally:
            release.set()
        first.result(timeout=5)
    adapter.cancel.assert_called_once()
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "accepted"
    order.refresh_from_db()
    assert courier.get_block(order)["attempts"][-1]["status"] == "C"


def test_definitive_rejection_is_not_success(context):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.shop.adapters.courier_machine import CourierError

    order, adapter = context
    adapter.cancel.side_effect = CourierError("not permitted", transient=False, outcome_unknown=False)
    task = courier.cancel_ride(order, actor="operator")
    with pytest.raises(DirectiveTerminalError, match="recusou"):
        run(task)
    run(task)
    adapter.cancel.assert_called_once()
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "A"
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "not_applied"


@pytest.mark.django_db(transaction=True)
def test_interruption_after_start_keeps_attempt_fenced(context):
    from shopman.orderman.exceptions import DirectiveTerminalError

    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    adapter.cancel.side_effect = SystemExit(17)
    with pytest.raises(SystemExit):
        run(task)
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "started"
    with pytest.raises(DirectiveTerminalError, match="sem resultado confirmado"):
        run(task)
    adapter.cancel.assert_called_once()


def test_registered_worker_marks_remote_unknown_failed_without_losing_fence(context):
    from shopman.orderman.dispatch import _process_directive

    from shopman.shop.adapters.courier_machine import CourierError

    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    adapter.cancel.side_effect = CourierError("timeout", transient=True)
    _process_directive(task)
    task.refresh_from_db()
    assert task.status == "failed"
    assert task.payload["cancel_attempt"]["state"] == "unknown"
    with pytest.raises(ValueError, match="já iniciado"):
        courier.cancel_ride(order, actor="operator")
    adapter.cancel.assert_called_once()


def test_definitive_worker_refusal_remains_visible_in_existing_panel(context):
    from shopman.orderman.dispatch import _process_directive

    from shopman.backstage.projections.order_queue import _courier_block
    from shopman.shop.adapters.courier_machine import CourierError

    order, adapter = context
    task = courier.cancel_ride(order, actor="operator")
    adapter.cancel.side_effect = CourierError("not permitted", transient=False, outcome_unknown=False)
    _process_directive(task)
    panel = _courier_block(order)
    assert panel["can_cancel"]
    assert "recusou" in panel["error"]["message"]
