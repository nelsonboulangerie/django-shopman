"""Cupom na sacola sem desconto diz POR QUÊ (beta 06/11).

O navegador adivinhava: todo desconto zero virava "nenhum item recebe o desconto".
PRIMEIRACOMPRA (R$ 5, mínimo R$ 30) numa sacola de R$ 18,70 mostrava essa frase,
quando o que faltava era R$ 11,30. Quem sabe o motivo é o ``DiscountModifier``,
que grava ``pricing.coupon.reason`` e a projeção da sacola entrega.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Coupon, Promotion, Shop
from shopman.shop.projections.cart import _coupon
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db


def _promo(*, code: str, **fields) -> Promotion:
    Shop.objects.get_or_create(name="Test Shop")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    for sku in ("PAO", "BOLO"):
        Product.objects.get_or_create(
            sku=sku,
            defaults={"name": sku, "base_price_q": 1870, "is_published": True, "is_sellable": True},
        )
    now = timezone.now()
    defaults = {"name": "Cupom", "type": Promotion.FIXED, "value": 500}
    defaults.update(fields)
    promo = Promotion.objects.create(
        ref=f"cupom-{code.lower()}",
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        **defaults,
    )
    Coupon.objects.create(code=code, promotion=promo, max_uses=1, is_active=True)
    return promo


def _auto_promo(ref: str, **fields) -> None:
    now = timezone.now()
    Promotion.objects.create(
        ref=ref,
        name=ref,
        type=Promotion.PERCENT,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        **fields,
    )


def _cart(code: str, *, qty: int = 1, sku: str = "PAO", fulfillment: str = "pickup"):
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": sku, "name": sku, "qty": qty, "unit_price_q": 1870},
            {"op": "set_data", "path": "fulfillment_type", "value": fulfillment},
            {"op": "set_data", "path": "coupon_code", "value": code},
        ],
    )
    session.refresh_from_db()
    return session


def test_minimum_not_reached_says_how_much_is_missing():
    _promo(code="PRIMEIRACOMPRA", min_order_q=3000)
    session = _cart("PRIMEIRACOMPRA")

    coupon = session.pricing["coupon"]
    assert coupon == {"code": "PRIMEIRACOMPRA", "discount_q": 0, "reason": "minimum", "missing_q": 1130}
    projection = _coupon(session.data, session.pricing)
    assert (projection.zero_reason, projection.missing_q) == ("minimum", 1130)


def test_minimum_reached_applies_and_carries_no_reason():
    _promo(code="PRIMEIRACOMPRA", min_order_q=3000)
    session = _cart("PRIMEIRACOMPRA", qty=2)

    assert session.pricing["coupon"] == {"code": "PRIMEIRACOMPRA", "discount_q": 500}
    assert _coupon(session.data, session.pricing).zero_reason == ""


def test_no_line_in_the_coupon_target():
    _promo(code="SOBOLO", type=Promotion.PERCENT, value=10, skus=["BOLO"])
    session = _cart("SOBOLO", sku="PAO")

    assert session.pricing["coupon"]["reason"] == "items"


def test_line_already_has_a_bigger_discount():
    _promo(code="DEZ", type=Promotion.PERCENT, value=10)
    _auto_promo("auto-vinte", value=20)
    session = _cart("DEZ")

    assert session.pricing["coupon"]["reason"] == "already_discounted"


def test_delivery_only_coupon_on_pickup_names_where_it_applies():
    _promo(code="ENTREGA", fulfillment_types=["delivery"])
    session = _cart("ENTREGA", fulfillment="pickup")

    assert session.pricing["coupon"]["reason"] == "fulfillment"
    assert session.pricing["coupon"]["fulfillment_types"] == ["delivery"]


def test_exhausted_coupon_is_unavailable():
    _promo(code="ESGOTADO")
    Coupon.objects.filter(code="ESGOTADO").update(uses_count=1)
    # Uma promoção automática no ar (noutro item): o bloco do cupom é escrito.
    _auto_promo("auto-outra", value=5, skus=["BOLO"])
    session = _cart("ESGOTADO")

    assert session.pricing["coupon"]["reason"] == "unavailable"
