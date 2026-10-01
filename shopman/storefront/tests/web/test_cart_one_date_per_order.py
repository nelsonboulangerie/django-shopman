"""Loja online: um pedido, uma data.

A lei é da SUPERFÍCIE (decisão do dono, 01/10/2026): na loja online o cliente
age sozinho, e cada pedido tem uma data alvo só. Quem quer dois pães hoje e três
para amanhã faz dois pedidos. (No balcão a régua é outra: a comanda pode ter
linhas de datas diferentes, uma data por linha.)

Antes deste teste a sacola aceitava as duas datas: com a fila de espera ligada,
o item que só existe na fornada de amanhã entrava ancorado em AMANHÃ ao lado de
um item pronto HOJE, e o pedido nascia com duas promessas. A sacola agora recusa
o item de outra data com 409 ``cart_date_mismatch`` e diz que ele é de OUTRO
pedido; nenhuma reserva nova sobra da recusa.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
DAY_AFTER = TODAY + timedelta(days=2)


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _enable_waitlist(channel, horizon_days: int = 2):
    channel.config = {
        **(channel.config or {}),
        "waitlist": {"enabled": True, "horizon_days": horizon_days},
    }
    channel.save(update_fields=["config"])


def _plan(product, qty: str, day: date):
    stock.plan(
        quantity=Decimal(qty), product=product, target_date=day,
        position=_position(), reason="fornada (teste de uma data por pedido)",
    )


def _ready(product, qty: str):
    stock.receive(
        quantity=Decimal(qty), sku=product.sku, position=_position(),
        target_date=None, reason="pronta-entrega (teste de uma data por pedido)",
    )


def _set_qty(client, sku, qty):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def _active_holds(sku):
    return list(Hold.objects.filter(sku=sku).active())


def _cart_skus(client) -> dict[str, int]:
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    return {item["sku"]: int(item["qty"]) for item in cart["items"]}


@pytest.fixture
def baguette(db):
    return Product.objects.create(
        sku="BAGUETE", name="Baguete", base_price_q=1200,
        is_published=True, is_sellable=True,
    )


@pytest.fixture
def shop_window(channel, product, croissant, baguette):
    """Fila ligada; três produtos no cardápio da loja."""
    for item in (product, croissant, baguette):
        _ensure_listing_item(channel, item, price_q=900)
    _enable_waitlist(channel)
    return channel


class TestTheCartRefusesASecondDate:
    def test_item_only_in_tomorrows_batch_does_not_join_a_cart_for_today(
        self, client, shop_window, product, croissant,
    ):
        _ready(product, "5")
        _plan(croissant, "4", TOMORROW)
        assert _set_qty(client, product.sku, 2).status_code == 200

        refused = _set_qty(client, croissant.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        body = refused.json()
        assert body["error_code"] == "cart_date_mismatch"
        assert body["sku"] == croissant.sku
        assert body["cart_date"] == TODAY.isoformat()
        assert body["item_date"] == TOMORROW.isoformat()
        assert "outro pedido" in body["detail"], body["detail"]
        assert "Croissant" in body["detail"]
        assert "amanhã" in body["detail"] and "hoje" in body["detail"]
        assert "—" not in body["detail"] + body["title"], "copy sem travessão"
        assert body["available_qty"] is None, "não há quantidade a oferecer: é outra data"
        assert body["substitutes"] == []
        assert body["is_notifiable"] is False
        assert _active_holds(croissant.sku) == [], "a recusa não deixa reserva para trás"
        assert _cart_skus(client) == {product.sku: 2}

    def test_ready_item_does_not_join_a_cart_waiting_for_tomorrows_batch(
        self, client, shop_window, product, croissant,
    ):
        _plan(croissant, "4", TOMORROW)
        _ready(product, "5")
        assert _set_qty(client, croissant.sku, 2).status_code == 200

        refused = _set_qty(client, product.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        body = refused.json()
        assert body["error_code"] == "cart_date_mismatch"
        assert body["cart_date"] == TOMORROW.isoformat()
        assert body["item_date"] == TODAY.isoformat()
        assert _active_holds(product.sku) == []
        assert _cart_skus(client) == {croissant.sku: 2}

    def test_two_different_batch_days_are_two_orders(
        self, client, shop_window, croissant, baguette,
    ):
        _plan(croissant, "4", TOMORROW)
        _plan(baguette, "4", DAY_AFTER)
        assert _set_qty(client, croissant.sku, 1).status_code == 200

        refused = _set_qty(client, baguette.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        assert refused.json()["item_date"] == DAY_AFTER.isoformat()
        assert _active_holds(baguette.sku) == []


class TestTheSameDateStillFits:
    def test_two_ready_items_share_today(self, client, shop_window, product, croissant):
        _ready(product, "5")
        _ready(croissant, "5")
        assert _set_qty(client, product.sku, 2).status_code == 200
        assert _set_qty(client, croissant.sku, 1).status_code == 200
        assert _cart_skus(client) == {product.sku: 2, croissant.sku: 1}

    def test_two_items_of_the_same_batch_share_its_day(
        self, client, shop_window, croissant, baguette,
    ):
        _plan(croissant, "4", TOMORROW)
        _plan(baguette, "4", TOMORROW)
        assert _set_qty(client, croissant.sku, 1).status_code == 200
        assert _set_qty(client, baguette.sku, 1).status_code == 200
        assert {h.target_date for h in Hold.objects.active()} == {TOMORROW}

    def test_emptying_the_cart_frees_the_date(self, client, shop_window, product, croissant):
        """A data é da sacola enquanto ela tem reserva; esvaziou, a próxima escolhe."""
        _ready(product, "5")
        _plan(croissant, "4", TOMORROW)
        assert _set_qty(client, product.sku, 1).status_code == 200
        assert _set_qty(client, product.sku, 0).status_code == 200

        assert _set_qty(client, croissant.sku, 1).status_code == 200
        assert {h.target_date for h in _active_holds(croissant.sku)} == {TOMORROW}

    def test_without_the_waitlist_everything_is_today(self, client, channel, product, croissant):
        """Fila desligada: toda reserva é para hoje, e a regra nunca morde."""
        for item in (product, croissant):
            _ensure_listing_item(channel, item, price_q=900)
            _ready(item, "5")
        assert _set_qty(client, product.sku, 1).status_code == 200
        assert _set_qty(client, croissant.sku, 1).status_code == 200
