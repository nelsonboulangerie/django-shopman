"""DiscountModifier: alinhamento vitrine vs carrinho (atendimento).

A elegibilidade é decidida por ``promotion_matches``; o modifier só traduz o seu
contexto de preço (``promotion_context``) e aplica o desconto.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.modifiers import DiscountModifier, promotion_context
from shopman.shop.policies.promotion import promotion_matches


def _promo(**overrides):
    base = {
        "ref": "promo-atendimento",
        "name": "Promoção",
        "type": "percent",
        "value": 10,
        "min_order_q": 0,
        "fulfillment_types": [],
        "skus": [],
        "collections": [],
        "customer_segments": [],
        "birthday_only": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestDiscountModifierMatches:
    def test_fulfillment_promo_does_not_match_when_session_has_no_fulfillment_type(self) -> None:
        """Promo só de entrega não pré-aplica antes de o cliente escolher entrega/retirada."""
        ctx = {
            "fulfillment_type": "",
            "sku_collections": {"CIABATTA": ["paes-artesanais"]},
        }
        promo = _promo(fulfillment_types=["delivery"])
        assert promotion_matches(promo, promotion_context(ctx, sku="CIABATTA")) is False

    def test_fulfillment_promo_rejects_wrong_ft(self) -> None:
        ctx = {"fulfillment_type": "pickup", "sku_collections": {}}
        promo = _promo(fulfillment_types=["delivery"])
        assert promotion_matches(promo, promotion_context(ctx, sku="CIABATTA")) is False

    def test_explicit_fulfillment_still_works(self) -> None:
        ctx = {"fulfillment_type": "delivery", "sku_collections": {}}
        promo = _promo(fulfillment_types=["delivery", "pickup"])
        assert promotion_matches(promo, promotion_context(ctx, sku="X")) is True


@pytest.mark.django_db
def test_modifier_applies_only_the_promotion_the_policy_accepts(monkeypatch) -> None:
    """A linha recebe o desconto da promoção que vale, e não o da só-de-entrega."""
    from shopman.shop.services import promotions as promotion_service

    pickup_only = _promo(ref="so-retirada", name="Retirada", value=10, fulfillment_types=["pickup"])
    delivery_only = _promo(ref="so-entrega", name="Entrega", value=50, fulfillment_types=["delivery"])
    monkeypatch.setattr(
        promotion_service,
        "get_active_promotions",
        lambda *_args, **_kwargs: [pickup_only, delivery_only],
    )
    session = SimpleNamespace(
        data={},
        pricing={},
        items=[{"line_id": "l1", "sku": "PAO", "qty": 1, "unit_price_q": 1_000, "line_total_q": 1_000}],
    )
    session.update_items = lambda items: setattr(session, "items", items)

    DiscountModifier().apply(
        channel=SimpleNamespace(ref="web"),
        session=session,
        ctx={"sku_collections": {"PAO": []}},
    )

    assert session.items[0]["unit_price_q"] == 900
    assert session.items[0]["meta"]["_disc"]
