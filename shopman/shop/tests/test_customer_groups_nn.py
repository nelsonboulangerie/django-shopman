"""Cliente em MAIS DE UM grupo: melhor vantagem por tipo, sem acumular.

Decisão do dono (14/10/2026): dois descontos não somam. Equipe (−30%) e Aliança
(−15%) concorrem; o cliente leva os −30%. O arredondamento e o tipo do desconto
vêm do grupo VENCEDOR da linha, não do grupo primário.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import promotions
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

SKU = "PAO-NN"


def _seed(*, base_q: int = 1000):
    Shop.objects.create(name="Test")
    Channel.objects.create(ref="web", name="web", config={})
    product = Product.objects.create(
        sku=SKU, name="Pão", base_price_q=base_q, is_published=True, is_sellable=True
    )
    listing = Listing.objects.create(ref="web", name="web", is_active=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=base_q, is_sellable=True)
    equipe = PriceTier.objects.create(
        ref="equipe",
        name="Equipe",
        priority=0,
        metadata={"discount_kind": "equipe", "rounding": 50, "savings_message": "Equipe: {amount}"},
    )
    alianca = PriceTier.objects.create(
        ref="alianca-francesa",
        name="Aliança Francesa",
        priority=10,
        listing_ref="atacado",
        metadata={"discount_kind": "parceiro", "rounding": 0},
    )
    now = timezone.now()
    Promotion.objects.create(
        ref="grupo-equipe",
        name="Equipe",
        type=Promotion.PERCENT,
        value=30,
        customer_segments=["equipe"],
        is_active=True,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Promotion.objects.create(
        ref="grupo-alianca-francesa",
        name="Aliança Francesa",
        type=Promotion.PERCENT,
        value=15,
        customer_segments=["alianca-francesa"],
        is_active=True,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    PriceTierAdvantage.objects.create(
        tier=alianca, kind="free_shipping", priority=0, config={"min_order_q": 0}
    )
    PriceTierAdvantage.objects.create(
        tier=equipe, kind="free_shipping", priority=5, config={"min_order_q": 5000}
    )
    customer = Customer.objects.create(
        ref="CUST-NN", first_name="Ana", price_tiers=[equipe, alianca]
    )
    return equipe, alianca, customer


def _reprice(customer_ref: str):
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": SKU, "name": "Pão", "qty": 1, "unit_price_q": 1000},
            {
                "op": "set_data",
                "path": "customer",
                "value": {
                    "ref": customer_ref,
                    "price_tiers": ["equipe", "alianca-francesa"],
                    "price_tier": "alianca-francesa",
                    "name": "Ana",
                },
            },
        ],
    )
    return cart_service.get_open_session(session_key=session.session_key, channel_ref="web")


def test_two_group_discounts_do_not_add_up():
    _seed()
    session = _reprice("CUST-NN")

    item = session.items[0]
    # Equipe 30% (700) vence Aliança 15% (850). NÃO soma 45% (550).
    assert item["unit_price_q"] == 700
    savings = session.pricing["discount"]["savings"]
    assert savings["kind"] == "equipe"
    assert savings["group"] == "Equipe"
    assert savings["amount_q"] == 300


def test_rounding_comes_from_the_winning_group_not_the_primary():
    _seed(base_q=1030)
    # O primário é a Aliança (priority 10, sem arredondamento), mas quem vence a
    # linha é a Equipe (30%, passo 50): 1030 → 721 → 700.
    session = _reprice("CUST-NN")
    assert session.items[0]["unit_price_q"] == 700


def test_best_group_promotion_is_the_best_discount():
    _seed()
    promo = promotions.customer_group_promotion(
        ["equipe", "alianca-francesa"], channel_ref="web"
    )

    assert promo is not None
    assert promo.ref == "grupo-equipe"
    assert promo.value == 30


def test_best_typed_advantage_by_priority():
    _seed()
    best = promotions.best_group_advantage(
        ["equipe", "alianca-francesa"], "free_shipping"
    )

    assert best is not None
    assert best.tier_ref == "equipe"  # prioridade 5 > 0
    assert best.value.config["min_order_q"] == 5000


def test_best_price_list_uses_the_priority_order():
    _seed()
    best = promotions.best_group_advantage(
        ["equipe", "alianca-francesa"], "price_list"
    )

    assert best is not None
    assert best.value == "atacado"
    assert best.tier_ref == "alianca-francesa"


def test_advantage_kind_without_rows_is_none():
    _seed()
    assert promotions.best_group_advantage(["equipe"], "exclusive_collections") is None
