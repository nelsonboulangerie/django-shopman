"""The operator's review, immutable order and drawer agree down to the cent."""
from decimal import Decimal

import pytest
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.shop.services import pos
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("qty,unit_q,discount,expected_q", [
    (3, 333, {"type": "percent", "value": 10}, 900),
    (6, 150, {"type": "percent", "value": 5}, 858),
    (3, 333, {"type": "fixed", "value": "1,00"}, 900),
    (1, 999, {"type": "fixed", "value": "1,00"}, 899),
])
def test_review_matches_committed_total_and_change(qty, unit_q, discount, expected_q):
    counter = _Counter()
    Product.objects.filter(sku="PAO").update(base_price_q=unit_q)
    payload = {
        "items": [{"sku": "PAO", "qty": qty, "unit_price_q": unit_q}],
        "manual_discount": discount,
        "payment_method": "cash", "tendered_q": 2000,
        "cash_shift_id": counter.shift.pk,
    }
    review = pos.review_sale(channel_ref="pdv", payload=payload, operator_username=counter.operator.username)
    result = counter.close(client_request_id="rounding", **payload)
    order = Order.objects.get(ref=result.order_ref)
    (entry,) = counter.sale_lines()
    assert review.total_q == order.total_q == entry.amount_q == expected_q
    assert review.change_q == entry.payload["change_q"] == 2000 - expected_q
    assert review.discount_q == qty * unit_q - expected_q
    assert all(i["line_total_q"] == Decimal(str(i["qty"])) * i["unit_price_q"] for i in order.snapshot["items"])
