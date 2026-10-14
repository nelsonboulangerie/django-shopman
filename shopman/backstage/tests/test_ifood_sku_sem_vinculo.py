"""P2-29: item do iFood sem produto da casa (sem ``externalCode`` ou com código velho).

O pedido já existe (o iFood não espera), então a reserva não acontece e o aviso
``stock_unknown_sku`` sai. Ele precisa dizer QUAL item, por quê, e levar aonde o
item do iFood se liga a um produto da casa: a revisão de vínculos do canal,
filtrada pelo nome do item.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.alerts import alert_context_href
from shopman.shop.models import Channel, Shop
from shopman.shop.services import stock

pytestmark = pytest.mark.django_db

GATED = {"stock": {"allow_untracked": False}}


@pytest.fixture
def ifood(db):
    Shop.objects.create(name="Loja")
    return Channel.objects.create(ref="ifood", name="iFood", config=GATED)


def _order(ref: str, *, channel_ref: str, line_id: str, sku: str, name: str) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        status=Order.Status.NEW,
        total_q=900,
        data={"fulfillment_type": "pickup"},
        snapshot={"items": [{"line_id": line_id, "sku": sku, "name": name, "qty": 1, "unit_price_q": 900}]},
    )
    OrderItem.objects.create(order=order, line_id=line_id, sku=sku, name=name, qty=1, unit_price_q=900, line_total_q=900)
    return order


def _alert(order: Order) -> OperatorAlert:
    return OperatorAlert.objects.get(type="stock_unknown_sku", order_ref=order.ref)


def test_item_without_external_code_names_the_item_and_opens_the_bindings(ifood):
    order = _order("IFOOD-261013-A01", channel_ref="ifood", line_id="9f1c-uuid", sku="9f1c-uuid", name="Pão de queijo")

    stock.hold(order)

    alert = _alert(order)
    assert '"Pão de queijo"' in alert.message
    assert "sem código externo" in alert.message
    assert "sem reserva de estoque" in alert.message
    assert alert_context_href(alert, surface="orders") == (
        "/channels/ifood/catalog?q=P%C3%A3o+de+queijo",
        "Revisar vínculos do iFood",
    )


def test_item_with_an_old_code_says_the_code(ifood):
    order = _order("IFOOD-261013-A02", channel_ref="ifood", line_id="7a2b-uuid", sku="PQ-VELHO", name="Pão de queijo")

    stock.hold(order)

    alert = _alert(order)
    assert '"Pão de queijo"' in alert.message
    assert "código PQ-VELHO" in alert.message
    assert alert_context_href(alert, surface="orders")[1] == "Revisar vínculos do iFood"


def test_other_channels_keep_opening_the_order(ifood):
    Channel.objects.create(ref="gate-web", name="Loja online", config=GATED)
    order = _order("WEB-261013-A03", channel_ref="gate-web", line_id="1", sku="GHOST", name="Bolo")

    stock.hold(order)

    assert alert_context_href(_alert(order), surface="orders") == ("/WEB-261013-A03", "Abrir o pedido")
