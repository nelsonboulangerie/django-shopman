"""Repeated labels and JSON primitives must not amplify rich queue work."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum
from unittest.mock import Mock

import pytest
from shopman.orderman.models import Order

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections import order_queue


@pytest.mark.django_db
def test_queue_resolves_each_label_once_per_read_without_retaining_old_copy(monkeypatch):
    Order.objects.bulk_create([Order(ref=f"LABEL-{i}", status="accepted", data={"payment": {"method": "cash"}}) for i in range(20)])
    status = Mock(return_value="Nome configurado")
    method = Mock(return_value="Meio configurado")
    monkeypatch.setattr(order_queue, "order_status_label", status)
    monkeypatch.setattr(order_queue, "payment_method_label", method)
    first = order_queue.build_two_zone_queue()
    assert len(first.prep) == 20
    assert {card.status_label for card in first.prep} == {"Nome configurado"}
    assert {card.payment_method_label for card in first.prep} == {"Meio configurado"}
    assert status.call_count == 1
    assert method.call_count == 1
    status.return_value = "Outro nome configurado"
    second = order_queue.build_two_zone_queue()
    assert {card.status_label for card in second.prep} == {"Outro nome configurado"}
    assert status.call_count == 2


def test_atomic_json_fast_path_keeps_enum_decimal_and_date_contracts():
    class Text(StrEnum):
        VALUE = "semantic"

    class Number(IntEnum):
        VALUE = 7

    @dataclass
    class Example:
        value: object

    result = projection_data(Example({"text": Text.VALUE, "number": Number.VALUE, "qty": Decimal("0.500"), "date": date(2026, 9, 11), "values": (None, False, 0, 1.5, "") }))
    assert result == {"value": {"text": "semantic", "number": 7, "qty": "0.500", "date": "2026-09-11", "values": [None, False, 0, 1.5, ""]}}
    assert type(result["value"]["text"]) is str
    assert type(result["value"]["number"]) is int


@pytest.mark.django_db
@pytest.mark.parametrize("status", order_queue.ACTIVE_STATUSES)
def test_batch_card_preserves_item_and_revision_contract_after_fresh_edit(status, django_user_model):
    from shopman.orderman.models import OrderItem

    from shopman.shop.services.operator_orders import operational_revision

    user = django_user_model.objects.create_superuser(username=f"queue-{status}", password="lab-only")
    order = Order.objects.create(ref=f"RICH-{status}", status=status)
    for index in range(5):
        OrderItem.objects.create(order=order, line_id=str(index), sku=f"SKU-{index}", name=f"Item {index}",
                                 qty=Decimal("0.500"), unit_price_q=1000, line_total_q=500)

    def read():
        queue = order_queue.build_two_zone_queue(user=user)
        cards = (*queue.intake, *queue.prep, *queue.expedition_pickup,
                 *queue.expedition_delivery, *queue.expedition_delivery_transit, *queue.preorders)
        card = next(card for card in cards if card.ref == order.ref)
        single = order_queue.build_order_card(Order.objects.get(pk=order.pk), user=user)
        assert (card.items_summary, card.items_count, card.revisions) == (
            single.items_summary, single.items_count, single.revisions)
        for field, revision in card.revisions.items():
            assert revision == operational_revision(Order.objects.get(pk=order.pk), field=field)
        return card

    first = read()
    assert first.items_count == 5
    assert first.items_summary.endswith("...")
    OrderItem.objects.filter(order=order, line_id="0").update(qty=Decimal("0.750"), name="Nome revisto")
    order.data = {"kitchen_note": "Nota revista"}
    order.save(update_fields=["data"])
    second = read()
    assert "0.75x Nome revisto" in second.items_summary
    assert second.revisions["kitchen_note"] != first.revisions["kitchen_note"]
