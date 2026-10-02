"""Observação por item na sacola da loja (``PUT /api/v1/cart/skus/<sku>/notes/``).

O PDV já mandava a observação de cada item à cozinha (``meta["notes"]`` da
linha → ticket do KDS). A loja só tinha a observação do pedido inteiro: quem
queria "sem gergelim" em um dos pães escrevia no rodapé e a cozinha adivinhava
de qual. Estes testes travam o primeiro elo (a sacola grava a observação na
linha) e o último (o pedido que nasce dela leva a observação à cozinha).
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from shopman.orderman.models import Session
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind

from shopman.shop.services import account as account_service
from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db


def _put_notes(client, sku, notes):
    return client.put(
        f"/api/v1/cart/skus/{sku}/notes/",
        data=json.dumps({"notes": notes}),
        content_type="application/json",
    )


def _session(client) -> Session:
    return Session.objects.get(session_key=client.session["cart_session_key"])


@pytest.fixture
def in_cart(client, channel, product):
    _ensure_listing_item(channel, product, price_q=90)
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=Decimal("20"), sku=product.sku, position=position, target_date=None, reason="teste")
    resp = client.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": 2}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content[:400]
    return product


def test_note_is_written_on_the_line_and_comes_back_in_the_cart(client, in_cart):
    resp = _put_notes(client, in_cart.sku, "  sem   gergelim  ")

    assert resp.status_code == 200, resp.content[:400]
    line = next(item for item in resp.json()["cart"]["items"] if item["sku"] == in_cart.sku)
    assert line["notes"] == "sem gergelim"
    assert line["qty"] == 2
    stored = _session(client).items[0]
    assert stored["meta"]["notes"] == "sem gergelim"
    assert stored["qty"] == 2

    # A quantidade muda e a observação fica.
    client.put(
        f"/api/v1/cart/skus/{in_cart.sku}/",
        data=json.dumps({"qty": 3}),
        content_type="application/json",
    )
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    assert cart["items"][0]["notes"] == "sem gergelim"


def test_empty_note_removes_it(client, in_cart):
    _put_notes(client, in_cart.sku, "bem assado")

    resp = _put_notes(client, in_cart.sku, "")

    assert resp.status_code == 200
    assert resp.json()["cart"]["items"][0]["notes"] == ""
    assert "notes" not in _session(client).items[0]["meta"]


def test_note_longer_than_the_limit_is_refused_in_the_error_dialect(client, in_cart):
    resp = _put_notes(client, in_cart.sku, "x" * 141)

    assert resp.status_code == 400
    assert resp.json()["field"] == "notes"


def test_note_for_an_item_outside_the_cart_is_404(client, in_cart):
    resp = _put_notes(client, "OUTRO-SKU", "sem sal")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Este item não está na sua sacola."


def test_the_note_reaches_the_kitchen_ticket_lines(client, in_cart):
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.services import kds

    _put_notes(client, in_cart.sku, "sem gergelim")
    line = _session(client).items[0]
    # O CommitService copia ``meta`` da linha da sessão para o ``OrderItem``
    # (``commit.py``); aqui o pedido nasce com a linha como a sessão a tinha.
    order = Order.objects.create(ref="NOTES-1", channel_ref="web", status="new", total_q=180)
    OrderItem.objects.create(
        order=order, line_id=line["line_id"], sku=line["sku"], name=line.get("name", ""),
        qty=line["qty"], unit_price_q=90, line_total_q=180, meta=line["meta"],
    )

    assert kds.order_lines(order)[0]["notes"] == "sem gergelim"


def test_anonymized_cart_refuses_a_new_note(client, in_cart):
    session = _session(client)
    Session.objects.filter(pk=session.pk).update(handle_type="anonymized", handle_ref="anon")

    resp = _put_notes(client, in_cart.sku, "sem sal")

    assert resp.status_code == 409
    assert "notes" not in _session(client).items[0]["meta"]


def test_account_erasure_scrubs_the_item_note():
    clean, changed = account_service._scrub_item_meta({"notes": "sem sal", "batch_ref": "B1"})

    assert changed is True
    assert clean == {"batch_ref": "B1"}
