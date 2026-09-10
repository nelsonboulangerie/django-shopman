"""D08: operational projections must preserve the Orderman's decimal quantity."""
from decimal import Decimal

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import build_operator_order, build_order_card


@pytest.mark.django_db
@pytest.mark.parametrize("qty,expected", [("0.500", "0.5"), ("1.125", "1.125"), ("2.000", "2"), ("999999999.999", "999999999.999")])
def test_detail_and_card_preserve_exact_quantity(qty, expected):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Lab")
    order = Order.objects.create(ref="DECIMAL", status="accepted", data={"payment": {"method": "cash"}})
    OrderItem.objects.create(order=order, line_id="1", sku="WEIGHED", name="Pesado", qty=Decimal(qty), unit_price_q=3000, line_total_q=1500)

    detail = build_operator_order(order)
    card = build_order_card(order)

    assert detail.items[0].qty == expected
    assert card.items_summary == f"{expected}x Pesado"
    assert detail.items[0].total_display == "R$ 15,00"
