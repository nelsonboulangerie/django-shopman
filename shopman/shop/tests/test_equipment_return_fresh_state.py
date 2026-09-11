"""Equipment custody return must preserve concurrent order context."""
import pytest
from shopman.orderman.models import Order

from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


def test_equipment_return_preserves_concurrent_note():
    order = Order.objects.create(ref="EQUIPMENT-CONTEXT", status="completed", data={
        "kitchen_note": "Initial", "dispatch": {"equipment": ["card_machine"], "equipment_out_at": "2026-09-10T12:00:00Z"}})
    stale = Order.objects.get(pk=order.pk)
    operator_orders.save_kitchen_note(order, notes="Concurrent note", actor="lab")
    operator_orders.mark_equipment_returned(stale, actor="lab")
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Concurrent note"
    assert order.data["dispatch"]["equipment_back_by"] == "lab"
