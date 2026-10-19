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
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Batch, Hold, Position, PositionKind

from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db

# O dia se lê na hora do TESTE, não na coleta: perto da meia-noite a coleta cai
# num dia e o teste no outro, e a "fornada de amanhã" vira a de hoje.
def _today() -> date:
    return timezone.localdate()


def _tomorrow() -> date:
    return _today() + timedelta(days=1)


def _day_after() -> date:
    return _today() + timedelta(days=2)


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
    # Produto com validade ganha lote; a loja só vende lote classificado.
    Batch.objects.filter(sku=product.sku, quality_grade_ref="").update(quality_grade_ref="standard")


def _bread_of_the_day(product):
    product.shelf_life_days = 0
    product.save(update_fields=["shelf_life_days"])


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
        _plan(croissant, "4", _tomorrow())
        assert _set_qty(client, product.sku, 2).status_code == 200

        refused = _set_qty(client, croissant.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        body = refused.json()
        assert body["error_code"] == "cart_date_mismatch"
        assert body["sku"] == croissant.sku
        assert body["cart_date"] == _today().isoformat()
        assert body["item_date"] == _tomorrow().isoformat()
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
        # Pão do dia: o pronto de hoje não vale amanhã (é a validade que diz).
        _bread_of_the_day(product)
        _plan(croissant, "4", _tomorrow())
        _ready(product, "5")
        assert _set_qty(client, croissant.sku, 2).status_code == 200

        refused = _set_qty(client, product.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        body = refused.json()
        assert body["error_code"] == "cart_date_mismatch"
        assert body["cart_date"] == _tomorrow().isoformat()
        assert body["item_date"] == _today().isoformat()
        assert _active_holds(product.sku) == []
        assert _cart_skus(client) == {croissant.sku: 2}

    def test_two_different_batch_days_are_two_orders(
        self, client, shop_window, croissant, baguette,
    ):
        _plan(croissant, "4", _tomorrow())
        _plan(baguette, "4", _day_after())
        assert _set_qty(client, croissant.sku, 1).status_code == 200

        refused = _set_qty(client, baguette.sku, 1)

        assert refused.status_code == 409, refused.content[:400]
        assert refused.json()["item_date"] == _day_after().isoformat()
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
        _plan(croissant, "4", _tomorrow())
        _plan(baguette, "4", _tomorrow())
        assert _set_qty(client, croissant.sku, 1).status_code == 200
        assert _set_qty(client, baguette.sku, 1).status_code == 200
        assert {h.target_date for h in Hold.objects.active()} == {_tomorrow()}

    def test_emptying_the_cart_frees_the_date(self, client, shop_window, product, croissant):
        """A data é da sacola enquanto ela tem reserva; esvaziou, a próxima escolhe."""
        _ready(product, "5")
        _plan(croissant, "4", _tomorrow())
        assert _set_qty(client, product.sku, 1).status_code == 200
        assert _set_qty(client, product.sku, 0).status_code == 200

        assert _set_qty(client, croissant.sku, 1).status_code == 200
        assert {h.target_date for h in _active_holds(croissant.sku)} == {_tomorrow()}

    def test_without_the_waitlist_everything_is_today(self, client, channel, product, croissant):
        """Fila desligada: toda reserva é para hoje, e a regra nunca morde."""
        for item in (product, croissant):
            _ensure_listing_item(channel, item, price_q=900)
            _ready(item, "5")
        assert _set_qty(client, product.sku, 1).status_code == 200
        assert _set_qty(client, croissant.sku, 1).status_code == 200


# ── A sacola reserva NA data dela (WP-DATA-E-PROMESSA, L2/P3/P4) ─────────────


def _cart_for(channel, day: date) -> str:
    """Sacola com a data que o cliente escolheu (``delivery_date`` na sessão)."""
    from shopman.shop.services import cart as cart_service

    session, key = cart_service.get_or_create_session(
        session_key=None, channel_ref=channel.ref, origin_channel="web",
    )
    session.data = {**(session.data or {}), "delivery_date": day.isoformat()}
    session.save(update_fields=["data"])
    return key


def _add(channel, key: str, product, qty: int):
    from shopman.shop.services import cart as cart_service

    return cart_service.add_item(
        session_key=key, channel_ref=channel.ref, origin_channel="web",
        sku=product.sku, qty=qty, unit_price_q=900,
    )


def _sell_out_today(channel, product, qty: str):
    """O pronto de hoje existe, mas outra sacola já levou tudo."""
    from shopman.shop.services import availability

    _ready(product, qty)
    taken = availability.reserve(
        product.sku, Decimal(qty), session_key="outra-sacola", channel_ref=channel.ref,
        target_date=_today(),
    )
    assert taken["ok"], taken


class TestTheCartReservesOnItsDate:
    def test_todays_sold_out_does_not_stop_an_order_for_tomorrows_batch(
        self, shop_window, croissant,
    ):
        _bread_of_the_day(croissant)
        _sell_out_today(shop_window, croissant, "2")
        _plan(croissant, "4", _tomorrow())
        key = _cart_for(shop_window, _tomorrow())

        _add(shop_window, key, croissant, 3)

        mine = [h for h in _active_holds(croissant.sku) if (h.metadata or {}).get("reference") == key]
        assert sum(h.quantity for h in mine) == Decimal("3")
        assert {h.target_date for h in mine} == {_tomorrow()}
        assert {h.quant.target_date for h in mine} == {_tomorrow()}, "sai da fornada de amanhã"

    def test_todays_ready_stock_does_not_serve_tomorrow_without_a_batch(
        self, shop_window, croissant,
    ):
        """O inverso: amanhã sem fornada, o pronto de hoje (pão do dia) não serve."""
        from shopman.shop.services.cart import CartDateMismatchError

        _bread_of_the_day(croissant)
        _ready(croissant, "5")
        key = _cart_for(shop_window, _tomorrow())

        with pytest.raises(CartDateMismatchError) as refused:
            _add(shop_window, key, croissant, 1)

        assert refused.value.cart_date == _tomorrow()
        assert refused.value.item_date == _today()
        assert _active_holds(croissant.sku) == [], "a recusa não reserva antes de recusar"

    def test_tomorrows_batch_does_not_serve_a_cart_for_today(self, shop_window, croissant):
        """Sacola de hoje: a fornada de amanhã é outro pedido, sem reserva."""
        from shopman.shop.services.cart import CartDateMismatchError

        _plan(croissant, "4", _tomorrow())
        key = _cart_for(shop_window, _today())

        with pytest.raises(CartDateMismatchError) as refused:
            _add(shop_window, key, croissant, 1)

        assert refused.value.cart_date == _today()
        assert refused.value.item_date == _tomorrow()
        assert _active_holds(croissant.sku) == []

    def test_cart_for_tomorrow_takes_tomorrows_batch_even_with_ready_stock_today(
        self, client, shop_window, croissant, baguette,
    ):
        """D18(c): o item existe nas duas datas e a sacola está em amanhã; entra em amanhã."""
        _bread_of_the_day(baguette)
        _plan(croissant, "4", _tomorrow())
        _ready(baguette, "5")
        _plan(baguette, "4", _tomorrow())
        assert _set_qty(client, croissant.sku, 1).status_code == 200

        added = _set_qty(client, baguette.sku, 2)

        assert added.status_code == 200, added.content[:400]
        assert {h.target_date for h in _active_holds(baguette.sku)} == {_tomorrow()}
        assert {h.quant.target_date for h in _active_holds(baguette.sku)} == {_tomorrow()}

    def test_partial_today_is_offered_instead_of_another_order(
        self, client, shop_window, product, croissant,
    ):
        """P4: sacola de hoje, o pronto cobre só parte; a recusa oferece o que há hoje."""
        _ready(product, "5")
        _ready(croissant, "2")
        _plan(croissant, "4", _tomorrow())
        assert _set_qty(client, product.sku, 1).status_code == 200

        refused = _set_qty(client, croissant.sku, 3)

        assert refused.status_code == 409, refused.content[:400]
        body = refused.json()
        assert body["error_code"] != "cart_date_mismatch", body
        assert body["available_qty"] == 2
        assert _active_holds(croissant.sku) == []
