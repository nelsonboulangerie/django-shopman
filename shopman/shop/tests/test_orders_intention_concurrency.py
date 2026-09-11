"""PostgreSQL witnesses for distinct intentions against the same order base."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import connection, connections
from shopman.orderman.models import Order

from shopman.shop import lifecycle
from shopman.shop.models import Shop
from shopman.shop.services import operator_orders, remote_mutations


@pytest.mark.django_db(transaction=True)
def test_distinct_keys_cannot_advance_the_same_base_twice():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and independent connections")
    Shop.objects.create(name="Lab")
    order = Order.objects.create(ref="SAME-BASE", status="accepted", channel_ref="web", data={"payment": {"method": "cash"}})
    base = operator_orders.operational_revision(order)
    barrier = Barrier(2)

    def worker(key):
        try:
            stale = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=5)

            def execute():
                try:
                    operator_orders.advance_order(stale, actor="lab", expected_revision=base, target_status="preparing")
                except operator_orders.OrderStateConflict:
                    return {"outcome": "not_applied"}, 409
                return {"outcome": "applied"}, 200

            return remote_mutations.run_idempotent_mutation(scope="lab.distinct-intentions", key=key, fingerprint=base, execute=execute)
        finally:
            connections.close_all()

    # This assay proves local serialization, not downstream/provider delivery.
    with patch.dict(lifecycle._PHASE_HANDLERS, {"on_preparing": lambda *_: None}):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["first", "second"]))
    assert sorted(result.response_code for result in results) == [200, 409]
    order.refresh_from_db()
    assert order.status == "preparing"
    assert order.events.filter(type="status_changed").count() == 1


@pytest.mark.django_db
def test_note_and_assignment_merge_but_stale_same_field_conflicts():
    order = Order.objects.create(ref="FIELDS", status="accepted", data={})
    stale = Order.objects.get(pk=order.pk)
    note_base = operator_orders.operational_revision(order, field="kitchen_note")
    assignment_base = operator_orders.operational_revision(stale, field="assignment")
    operator_orders.save_kitchen_note(order, notes="Sem cebola", expected_revision=note_base)
    operator_orders.assign_order(stale, operator_id=1, operator_name="Ana", actor="ana", expected_revision=assignment_base)
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Sem cebola"
    assert order.data["assignment"]["operator_name"] == "Ana"
    with pytest.raises(operator_orders.OrderStateConflict):
        operator_orders.save_kitchen_note(stale, notes="Sem alho", expected_revision=note_base)
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Sem cebola"


@pytest.mark.django_db
@pytest.mark.parametrize("writer", ["courier", "gateway_throttle", "lifecycle"])
def test_background_writer_keeps_note_and_captured_payment(writer):
    from shopman.shop.services import courier, payment

    order = Order.objects.create(ref="BACKGROUND", status="accepted", data={"payment": {"method": "cash"}})
    stale = Order.objects.get(pk=order.pk)
    operator_orders.save_kitchen_note(order, notes="Sem cebola")
    fresh = Order.objects.get(pk=order.pk)
    fresh.data["payment"]["captured_at"] = "2026-09-10T12:00:00+00:00"
    fresh.save(update_fields=["data"])
    if writer == "courier":
        with patch.object(courier, "_emit_sse"):
            courier._save_block(stale, {"id_mch": "LAB", "status": "A"})
    elif writer == "gateway_throttle":
        payment._stamp_gateway_check(stale)
    else:
        lifecycle._mark_phase_complete(stale, "on_accepted")
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Sem cebola"
    assert order.data["payment"]["captured_at"] == "2026-09-10T12:00:00+00:00"


@pytest.mark.django_db(transaction=True)
def test_concurrent_note_and_assignment_preserve_both_fields():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL independent connections")
    order = Order.objects.create(ref="TWO-FIELDS", status="accepted", data={})
    note_base = operator_orders.operational_revision(order, field="kitchen_note")
    claim_base = operator_orders.operational_revision(order, field="assignment")
    barrier = Barrier(2)

    def worker(kind):
        try:
            stale = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=5)
            if kind == "note":
                operator_orders.save_kitchen_note(stale, notes="Sem cebola", expected_revision=note_base)
            else:
                operator_orders.assign_order(stale, operator_id=1, operator_name="Ana", actor="ana", expected_revision=claim_base)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, ["note", "claim"]))
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Sem cebola"
    assert order.data["assignment"]["operator_name"] == "Ana"
