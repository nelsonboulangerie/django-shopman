"""Fila de espera — admissão até o limite conhecido (WP-P2E F1).

O beco que estes testes fecham: fornada planejada para uma data FUTURA não
contava nada para o cliente. ``quants_eligible_for`` corta ``target_date >
target`` e toda leitura da loja perguntava por HOJE, então o balde
``planned`` chegava zerado, o item lia "Esgotado" e o 409 dizia "acabou" —
enquanto a loja prometia lista de espera. Com ``waitlist.enabled``, a
leitura passa a perguntar pelo HORIZONTE do canal e a fornada de amanhã
volta a ser promessa: entra na fila até o limite, e nem uma unidade além.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart
from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db

TOMORROW = timedelta(days=1)


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _enable_waitlist(channel, *, horizon_days: int = 2):
    channel.config = {
        **(channel.config or {}),
        "waitlist": {"enabled": True, "horizon_days": horizon_days},
    }
    channel.save(update_fields=["config"])


def _plan_tomorrow(product, qty: str):
    stock.plan(
        quantity=Decimal(qty),
        product=product,
        target_date=date.today() + TOMORROW,
        position=_position(),
        reason="fornada de amanhã (teste fila)",
    )


def _set_qty(client, sku, qty):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def _cart(client):
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.get("/carrinho/")
    request.session = client.session  # type: ignore[attr-defined]
    return build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)


class TestWaitlistDisabledKeepsTodaysBehaviour:
    def test_future_batch_promises_nothing_when_waitlist_is_off(
        self, client, channel, product,
    ):
        _ensure_listing_item(channel, product, price_q=90)
        _plan_tomorrow(product, "10")

        resp = _set_qty(client, product.sku, 2)

        assert resp.status_code == 409, "fila desligada: fornada de amanhã não promete nada"
        assert resp.json()["available_qty"] == 0


class TestWaitlistAdmitsUpToTheKnownLimit:
    def test_expired_hold_does_not_hide_fresh_zero_day_stock(
        self, client, channel, product,
    ):
        """A sacola volta a oferecer a produção fresca após o hold expirar.

        O cardápio já lia o pronto para hoje separado da próxima fornada. A
        sacola passava o horizonte inteiro ao Stockman; em produto com validade
        zero, isso descartava o estoque de hoje e mantinha a linha bloqueada.
        """
        from django.utils import timezone

        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        product.shelf_life_days = 0
        product.save(update_fields=["shelf_life_days"])
        stock.receive(
            quantity=Decimal("3"),
            sku=product.sku,
            position=_position(),
            target_date=date.today(),
            reason="produção fresca antes do hold",
        )

        assert _set_qty(client, product.sku, 3).status_code in (200, 201)
        Hold.objects.filter(sku=product.sku).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        stock.receive(
            quantity=Decimal("3"),
            sku=product.sku,
            position=_position(),
            target_date=date.today(),
            reason="reposição fresca após hold vencido",
        )

        from shopman.shop.services import availability

        decision = availability.decide(
            product.sku, Decimal("3"), channel_ref=STOREFRONT_CHANNEL_REF,
        )
        proj = _cart(client)

        assert decision["approved"] is True
        assert decision["available_qty"] == Decimal("6")
        assert decision["target_date"] == date.today()
        assert proj.items[0].is_available is True
        assert proj.items[0].available_qty == 6
        assert proj.has_unavailable_items is False
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.enabled is True

    def test_future_batch_admits_and_creates_a_fermata_hold(
        self, client, channel, product,
    ):
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        _plan_tomorrow(product, "10")

        resp = _set_qty(client, product.sku, 2)

        assert resp.status_code in (200, 201), resp.content[:400]
        hold = Hold.objects.get(sku=product.sku)
        assert hold.quantity == Decimal("2")
        assert hold.expires_at is None, "reserva de fila é fermata: não corre TTL"
        assert hold.metadata.get("planned") is True
        assert hold.target_date == date.today() + TOMORROW, (
            "o hold ancora na fornada, não no horizonte — a sacola promete o dia certo"
        )

    def test_cart_line_carries_the_queue_capacity_and_does_not_block_checkout(
        self, client, channel, product,
    ):
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        _plan_tomorrow(product, "10")

        assert _set_qty(client, product.sku, 2).status_code in (200, 201)
        proj = _cart(client)

        assert len(proj.items) == 1
        item = proj.items[0]
        assert item.is_awaiting_confirmation is True
        assert item.available_qty == 10, (
            "o stepper enxerga a fornada inteira — antes lia ready_physical e travava em 0"
        )
        assert proj.has_unavailable_items is False
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.enabled is True
        assert item.planned_for_date == (date.today() + TOMORROW).isoformat()

    def test_beyond_the_limit_is_refused_as_a_planned_offer_not_as_sold_out(
        self, client, channel, product,
    ):
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        _plan_tomorrow(product, "3")

        resp = _set_qty(client, product.sku, 4)

        assert resp.status_code == 409, "a fila tem limite: 4 não cabe numa fornada de 3"
        body = resp.json()
        assert body["available_qty"] == 3
        assert body["is_planned"] is True, (
            "recusa honesta de fila: 'próximo lote', não 'o último acabou de sair'"
        )
        assert body["planned_offer_title"]

    def test_the_queue_is_first_come_first_served(self, client, channel, product):
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        _plan_tomorrow(product, "3")

        from shopman.shop.services import availability as av

        first = av.reserve(
            product.sku, Decimal("3"),
            session_key="quem-chegou-antes", channel_ref=STOREFRONT_CHANNEL_REF,
        )
        assert first["ok"] is True

        resp = _set_qty(client, product.sku, 1)

        assert resp.status_code == 409, "fornada esgotada na fila não admite mais ninguém"
        assert resp.json()["available_qty"] == 0
