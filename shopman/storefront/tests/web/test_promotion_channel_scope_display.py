"""A vitrine só pode anunciar o preço que o caixa honra.

Este arquivo existe porque a suíte nunca comparou a projeção da VITRINE com a do
CARRINHO para a MESMA promoção **sob escopo de canal**. Os testes de promoção
exercitavam o ``DiscountModifier`` (que filtra por canal desde sempre) e os do
catálogo usavam promoções sem ``channels``, onde os dois motores concordam por
acidente. No vão entre eles cabia o defeito de produção:

- ``catalog._active_storefront_promotions`` montava a própria query e nunca chamava
  ``applies_to_channel``, apesar do docstring prometer "the channel's promotions";
- ``adapters/pricing`` repetia a mesma query no fallback de SKU avulso (a PDP);
- ``services/fomo`` repetia de novo, no badge cujo docstring diz que "badge de
  vitrine é promessa".

Com uma promoção de 30% restrita ao PDV, a loja online mostrava ~~R$ 6,00~~ R$ 4,20
com selo −30% e a sacola cobrava R$ 6,00 — sem erro de JS e sem resposta não-2xx. A
guarda de ``expected_total_q`` não pega: o carrinho está internamente coerente, e a
mentira acontece uma tela antes.

Todo teste daqui vem com **controle positivo**: a mesma promoção sem ``channels``
tem que aparecer nas três telas. Afirmar ausência sem provar que a presença é
detectável não prova nada.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem

from shopman.shop.models import Channel, Promotion
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

pytestmark = pytest.mark.django_db


def _publish(listing, product) -> None:
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={
            "price_q": product.base_price_q,
            "is_published": True,
            "is_sellable": True,
        },
    )


def _promotion(ref: str, *, sku: str, channel_refs: list[str] | None = None) -> Promotion:
    now = timezone.now()
    promo = Promotion.objects.create(
        ref=ref,
        name=f"Relâmpago {ref}",
        # ⚠️ O valor é ``percent``, NÃO "percentage" — uma promoção com type
        # desconhecido simplesmente não compete e o teste passaria verde provando
        # nada.
        type=Promotion.PERCENT,
        value=30,
        skus=[sku],
        is_active=True,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )
    if channel_refs:
        promo.channels.set(list(Channel.objects.filter(ref__in=channel_refs)))
    return promo


def _vitrine_price_q(sku: str) -> tuple[int, bool]:
    from shopman.storefront.presentation import build_catalog_items_for_skus

    item = build_catalog_items_for_skus([sku], channel_ref=STOREFRONT_CHANNEL_REF)[0]
    return item.base_price_q, item.has_promotion


def _pdp_price_q(sku: str) -> tuple[int, bool]:
    from shopman.storefront.presentation.product_detail import build_product_detail

    pdp = build_product_detail(sku=sku, channel_ref=STOREFRONT_CHANNEL_REF)
    assert pdp is not None, "a PDP precisa existir, senão o teste não prova nada"
    return pdp.base_price_q, pdp.has_promotion


def _cart_unit_price_q(client, sku: str) -> int:
    from shopman.shop.projections.cart import build_cart as build_cart_data

    response = client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
    )
    assert response.status_code < 400, response.status_code
    cart = build_cart_data(client.session.get("cart_session_key"), STOREFRONT_CHANNEL_REF)
    line = next(line for line in cart.lines if line.sku == sku)
    return line.unit_price_q


def _badge_promotion_names(sku: str) -> list[str]:
    from shopman.shop.services import fomo

    context = fomo.context_for_sku(sku, channel_ref=STOREFRONT_CHANNEL_REF)
    return [p["name"] for p in context["promotions"]]


class TestPromotionScopedToAnotherChannel:
    """Promoção restrita ao PDV: nada na loja online pode anunciá-la."""

    def test_menu_card_pdp_and_cart_agree(
        self, client, channel, listing, collection, collection_item, product,
    ):
        _publish(listing, product)
        Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
        _promotion("so-no-pdv", sku=product.sku, channel_refs=["pdv"])

        vitrine_q, vitrine_promo = _vitrine_price_q(product.sku)
        pdp_q, pdp_promo = _pdp_price_q(product.sku)
        cart_q = _cart_unit_price_q(client, product.sku)

        # A conta que o cliente confere: as três telas dizem o MESMO preço.
        assert vitrine_q == pdp_q == cart_q == product.base_price_q
        assert vitrine_promo is False, "o card não pode mostrar selo de desconto"
        assert pdp_promo is False, "a PDP não pode mostrar selo de desconto"

    def test_no_urgency_badge_for_a_promotion_of_another_channel(
        self, channel, listing, collection, collection_item, product,
    ):
        _publish(listing, product)
        Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
        _promotion("so-no-pdv", sku=product.sku, channel_refs=["pdv"])

        assert _badge_promotion_names(product.sku) == []


class TestPositiveControl:
    """Controle positivo: sem ``channels``, a MESMA promoção aparece nas três telas.

    Sem isto, os testes acima passariam mesmo se a projeção tivesse parado de
    resolver promoção nenhuma — que é o vício de afirmar ausência.
    """

    def test_unscoped_promotion_shows_everywhere_and_the_cart_honors_it(
        self, client, channel, listing, collection, collection_item, product,
    ):
        _publish(listing, product)
        _promotion("para-todos", sku=product.sku)

        discounted_q = product.base_price_q - (product.base_price_q * 30 // 100)

        vitrine_q, vitrine_promo = _vitrine_price_q(product.sku)
        pdp_q, pdp_promo = _pdp_price_q(product.sku)
        cart_q = _cart_unit_price_q(client, product.sku)

        assert vitrine_promo is True
        assert pdp_promo is True
        assert vitrine_q == pdp_q == cart_q == discounted_q

    def test_promotion_scoped_to_this_channel_shows_and_is_charged(
        self, client, channel, listing, collection, collection_item, product,
    ):
        _publish(listing, product)
        _promotion("so-na-web", sku=product.sku, channel_refs=[STOREFRONT_CHANNEL_REF])

        discounted_q = product.base_price_q - (product.base_price_q * 30 // 100)

        vitrine_q, _ = _vitrine_price_q(product.sku)
        pdp_q, _ = _pdp_price_q(product.sku)
        cart_q = _cart_unit_price_q(client, product.sku)

        assert vitrine_q == pdp_q == cart_q == discounted_q

    def test_badge_appears_for_an_unscoped_promotion(
        self, channel, listing, collection, collection_item, product,
    ):
        _publish(listing, product)
        promo = _promotion("para-todos", sku=product.sku)

        assert _badge_promotion_names(product.sku) == [promo.name]
