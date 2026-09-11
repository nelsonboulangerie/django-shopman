"""A delayed estimate cannot be stored against a replacement destination."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from shopman.orderman.models import Order

from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.services.operator_orders import OrderStateConflict

pytestmark = pytest.mark.django_db


def test_estimate_does_not_adopt_old_destination(monkeypatch):
    cache.clear()
    Shop.objects.create(name="Synthetic quote", latitude=-23.34, longitude=-51.16)
    order = Order.objects.create(ref="QUOTE-LAB", status="ready", data={"fulfillment_type": "delivery",
        "delivery_address_structured": {"latitude": -23.31, "longitude": -51.15}})

    def estimate(**kwargs):
        other = Order.objects.get(pk=order.pk)
        other.data["delivery_address_structured"]["latitude"] = -23.39
        other.save(update_fields=["data"])
        return SimpleNamespace(value_q=1250, minutes=15, km=4)

    monkeypatch.setattr(courier, "get_adapter", lambda name: Mock(estimate=estimate))
    with pytest.raises(OrderStateConflict):
        courier.estimate_for_order(order, store=True)
    order.refresh_from_db()
    assert "estimate" not in courier.get_block(order)
