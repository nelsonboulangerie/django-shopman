"""The physical preparation read must preserve the order's exact quantity."""
from decimal import Decimal

import pytest
from shopman.offerman.models import Product, ProductComponent
from shopman.orderman.models import Order, OrderItem, Session

from shopman.backstage.models import KDSInstance
from shopman.backstage.projections.kds import build_kds_ticket
from shopman.shop.services import kds

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("bundle", [False, True])
def test_fraction_survives_ticket_and_projection(bundle):
    KDSInstance.objects.create(ref="fraction-picking", name="Lab", type="picking")
    Session.objects.create(session_key="FRACTION-LAB", channel_ref="web")
    order = Order.objects.create(ref="FRACTION-LAB", session_key="FRACTION-LAB", status="preparing")
    parent = Product.objects.create(sku="LAB-FRAC", name="Lab", unit="kg")
    if bundle:
        child = Product.objects.create(sku="LAB-COMP", name="Componente", unit="kg")
        ProductComponent.objects.create(parent=parent, component=child, qty=Decimal("0.500"))
    OrderItem.objects.create(order=order, line_id="fraction-line", sku=parent.sku, name=parent.name, qty=Decimal("0.500"), unit_price_q=1000, line_total_q=500)
    ticket = kds.dispatch(order)[0]
    expected = "0.25" if bundle else "0.5"
    assert ticket.items[0]["qty"] == expected
    assert build_kds_ticket(ticket.pk).items[0].qty == expected
    assert kds.dispatch(order) == []  # exact quantity does not change line dedupe
