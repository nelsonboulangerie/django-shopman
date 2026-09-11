"""Synthetic physical custody: no payment provider or hardware is contacted."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.urls import reverse
from shopman.orderman.models import Fulfillment, Order

from shopman.backstage.models import DeliveryDevice
from shopman.backstage.projections.order_queue import build_two_zone_queue
from shopman.backstage.services.delivery_devices import PREFIX
from shopman.backstage.tests._order_intent import advance_payload
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds, operator_orders


@pytest.fixture
def inventory(db):
    Shop.objects.create(name="Device lab")
    Channel.objects.create(ref="device-lab", name="Device lab", config={"fulfillment": {"equipment": ["card_machine"]}})
    return DeliveryDevice.objects.create(label="Azul", identification="LAB-01")


def order(ref, *, card=True):
    return Order.objects.create(ref=ref, channel_ref="device-lab", status="ready", total_q=1000, data={
        "fulfillment_type": "delivery", "payment": {"method": "credit" if card else "cash", "collection": "on_delivery"}})


def dispatch(order, device):
    return operator_orders.advance_order(order, actor="lab", equipment=[PREFIX + str(device.ref)])


@pytest.mark.django_db
def test_dispatch_return_and_reallocation_keep_payment_independent(inventory):
    first, second = order("DEVICE-1"), order("DEVICE-2")
    dispatch(first, inventory)
    inventory.refresh_from_db()
    assert inventory.current_order_id == first.pk
    with pytest.raises(ValueError, match="maquininha"):
        dispatch(second, inventory)
    second.refresh_from_db()
    assert second.status == "ready"
    queue = build_two_zone_queue()
    assert not queue.equipment_available
    assert queue.equipment_out[0].label == "Azul"
    operator_orders.mark_equipment_returned(first, actor="lab")
    assert "cod_settled_at" not in first.data["payment"]
    assert build_two_zone_queue().equipment_available[0].label == "Azul"
    dispatch(second, inventory)
    with pytest.raises(ValueError, match="já voltou"):
        operator_orders.mark_equipment_returned(first, actor="lab")
    inventory.refresh_from_db()
    assert inventory.current_order_id == second.pk


@pytest.mark.django_db
def test_inactive_and_missing_do_not_block_unrelated_cash(inventory):
    inventory.active = False
    inventory.save(update_fields=("active",))
    with pytest.raises(ValueError, match="maquininha"):
        dispatch(order("INACTIVE"), inventory)
    with pytest.raises(ValueError, match="maquininha"):
        operator_orders.advance_order(order("MISSING"), actor="lab")
    plain = order("CASH", card=False)
    operator_orders.advance_order(plain, actor="lab")
    assert plain.status == "dispatched"


@pytest.mark.django_db
@pytest.mark.parametrize("entry", ["order", "kds", "fulfillment", "courier"])
def test_alternative_dispatch_cannot_bypass_allocation(inventory, entry):
    pending = order("BYPASS")
    with pytest.raises(ValueError, match="maquininha"):
        if entry == "order":
            pending.transition_status("dispatched")
        elif entry == "kds":
            assert "Gestor" in kds.expedition_block_reason(pending, action="dispatch")
            kds.expedition_action(pending, action="dispatch", actor="lab")
        elif entry == "courier":
            from shopman.shop.services import courier

            pending.data["courier"] = {"id_mch": "synthetic-ride", "status": "E"}
            pending.save(update_fields=("data",))
            courier.recover_local_status(pending, ride_id="synthetic-ride")
        else:
            fulfillment = Fulfillment.objects.create(order=pending, status="in_progress")
            fulfillment.status = "dispatched"
            fulfillment.save()
    pending.refresh_from_db()
    assert pending.status == "ready"


@pytest.mark.django_db
def test_partial_failure_rolls_back_device_and_dispatch(inventory):
    pending = order("PARTIAL")
    with patch.object(operator_orders, "_sync_delivery_fulfillment", side_effect=RuntimeError("lab fault")):
        with pytest.raises(RuntimeError, match="lab fault"):
            dispatch(pending, inventory)
    inventory.refresh_from_db()
    pending.refresh_from_db()
    assert inventory.current_order_id is None
    assert pending.status == "ready" and "dispatch" not in pending.data


@pytest.mark.django_db
def test_one_order_cannot_hold_two_devices(inventory):
    pending = order("UNIQUE")
    dispatch(pending, inventory)
    with pytest.raises(IntegrityError), transaction.atomic():
        DeliveryDevice.objects.create(label="B", identification="LAB-02", current_order=pending)


@pytest.mark.django_db
def test_lost_response_replays_same_allocation_receipt(inventory, client, django_user_model):
    user = django_user_model.objects.create_superuser("device-user", password="synthetic")
    client.force_login(user)
    pending = order("REPLAY")
    url = reverse("api-backstage-order-advance", args=[pending.ref])
    body = advance_payload(client, pending.ref, equipment=[PREFIX + str(inventory.ref)])
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="device-intent")
    assert first.status_code == 200, first.content
    receipt = client.get(url, {"idempotency_key": "device-intent"})
    assert receipt.json()["outcome"] == "applied"
    repeated = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="device-intent")
    assert repeated.status_code == 200 and repeated.json()["replayed"]
    inventory.refresh_from_db()
    assert inventory.current_order_id == pending.pk
    assert pending.events.filter(type="status_changed", payload__new_status="dispatched").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_orders_have_exactly_one_winner(inventory, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row locks required")
    orders = [order("RACE-A"), order("RACE-B")]
    from shopman.backstage.services import delivery_devices

    available_read = delivery_devices.has_available
    both_saw_available = Barrier(2)
    def observe_before_competing(pending):
        available = available_read(pending)
        assert available
        both_saw_available.wait(timeout=10)
        return available
    monkeypatch.setattr(delivery_devices, "has_available", observe_before_competing)
    barrier = Barrier(2)
    def attempt(pk):
        try:
            stale = Order.objects.get(pk=pk)
            barrier.wait(timeout=5)
            try:
                dispatch(stale, inventory)
                return "applied"
            except ValueError as exc:
                assert "maquininha" in str(exc)
                return "refused"
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [o.pk for o in orders]))
    assert sorted(results) == ["applied", "refused"]
    assert Order.objects.filter(status="dispatched").count() == 1
    inventory.refresh_from_db()
    assert inventory.current_order.status == "dispatched"


@pytest.mark.django_db(transaction=True)
def test_return_racing_settlement_preserves_both_facts(inventory, django_user_model):
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row locks required")
    from shopman.cashman import services as cash
    from shopman.payman.models import PaymentIntent

    user = django_user_model.objects.create_user(username="device-custody")
    shift = cash.open_shift(operator=user)
    pending = order("RETURN-SETTLE")
    dispatch(pending, inventory)
    barrier = Barrier(2)
    def attempt(kind):
        try:
            stale = Order.objects.get(pk=pending.pk)
            barrier.wait(timeout=5)
            if kind == "return":
                operator_orders.mark_equipment_returned(stale, actor=user.username)
            else:
                operator_orders.settle_delivery_cash(stale, actor=user.username, cash_shift=shift)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, ["return", "settle"]))
    inventory.refresh_from_db()
    pending.refresh_from_db()
    assert inventory.current_order_id is None
    assert pending.data["payment"]["cod_settled_at"]
    assert pending.data["dispatch"]["equipment_back_at"]
    assert PaymentIntent.objects.filter(order_ref=pending.ref, status="captured").count() == 1
    assert cash.balance(shift) == 0


@pytest.mark.django_db
def test_admin_stale_form_cannot_release_allocated_device(inventory):
    from django.contrib import admin

    from shopman.backstage.admin.delivery_devices import DeliveryDeviceAdmin

    stale = DeliveryDevice.objects.get(pk=inventory.pk)
    pending = order("ADMIN-RACE")
    dispatch(pending, inventory)
    stale.label = "Nome atualizado"
    stale.active = False
    DeliveryDeviceAdmin(DeliveryDevice, admin.site).save_model(None, stale, None, True)
    inventory.refresh_from_db()
    assert inventory.current_order_id == pending.pk
    assert not inventory.active
    operator_orders.mark_equipment_returned(pending, actor="lab")
    assert not build_two_zone_queue().equipment_available


@pytest.mark.django_db
def test_reverse_migration_refuses_populated_inventory(inventory):
    import importlib
    from types import SimpleNamespace

    from django.apps import apps

    migration = importlib.import_module("shopman.backstage.migrations.0061_delivery_device")
    with pytest.raises(RuntimeError, match="Preserve"):
        migration.refuse_populated_inventory_removal(apps, SimpleNamespace(connection=connection))
    assert DeliveryDevice.objects.filter(pk=inventory.pk).exists()
