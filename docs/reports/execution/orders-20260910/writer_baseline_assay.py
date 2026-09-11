"""Diagnostic assertions reproduce defects, not acceptance of product behavior."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection
from shopman.orderman.models import Order

from shopman.shop import lifecycle
from shopman.shop.models import Shop
from shopman.shop.services import courier, operator_orders, payment, waitlist


@pytest.mark.django_db
@pytest.mark.parametrize("writer", ["courier", "gateway_throttle", "waitlist"])
def test_stale_background_writer_erases_independent_note(writer):
    Shop.objects.create(name="Lab")
    order=Order.objects.create(ref="WRITER",status="accepted",data={"payment":{"method":"cash"}})
    stale=Order.objects.get(pk=order.pk)
    operator_orders.save_kitchen_note(order,notes="Sem cebola")
    if writer=="courier":
        with patch.object(courier,"_emit_sse"):
            courier._save_block(stale,{"id_mch":"LAB","status":"A"})
    elif writer=="gateway_throttle":
        payment._stamp_gateway_check(stale)
    else:
        waitlist._write_state(stale,state="confirming")
    order.refresh_from_db()
    assert "kitchen_note" not in order.data

@pytest.mark.django_db(transaction=True)
def test_lifecycle_fresh_read_without_lock_still_loses_interleaved_note():
    assert connection.vendor=="postgresql", "This assay requires the isolated PostgreSQL cluster"
    Shop.objects.create(name="Lab")
    order=Order.objects.create(ref="PHASE",status="accepted",data={"payment":{"method":"cash"}})
    save=Order.save
    def write_note():
        close_old_connections()
        try:
            fresh=Order.objects.get(pk=order.pk)
            operator_orders.save_kitchen_note(fresh,notes="Sem cebola")
        finally:
            close_old_connections()
    def interleaved_save(instance,*args,**kwargs):
        if instance is order:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write_note).result(timeout=5)
        return save(instance,*args,**kwargs)
    with patch.object(Order,"save",interleaved_save):
        lifecycle._mark_phase_complete(order,"on_accepted")
    order.refresh_from_db()
    assert order.data["lifecycle"]["on_accepted"]=="done"
    assert "kitchen_note" not in order.data
