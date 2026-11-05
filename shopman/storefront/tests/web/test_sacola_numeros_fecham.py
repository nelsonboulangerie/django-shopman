"""Beta 05/11 (MKT-05): na sacola os números não fechavam.

Oferta de valor fixo (R$ 10 no Croissant de R$ 13): o desconto de pedido é
rateado no preço cobrado da linha, e a sacola exibia esse unitário rateado
("2 × R$ 8,00 cada", linha R$ 16,00) sob um Subtotal cheio de R$ 26,00. A
regra agora é uma só: a linha fala o preço CHEIO, o desconto mora no resumo,
a soma das linhas é o Subtotal e o Subtotal menos os descontos é o Total.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from shopman.shop.models import Promotion
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart
from shopman.storefront.tests.web.conftest import _ensure_listing_item, _seed_stock_for_product_sku

pytestmark = pytest.mark.django_db


def _cart(client, sku: str, qty: int):
    client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )
    request = RequestFactory().get("/sacola/")
    request.session = client.session
    return build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)


def _promo(sku: str, *, type_: str, value: int) -> None:
    now = timezone.now()
    Promotion.objects.create(
        ref=f"beta-mkt05-{type_}",
        name="Oferta do Croissant",
        type=type_,
        value=value,
        skus=[sku],
        is_active=True,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )


def _q(display: str) -> int:
    return int(display.replace("R$", "").replace(".", "").replace(",", "").strip())


def _assert_fecha(cart) -> None:
    assert sum(item.total_price_q for item in cart.items) == cart.subtotal_q
    exibido_q = sum(_q(item.total_display) for item in cart.items)
    assert exibido_q == cart.original_subtotal_q, "a soma das linhas exibidas é o Subtotal"
    descontos_q = sum(row.amount_q for row in cart.discount_lines)
    assert cart.original_subtotal_q - descontos_q == cart.grand_total_q


@pytest.mark.parametrize("qty", [1, 2])
def test_oferta_de_valor_fixo_nao_rateia_no_preco_exibido(client, channel, croissant, qty):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=1300)
    _promo(croissant.sku, type_=Promotion.FIXED, value=1000)

    cart = _cart(client, croissant.sku, qty)

    assert cart.has_discount, "setup: a oferta tem de valer"
    item = cart.items[0]
    assert item.price_display == "R$ 13,00"
    assert item.total_display == f"R$ {13 * qty},00"
    assert cart.original_subtotal_display == f"R$ {13 * qty},00"
    assert cart.grand_total_q == 1300 * qty - 1000
    _assert_fecha(cart)


def test_promocao_por_item_tambem_fecha(client, channel, croissant):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=1600)
    _promo(croissant.sku, type_=Promotion.PERCENT, value=15)

    cart = _cart(client, croissant.sku, 2)

    assert cart.has_discount, "setup: a promoção tem de valer"
    assert cart.items[0].price_display == "R$ 16,00"
    assert cart.grand_total_q == 2720
    _assert_fecha(cart)
