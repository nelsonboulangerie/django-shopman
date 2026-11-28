"""Na sacola os números fecham: a soma das linhas é o Subtotal.

Beta 05/11 (MKT-05): oferta de valor fixo (R$ 10 no Croissant de R$ 13) é
desconto de PEDIDO; o motor a rateia no preço cobrado, e a sacola exibia esse
unitário rateado ("2 × R$ 8,00 cada", linha R$ 16,00) sob um Subtotal de
R$ 26,00. Desconto de pedido nunca vira preço de linha: mora no resumo.

Decisão do dono 1 (16/11/2026, plano EXCELENCIA-STOREFRONT, P1-05): a promoção
do PRODUTO abate na linha. O unitário e o total da linha falam o preço com
desconto, cada um com o cheio riscado ao lado; o Subtotal é a soma das linhas
como a tela as mostra; o resumo diz quanto a promoção economizou e só subtrai
cupom, pontos e desconto de pedido.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from shopman.shop.models import Coupon, Promotion
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
    """Linhas, Subtotal, descontos do resumo e Total contam a mesma conta."""
    assert sum(item.total_price_q for item in cart.items) == cart.subtotal_q
    exibido_q = sum(_q(item.line_total_display) for item in cart.items)
    assert exibido_q == cart.lines_subtotal_q, "a soma das linhas exibidas é o Subtotal"
    assert _q(cart.lines_subtotal_display) == cart.lines_subtotal_q
    resumo_q = sum(row.amount_q for row in cart.order_discount_lines)
    assert cart.lines_subtotal_q - resumo_q == cart.subtotal_q
    assert cart.subtotal_q + (cart.delivery_fee_q or 0) == cart.grand_total_q
    assert cart.promo_savings_q + resumo_q == cart.discount_total_q, (
        "o que abateu nas linhas mais o que o resumo subtrai é todo o desconto"
    )


@pytest.mark.parametrize("qty", [1, 2])
def test_oferta_de_valor_fixo_nao_rateia_no_preco_exibido(client, channel, croissant, qty):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=1300)
    _promo(croissant.sku, type_=Promotion.FIXED, value=1000)

    cart = _cart(client, croissant.sku, qty)

    assert cart.has_discount, "setup: a oferta tem de valer"
    item = cart.items[0]
    assert item.price_display == "R$ 13,00"
    assert item.promo_price_display is None
    assert item.line_total_display == f"R$ {13 * qty},00"
    assert item.line_total_struck_display is None
    assert cart.lines_subtotal_display == f"R$ {13 * qty},00"
    assert cart.promo_savings_display is None
    assert [(row.label, row.amount_q) for row in cart.order_discount_lines] == [
        ("Oferta do Croissant", 1000)
    ]
    assert cart.grand_total_q == 1300 * qty - 1000
    _assert_fecha(cart)


def test_promocao_por_item_tambem_fecha(client, channel, croissant):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=1600)
    _promo(croissant.sku, type_=Promotion.PERCENT, value=15)

    cart = _cart(client, croissant.sku, 2)

    assert cart.has_discount, "setup: a promoção tem de valer"
    item = cart.items[0]
    assert item.price_display == "R$ 16,00"
    assert item.promo_price_display == "R$ 13,60"
    assert item.line_total_display == "R$ 27,20"
    assert item.line_total_struck_display == "R$ 32,00"
    assert cart.lines_subtotal_display == "R$ 27,20"
    assert cart.promo_savings_display == "R$ 4,80"
    assert cart.order_discount_lines == (), "a promoção já abateu na linha"
    assert cart.grand_total_q == 2720
    _assert_fecha(cart)


def test_linha_com_promocao_mostra_o_preco_do_cardapio(client, channel, croissant):
    """Beta 06/11: o cardápio dizia R$ 5,10 (-15%) e a linha só "1 × R$ 6,00".

    A linha repete a dupla do cardápio (cheio riscado, promoção ao lado) no
    unitário e no total: "1 × R$ 6,00 R$ 5,10" à esquerda e, à direita, o
    mesmo R$ 5,10 com o R$ 6,00 riscado (P1-05: antes o total dizia R$ 6,00).
    """
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=600)
    _promo(croissant.sku, type_=Promotion.PERCENT, value=15)

    cart = _cart(client, croissant.sku, 1)

    item = cart.items[0]
    assert item.price_display == "R$ 6,00"
    assert item.promo_price_display == "R$ 5,10"
    assert item.discount_label == "Oferta do Croissant"
    assert item.line_total_display == "R$ 5,10"
    assert item.line_total_struck_display == "R$ 6,00"
    assert item.list_price_q == 600
    _assert_fecha(cart)


def test_oferta_de_valor_fixo_nao_vira_preco_de_linha(client, channel, croissant):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=1300)
    _promo(croissant.sku, type_=Promotion.FIXED, value=1000)

    cart = _cart(client, croissant.sku, 2)

    assert cart.items[0].promo_price_display is None


def test_sem_desconto_o_resumo_nao_inventa_linha(client, channel, croissant):
    _seed_stock_for_product_sku(croissant.sku)
    _ensure_listing_item(channel, croissant, price_q=600)

    cart = _cart(client, croissant.sku, 3)

    item = cart.items[0]
    assert item.line_total_display == "R$ 18,00"
    assert item.line_total_struck_display is None
    assert cart.lines_subtotal_display == "R$ 18,00"
    assert cart.promo_savings_display is None
    assert cart.order_discount_lines == ()
    _assert_fecha(cart)


def test_promocao_na_linha_e_cupom_no_resumo(client, channel, croissant, product):
    """Uma linha em promoção e outra só com cupom: cada desconto no seu lugar.

    A promoção do Croissant abate na linha dele; o cupom, que é do pedido, só
    aparece no resumo, e o resumo não subtrai a promoção de novo.
    """
    _seed_stock_for_product_sku(croissant.sku)
    _seed_stock_for_product_sku(product.sku)
    _ensure_listing_item(channel, croissant, price_q=600)
    _ensure_listing_item(channel, product, price_q=1000)
    _promo(croissant.sku, type_=Promotion.PERCENT, value=15)
    now = timezone.now()
    coupon_promo = Promotion.objects.create(
        ref="beta-l03-cupom",
        name="Boas-vindas",
        type=Promotion.PERCENT,
        value=10,
        skus=[product.sku],
        is_active=True,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )
    Coupon.objects.create(code="BEMVINDA", promotion=coupon_promo, max_uses=0)

    _cart(client, croissant.sku, 1)
    _cart(client, product.sku, 2)
    applied = client.post(
        "/api/v1/cart/coupon/",
        data=json.dumps({"code": "BEMVINDA"}),
        content_type="application/json",
    )
    assert applied.status_code == 200, applied.content
    request = RequestFactory().get("/sacola/")
    request.session = client.session
    cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

    by_sku = {item.sku: item for item in cart.items}
    promo_line = by_sku[croissant.sku]
    assert promo_line.line_total_display == "R$ 5,10"
    assert promo_line.line_total_struck_display == "R$ 6,00"
    coupon_line = by_sku[product.sku]
    assert coupon_line.promo_price_display is None, "cupom não vira preço de linha"
    assert coupon_line.line_total_display == "R$ 20,00"
    assert coupon_line.line_total_struck_display is None

    assert cart.lines_subtotal_display == "R$ 25,10"
    assert cart.promo_savings_display == "R$ 0,90"
    assert [(row.label, row.amount_q) for row in cart.order_discount_lines] == [
        ("Cupom BEMVINDA", 200)
    ]
    assert cart.grand_total_q == 2310
    _assert_fecha(cart)
