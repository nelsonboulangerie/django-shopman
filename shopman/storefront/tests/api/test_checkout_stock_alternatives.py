"""Faltou estoque no envio: a recusa traz a folha de alternativas pronta (#2687).

Até aqui a recusa ``insufficient_supply`` do ``POST /api/v1/checkout/`` dizia só
o item e a tela mandava a cliente à sacola. A folha de alternativas, que a
sacola abre no 409, precisa do teto da linha, dos substitutos e de saber se dá
para pedir o aviso de volta. A recusa do envio agora traz esse mesmo corpo em
``stock_issue``, lido da linha recusada sem mexer em reserva nenhuma, e o
checkout abre a folha sem sair da tela.

O caso de verdade: a reserva da sacola venceu, outra cliente levou parte do pão,
e a primeira tenta enviar.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

SKU = "TABAT"


def _world(*, on_shelf: str = "5"):
    from shopman.offerman.models import Listing, ListingItem, Product
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Casa", brand_name="Casa", short_name="Casa", phone="554333231997")
    Channel.objects.create(ref="web", name="Loja online", is_active=True)
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    product = Product.objects.create(
        sku=SKU, name="Tabatière", base_price_q=600, is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(listing=listing, product=product, price_q=600, is_published=True, is_sellable=True)
    position, _ = Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(
        quantity=Decimal(on_shelf), sku=SKU, position=position, target_date=None,
        reason="pronta-entrega (teste das alternativas no checkout)",
    )
    return product


def _set_qty(client, qty, sku=SKU):
    resp = client.put(f"/api/v1/cart/skus/{sku}/", data=json.dumps({"qty": qty}), content_type="application/json")
    assert resp.status_code in (200, 201), resp.content[:400]
    return resp


def _session_key(client) -> str:
    return client.session["cart_session_key"]


def _holds(client):
    from shopman.stockman.models import Hold

    return Hold.objects.filter(metadata__reference=_session_key(client))


def _lapse(client):
    """A reserva da sacola vence e a varredura a solta."""
    from shopman.stockman.services.holds import StockHolds

    _holds(client).filter(expires_at__isnull=False).update(expires_at=timezone.now() - timedelta(minutes=5))
    assert StockHolds.release_expired() >= 1


def _another_customer_takes(qty):
    _set_qty(Client(), qty)


def _shortage(client):
    from shopman.shop.services.cart import line_shortage

    return line_shortage(session_key=_session_key(client), channel_ref="web", sku=SKU)


def _line(client) -> dict:
    body = client.get("/api/v1/storefront/cart/").json()
    [line] = (body.get("cart") or body)["items"]
    return line


# ── a leitura da linha recusada ─────────────────────────────────────────


class TestLineShortage:
    def test_says_how_many_are_left_for_the_line(self):
        _world(on_shelf="5")
        client = Client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(3)

        shortage = _shortage(client)

        assert shortage.sku == SKU
        assert shortage.requested_qty == 4
        assert shortage.available_qty == 2
        assert shortage.line_qty is None
        assert shortage.line_id == _line(client)["line_id"]
        assert shortage.error_code == "insufficient_supply"
        assert shortage.is_paused is False

    def test_nothing_left_offers_no_quantity(self):
        _world(on_shelf="4")
        client = Client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(4)

        assert _shortage(client).available_qty == 0

    def test_the_live_reservation_of_the_bag_counts(self):
        # A reserva viva é da própria cliente: sem contá-la, o teto seria só o
        # livre (1) e a folha mandaria encolher uma linha que cabe inteira.
        _world(on_shelf="5")
        client = Client()
        _set_qty(client, 4)

        assert _shortage(client).available_qty == 4

    def test_only_reads(self):
        _world(on_shelf="5")
        client = Client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(3)
        holds_before = sorted(_holds(client).values_list("pk", "status"))
        line_before = _line(client)

        _shortage(client)

        assert sorted(_holds(client).values_list("pk", "status")) == holds_before
        assert _line(client)["qty"] == line_before["qty"]

    def test_passes_the_missing_quantity_and_the_bag_date_to_the_substitutes(self, monkeypatch):
        from shopman.shop.services import substitutes

        calls = []
        offer = [{"sku": "CROIS", "name": "Croissant", "price_q": 800, "available_qty": 9, "can_order": True}]

        def fake_find(sku, **kwargs):
            calls.append((sku, kwargs))
            return offer

        monkeypatch.setattr(substitutes, "find", fake_find)
        _world(on_shelf="5")
        client = Client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(3)

        shortage = _shortage(client)

        assert shortage.substitutes == offer
        [(sku, kwargs)] = calls
        assert sku == SKU
        assert kwargs["qty"] == Decimal("4")
        assert kwargs["channel"] == "web"
        assert "target_date" in kwargs

    def test_no_line_no_shortage(self):
        _world(on_shelf="5")
        client = Client()
        _set_qty(client, 1, sku=SKU)
        from shopman.shop.services.cart import line_shortage

        assert line_shortage(session_key=_session_key(client), channel_ref="web", sku="OUTRO") is None
        assert line_shortage(session_key="sem-sacola", channel_ref="web", sku=SKU) is None


# ── a recusa do envio, ponta a ponta ────────────────────────────────────


def _checkout(client):
    from shopman.storefront.tests._checkout_baseline import with_baseline
    from shopman.storefront.tests._pickup_today import today_pickup_slot

    payload = with_baseline(client, {
        "name": "Ana", "phone": "+5543999990001",
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": today_pickup_slot(),
        "payment_method": "cash",
    })
    return client.post("/api/v1/checkout/", data=payload, content_type="application/json")


def _customer_client():
    from shopman.guestman.models import Customer

    from shopman.storefront.tests.security.conftest import login_as_customer

    client = Client()
    login_as_customer(client, Customer.objects.create(ref="CUST-ANA", first_name="Ana", phone="+5543999990001"))
    return client


class TestCheckoutRefusalCarriesTheSheet:
    def test_the_refusal_brings_what_the_bag_409_brings(self):
        _world(on_shelf="5")
        client = _customer_client()
        _set_qty(client, 4)
        line_id = _line(client)["line_id"]
        _lapse(client)
        _another_customer_takes(3)

        resp = _checkout(client)

        assert resp.status_code == 400, resp.content[:600]
        body = resp.json()
        assert body["error_code"] == "insufficient_supply"
        assert body["context"]["sku"] == SKU
        issue = body["stock_issue"]
        assert issue["sku"] == SKU
        assert issue["name"] == "Tabatière"
        assert issue["requested_qty"] == 4
        assert issue["available_qty"] == 2
        assert issue["line_qty"] is None
        assert issue["line_id"] == line_id
        assert issue["is_notifiable"] is True
        assert issue["shortage_title"]
        assert isinstance(issue["substitutes"], list)
        refs = [action["ref"] for action in issue["actions"]]
        assert "set_available_qty" in refs
        assert "notify_when_available" in refs

    def test_the_bag_is_left_as_she_left_it(self):
        _world(on_shelf="5")
        client = _customer_client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(3)

        _checkout(client)

        assert _line(client)["qty"] == 4

    def test_nothing_left_still_brings_the_way_back(self):
        _world(on_shelf="4")
        client = _customer_client()
        _set_qty(client, 4)
        _lapse(client)
        _another_customer_takes(4)

        issue = _checkout(client).json()["stock_issue"]

        assert issue["available_qty"] == 0
        assert issue["is_notifiable"] is True
        refs = [action["ref"] for action in issue["actions"]]
        assert "set_available_qty" not in refs
        assert "notify_when_available" in refs
