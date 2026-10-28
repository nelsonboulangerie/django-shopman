"""Cupom restrito a grupo/segmento só vale para quem é elegível.

Regressão do audit pré-staging: o cupom FUNCIONARIO (``customer_segments=["staff"]``)
era aceito por qualquer cliente. O modifier não casa o segmento, então o desconto
saía 0 e o cupom "grudava" no carrinho sem aviso. Agora ``apply_coupon`` recusa no
gate (``coupon_not_eligible``) quem não pertence ao grupo/segmento alvo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Coupon, Promotion, Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def funcionario_coupon(db):
    Shop.objects.create(name="Test Shop")
    Channel.objects.create(ref="web", name="Web")
    product = Product.objects.create(
        sku="PAO-CUPOM", name="Pão", base_price_q=2500, is_published=True, is_sellable=True
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    ListingItem.objects.create(
        listing=listing, product=product, price_q=2500, is_published=True, is_sellable=True
    )
    _seed_stock(product.sku)
    now = timezone.now()
    promo = Promotion.objects.create(
        ref="desconto-funcionario",
        name="Desconto Funcionário",
        type=Promotion.PERCENT,
        value=20,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        customer_segments=["staff"],
    )
    return Coupon.objects.create(code="FUNCIONARIO", promotion=promo, max_uses=0)


def _seed_stock(sku: str) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=Decimal("100"), sku=sku, position=position, target_date=date.today(), reason="seed")


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    info = make_identity_view(
        subject_id=customer.uuid, name=customer.name, phone=customer.phone,
        email=getattr(customer, "email", None) or None, is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def _fill_cart(client: Client) -> None:
    client.put(
        "/api/v1/cart/skus/PAO-CUPOM/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
    )


def _apply(client: Client) -> Client:
    return client.post(
        "/api/v1/cart/coupon/",
        data=json.dumps({"code": "FUNCIONARIO"}),
        content_type="application/json",
    )


def test_anonymous_customer_cannot_apply_staff_coupon(client: Client, funcionario_coupon):
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "coupon_rejected"


def test_non_staff_customer_cannot_apply_staff_coupon(client: Client, funcionario_coupon):
    varejo = PriceTier.objects.create(ref="varejo", name="Varejo")
    customer = Customer.objects.create(
        ref="CUS-VAREJO-01", first_name="Cliente", phone="+5543988887777", price_tiers=varejo
    )
    _login_as_customer(client, customer)
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "coupon_rejected"


def test_staff_customer_can_apply_staff_coupon(client: Client, funcionario_coupon):
    staff = PriceTier.objects.create(ref="staff", name="Equipe")
    customer = Customer.objects.create(
        ref="CUS-STAFF-01", first_name="Funcionário", phone="+5543988886666", price_tiers=staff
    )
    _login_as_customer(client, customer)
    _fill_cart(client)
    resp = _apply(client)
    assert resp.status_code == 200
    assert "cart" in resp.json()


# ── Laudo S8 (23/10): balde próprio do cupom, que conta só a recusa ──


@pytest.fixture
def _coupon_bucket():
    from unittest.mock import patch

    from django.core.cache import cache

    cache.clear()
    # Janela fixa: todas as tentativas caem no mesmo minuto do ratelimit.
    with patch("django_ratelimit.core._get_window", return_value=2_000_000_000):
        yield
    cache.clear()


def _try_code(client: Client, code: str):
    return client.post("/api/v1/cart/coupon/", data=json.dumps({"code": code}), content_type="application/json")


def test_guessing_codes_stops_at_the_tenth_rejection(client: Client, funcionario_coupon, _coupon_bucket):
    _fill_cart(client)
    for i in range(10):
        resp = _try_code(client, f"CHUTE{i}")
        assert resp.status_code == 400, i
        assert resp.json()["error_code"] == "coupon_rejected"
    resp = _try_code(client, "CHUTE10")
    assert resp.status_code == 429
    assert resp.json()["error_code"] == "rate_limited"


def test_logged_customer_has_the_same_limit(client: Client, funcionario_coupon, _coupon_bucket):
    customer = Customer.objects.create(ref="CUS-CHUTE-01", first_name="Cliente", phone="+5543988886666")
    _login_as_customer(client, customer)
    _fill_cart(client)
    for i in range(10):
        assert _try_code(client, f"CHUTE{i}").status_code == 400, i
    assert _try_code(client, "CHUTE10").status_code == 429


def test_valid_coupon_does_not_spend_the_bucket(client: Client, funcionario_coupon, _coupon_bucket):
    now = timezone.now()
    promo = Promotion.objects.create(
        ref="aberto", name="Aberto", type=Promotion.PERCENT, value=5,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code="ABERTO", promotion=promo, max_uses=0)
    _fill_cart(client)
    for _ in range(12):
        assert _try_code(client, "ABERTO").status_code == 200
