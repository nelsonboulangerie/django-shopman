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
