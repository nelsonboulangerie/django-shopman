"""O card da comanda no quadro mostra o total que o motor cobra, com desconto manual.

Issue #3245. O ``ManualDiscountModifier`` rateia o desconto manual de pedido
entre as linhas e o tira do ``unit_price_q`` de cada uma, na própria gravação da
comanda. O card do quadro (``_tab_projection``) somava ``qty × unit_price_q``
das linhas e ainda subtraía ``manual_discount.discount_q``: o desconto saía duas
vezes, e o operador via no quadro um total menor do que o cobrado.

A régua: o total do card é o total da revisão e o total do pedido fechado, com
desconto de pedido (fixo e percentual), desconto de linha e os dois juntos.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab, build_pos_tabs
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

pytestmark = pytest.mark.django_db

SAVE_URL = "/api/v1/backstage/pos/tabs/save/"
CLOSE_URL = "/api/v1/backstage/pos/sale/close/"
OPERADOR = "caixa-3245"


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    POSTab.objects.create(ref="00000045", label="45")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    for sku, name, price_q in (("PAO-3245", "Pão", 1000), ("CAFE-3245", "Café", 750)):
        product = Product.objects.create(
            sku=sku, name=name, base_price_q=price_q, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=price_q)
    operator = get_user_model().objects.create_user(username=OPERADOR, password="x", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
    )
    client.force_login(operator)
    terminal = Terminal.default()
    bind_station(client, terminal.ref)
    cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    return {"client": client}


def _post(client, url: str, body: dict):
    return client.post(url, data=json.dumps(body), content_type="application/json")


def _body(session, *, line_discount: dict | None, order_discount: dict | None, request_id: str) -> dict:
    pao = {"line_id": "L1", "sku": "PAO-3245", "name": "Pão", "qty": 3, "unit_price_q": 1000}
    if line_discount:
        pao["discount"] = line_discount
    body = {
        "intent_version": POS_SALE_INTENT_VERSION,
        "tab_ref": "45",
        "tab_session_key": session.session_key,
        "expected_revision": build_open_tab(session)["revision"],
        "items": [
            pao,
            {"line_id": "L2", "sku": "CAFE-3245", "name": "Café", "qty": 1, "unit_price_q": 750},
        ],
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "payment_collection": "terminal",
        "client_request_id": request_id,
    }
    if order_discount:
        body["manual_discount"] = order_discount
    return body


def _card_total_display() -> str:
    (card,) = [tab for tab in build_pos_tabs(channel_ref="pdv") if tab.ref == "00000045"]
    assert card.state == "in_use"
    return card.total_display


CASOS = {
    # 3 × 10,00 + 7,50 = 37,50 cheio em todos os casos.
    "pedido_fixo": (None, {"type": "fixed", "value": "5", "discount_q": 500, "reason": "cortesia"}),
    "pedido_percentual": (None, {"type": "percent", "value": "10", "discount_q": 375, "reason": "cortesia"}),
    "linha": ({"type": "percent", "value": 10, "reason": "cortesia"}, None),
    "linha_e_pedido": (
        {"type": "percent", "value": 10, "reason": "cortesia"},
        {"type": "fixed", "value": "2", "discount_q": 200, "reason": "cortesia"},
    ),
}


@pytest.mark.parametrize("caso", list(CASOS))
def test_card_da_comanda_mostra_o_total_que_o_motor_cobra(balcao, caso):
    client = balcao["client"]
    line_discount, order_discount = CASOS[caso]
    session = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="45", actor="test", operator_username=OPERADOR)
    body = _body(session, line_discount=line_discount, order_discount=order_discount, request_id=f"3245-{caso}")

    saved = _post(client, f"{SAVE_URL}?review=1", body)
    assert saved.status_code == 200, saved.content
    review_total_q = saved.json()["review"]["total_q"]
    assert review_total_q < 3750, "o desconto manual não entrou: o caso não prova nada"

    card = _card_total_display()

    closed = _post(client, CLOSE_URL, {
        **body,
        "expected_revision": saved.json()["revision"],
        "expected_total_q": review_total_q,
        "tendered_q": review_total_q,
    })
    assert closed.status_code == 200, closed.content
    order_total_q = Order.objects.get(ref=closed.json()["order_ref"]).total_q

    assert order_total_q == review_total_q
    assert card == f"R$ {format_money(order_total_q)}"
