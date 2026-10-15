"""Preço do grupo: arredondamento, tipo do desconto e economia.

Decisão do dono (14/10/2026): o preço final do grupo cai no R$ X,00 ou R$ X,50
mais próximo, podendo subir ou descer até R$ 0,25. O desconto registra o tipo
(`discount_kind`) para o B.I. e a economia vira mensagem no snapshot do pedido.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Promotion, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

SKU = "PAO-GRUPO"


def _seed(*, base_q: int, percent: int, rounding: int = 50) -> None:
    Shop.objects.create(name="Test")
    Channel.objects.create(ref="web", name="web", config={})
    product = Product.objects.create(
        sku=SKU, name="Pão", base_price_q=base_q, is_published=True, is_sellable=True
    )
    listing = Listing.objects.create(ref="web", name="web", is_active=True)
    ListingItem.objects.create(listing=listing, product=product, price_q=base_q, is_sellable=True)
    tier = PriceTier.objects.create(
        ref="equipe",
        name="Equipe",
        metadata={
            "discount_kind": "equipe",
            "rounding": rounding,
            "savings_message": "Hoje você economizou {amount} por ser da Equipe",
        },
    )
    now = timezone.now()
    Promotion.objects.create(
        ref="grupo-equipe",
        name="Equipe",
        type=Promotion.PERCENT,
        value=percent,
        customer_segments=["equipe"],
        is_active=True,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Customer.objects.create(ref="CUST-EQUIPE", first_name="Ana", price_tiers=tier)


def _price_of(*, base_q: int, percent: int, rounding: int = 50) -> tuple[int, dict]:
    _seed(base_q=base_q, percent=percent, rounding=rounding)
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": SKU, "name": "Pão", "qty": 1, "unit_price_q": base_q},
            {
                "op": "set_data",
                "path": "customer",
                "value": {"ref": "CUST-EQUIPE", "price_tier": "equipe", "name": "Ana"},
            },
        ],
    )
    session = cart_service.get_open_session(session_key=session.session_key, channel_ref="web")
    return int((session.items or [{}])[0].get("unit_price_q", 0)), (session.pricing or {})


@pytest.mark.parametrize(
    "base_q,percent,expected",
    [
        (1000, 15, 850),  # 850 já é múltiplo de 50
        (1010, 15, 850),  # 858,5 desce 8,5 centavos
        (1030, 15, 900),  # 875,5 sobe 24,5 centavos
        (1090, 15, 950),  # 926,5 sobe 23,5 centavos
    ],
)
def test_final_price_rounds_to_the_nearest_50(base_q, percent, expected):
    price_q, _pricing = _price_of(base_q=base_q, percent=percent)
    assert price_q == expected


def test_rounding_off_keeps_the_exact_discount():
    """O `rounding: 0` do grupo desliga o arredondamento (configurável)."""
    price_q, _pricing = _price_of(base_q=1200, percent=15, rounding=0)
    assert price_q == 1020  # 1200 − 15%


def test_rounding_on_rounds_the_exact_discount():
    price_q, _pricing = _price_of(base_q=1200, percent=15, rounding=50)
    assert price_q == 1000  # 1020 desce para o múltiplo de 50 mais perto


def test_discount_kind_and_savings_are_recorded():
    _base, pricing = _price_of(base_q=800, percent=10)
    discount = pricing.get("discount") or {}
    (record,) = discount.get("items") or []
    assert record["discount_kind"] == "equipe"
    savings = discount.get("savings") or {}
    assert savings["amount_q"] == 100
    assert savings["group"] == "Equipe"
    assert savings["kind"] == "equipe"
    assert savings["message"] == "Hoje você economizou R$ 1,00 por ser da Equipe"


def test_anonymous_has_no_group_savings():
    _seed(base_q=800, percent=10)
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[{"op": "add_line", "sku": SKU, "name": "Pão", "qty": 1, "unit_price_q": 800}],
    )
    session = cart_service.get_open_session(session_key=session.session_key, channel_ref="web")
    assert "savings" not in ((session.pricing or {}).get("discount") or {})
