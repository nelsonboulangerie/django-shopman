"""A elegibilidade de promoção é uma política pura, com uma tabela-verdade só.

Loja online, PDV (carrinho e frete), vitrine (selo FOMO), cupom (inclusive o da
concierge) e anúncio do Marketing perguntam a ``promotion_matches``. Este teste
roda sem Django: ``python -m pytest -p no:django scripts/tests/test_promotion_eligibility_policy.py``.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from shopman.shop.policies.promotion import PromotionContext, Shopper, promotion_matches


def _promo(**overrides):
    base = {
        "skus": [],
        "collections": [],
        "fulfillment_types": [],
        "customer_segments": [],
        "birthday_only": False,
        "min_order_q": 0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


ANON = Shopper()
GROUP = Shopper(tier_refs=frozenset({"equipe"}))
RFM = Shopper(segment="campeao")
BIRTHDAY = Shopper(is_birthday=True)


@pytest.mark.parametrize(
    ("promo", "ctx", "expected"),
    [
        # Aberta a todos: vale em qualquer pergunta.
        (_promo(), PromotionContext(), True),
        (_promo(), PromotionContext(sku="PAO", fulfillment_type="", merchandise_subtotal_q=0), True),
        (_promo(), PromotionContext(sku="PAO", promise_to_any_visitor=True), True),
        # Alvo por cliente: grupo OU segmento RFM; aniversário.
        (_promo(customer_segments=["equipe"]), PromotionContext(), False),
        (_promo(customer_segments=["equipe"]), PromotionContext(shopper=GROUP), True),
        (_promo(customer_segments=["campeao"]), PromotionContext(shopper=RFM), True),
        (_promo(customer_segments=["equipe"]), PromotionContext(shopper=RFM), False),
        (_promo(birthday_only=True), PromotionContext(), False),
        (_promo(birthday_only=True), PromotionContext(shopper=BIRTHDAY), True),
        # Atendimento: fora da pergunta, escolhido, ou ainda não escolhido (retirada é o padrão).
        (_promo(fulfillment_types=["delivery"]), PromotionContext(), True),
        (_promo(fulfillment_types=["delivery"]), PromotionContext(fulfillment_type="delivery"), True),
        (_promo(fulfillment_types=["delivery"]), PromotionContext(fulfillment_type="pickup"), False),
        (_promo(fulfillment_types=["delivery"]), PromotionContext(fulfillment_type=""), False),
        (_promo(fulfillment_types=["pickup"]), PromotionContext(fulfillment_type=""), True),
        (_promo(fulfillment_types=["pickup"]), PromotionContext(fulfillment_type=" delivery "), False),
        # Mínimo: fora da pergunta, ou o subtotal de mercadorias contra ele (inclusivo).
        (_promo(min_order_q=3_000), PromotionContext(), True),
        (_promo(min_order_q=3_000), PromotionContext(merchandise_subtotal_q=2_999), False),
        (_promo(min_order_q=3_000), PromotionContext(merchandise_subtotal_q=3_000), True),
        # Item: SKU e coleção só quando a pergunta é sobre uma linha.
        (_promo(skus=["PAO"]), PromotionContext(), True),
        (_promo(skus=["PAO"]), PromotionContext(sku="PAO"), True),
        (_promo(skus=["PAO"]), PromotionContext(sku="CAFE"), False),
        (_promo(collections=["paes"]), PromotionContext(sku="PAO", sku_collections=("paes",)), True),
        (_promo(collections=["paes"]), PromotionContext(sku="PAO", sku_collections=("bebidas",)), False),
        (_promo(collections=["paes"]), PromotionContext(sku="PAO"), False),
        # Promessa da vitrine: qualquer condição de compra ou de cliente a desfaz.
        (_promo(fulfillment_types=["pickup"]), PromotionContext(sku="PAO", promise_to_any_visitor=True), False),
        (_promo(min_order_q=1), PromotionContext(sku="PAO", promise_to_any_visitor=True), False),
        (_promo(customer_segments=["equipe"]), PromotionContext(sku="PAO", promise_to_any_visitor=True), False),
        (_promo(birthday_only=True), PromotionContext(sku="PAO", promise_to_any_visitor=True), False),
        (_promo(skus=["CAFE"]), PromotionContext(sku="PAO", promise_to_any_visitor=True), False),
    ],
)
def test_promotion_eligibility_truth_table(promo, ctx: PromotionContext, expected: bool) -> None:
    assert promotion_matches(promo, ctx) is expected


@pytest.mark.parametrize(
    ("birthday", "day", "expected"),
    [
        (None, date(2026, 10, 18), False),
        (date(1990, 10, 18), date(2026, 10, 18), True),
        (date(1990, 10, 17), date(2026, 10, 18), False),
        (date(1992, 2, 29), date(2028, 2, 29), True),
    ],
)
def test_birthday_is_the_day_of_the_sale(birthday, day, expected: bool) -> None:
    assert Shopper.birthday_on(birthday, day) is expected
