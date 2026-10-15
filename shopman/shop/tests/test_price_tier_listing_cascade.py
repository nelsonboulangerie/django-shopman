"""Cascata "faixa do cliente -> listing" de ponta a ponta (decisão do dono, 14/10).

O canônico é ``offerman.Listing`` (o preço) apontado por
``guestman.PriceTier.listing_ref`` (de quem é), orquestrado pela cascata de
``shop/handlers/pricing.py``. Até aqui a ponta do cliente nunca era ligada:
``ctx["customer"]`` ficava vazio em todo chamador e a faixa não mudava preço
nenhum. O ``CustomerPricingModifier`` (ordem 5) resolve o cliente da sessão
uma vez, em QUALQUER canal, e o preço em lote lê a faixa dele.
"""

from __future__ import annotations

import pytest
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Shop
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

SKU = "PAO-FAIXA"
CHANNEL_PRICE_Q = 1000
TIER_PRICE_Q = 800


def _seed(*, tier_listing: bool = True) -> PriceTier:
    Shop.objects.create(name="Test")
    for ref in ("web", "pdv"):
        Channel.objects.create(ref=ref, name=ref, config={})
    product = Product.objects.create(
        sku=SKU, name="Pão", base_price_q=CHANNEL_PRICE_Q, is_published=True, is_sellable=True
    )
    for ref in ("web", "pdv"):
        listing = Listing.objects.create(ref=ref, name=ref, is_active=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=CHANNEL_PRICE_Q, is_sellable=True)
    tier = PriceTier.objects.create(ref="vip", name="VIP", listing_ref="vip" if tier_listing else "")
    if tier_listing:
        listing = Listing.objects.create(ref="vip", name="VIP", is_active=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=TIER_PRICE_Q, is_sellable=True)
    return tier


def _open_session(channel_ref: str, *, customer_ref: str | None, tier_ref: str = "vip") -> str:
    session = sessions.create_session(channel_ref)
    ops: list[dict] = [
        {"op": "add_line", "sku": SKU, "name": "Pão", "qty": 1, "unit_price_q": CHANNEL_PRICE_Q},
    ]
    if customer_ref:
        ops.append({
            "op": "set_data",
            "path": "customer",
            "value": {"ref": customer_ref, "price_tier": tier_ref, "name": "Aluno"},
        })
    sessions.modify_session(session_key=session.session_key, channel_ref=channel_ref, ops=ops)
    return session.session_key


def _unit_price_q(session_key: str, channel_ref: str) -> int:
    session = cart_service.get_open_session(session_key=session_key, channel_ref=channel_ref)
    return int((session.items or [{}])[0].get("unit_price_q", 0))


def _customer(tier: PriceTier) -> Customer:
    return Customer.objects.create(ref="CUST-VIP", first_name="Ana", price_tiers=tier)


@pytest.mark.parametrize("channel_ref", ["web", "pdv"])
def test_identified_customer_gets_the_tier_listing_price(channel_ref):
    """A loja online E o PDV pagam a tabela do grupo, não a do canal."""
    tier = _seed()
    _customer(tier)

    session_key = _open_session(channel_ref, customer_ref="CUST-VIP")

    assert _unit_price_q(session_key, channel_ref) == TIER_PRICE_Q


def test_anonymous_pays_the_channel_listing():
    """Sem cliente identificado, o cardápio anônimo continua o do canal."""
    _seed()

    session_key = _open_session("web", customer_ref=None)

    assert _unit_price_q(session_key, "web") == CHANNEL_PRICE_Q


def test_tier_without_item_falls_back_to_the_channel_listing():
    """A faixa sem o SKU não zera o preço: cai na vitrine do canal."""
    tier = _seed(tier_listing=False)
    _customer(tier)

    session_key = _open_session("web", customer_ref="CUST-VIP")

    assert _unit_price_q(session_key, "web") == CHANNEL_PRICE_Q


def test_reprice_keeps_the_tier_price():
    """Reprecificar (cada mexida na sacola) não perde a faixa."""
    tier = _seed()
    _customer(tier)

    session_key = _open_session("web", customer_ref="CUST-VIP")
    cart_service.reprice(session_key=session_key, channel_ref="web")

    assert _unit_price_q(session_key, "web") == TIER_PRICE_Q


def _seed_many(count: int) -> PriceTier:
    Shop.objects.create(name="Test")
    Channel.objects.create(ref="web", name="web", config={})
    channel_listing = Listing.objects.create(ref="web", name="web", is_active=True)
    vip_listing = Listing.objects.create(ref="vip", name="VIP", is_active=True)
    for index in range(count):
        product = Product.objects.create(
            sku=f"SKU-{index}",
            name=f"Item {index}",
            base_price_q=CHANNEL_PRICE_Q,
            is_published=True,
            is_sellable=True,
        )
        ListingItem.objects.create(listing=channel_listing, product=product, price_q=CHANNEL_PRICE_Q, is_sellable=True)
        ListingItem.objects.create(listing=vip_listing, product=product, price_q=TIER_PRICE_Q, is_sellable=True)
    return PriceTier.objects.create(ref="vip", name="VIP", listing_ref="vip")


def test_price_query_count_does_not_grow_with_the_number_of_items():
    """A faixa do cliente é resolvida em LOTE: o número de consultas não cresce
    com o número de itens (mesmo padrão de web/test_catalog_nplus1_measure)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _seed_many(6)
    Customer.objects.create(ref="CUST-VIP", first_name="Ana", price_tiers=PriceTier.objects.get(ref="vip"))

    def price_query_count(item_count: int) -> int:
        session = sessions.create_session("web")
        ops: list[dict] = [
            {"op": "add_line", "sku": f"SKU-{index}", "name": "Item", "qty": 1, "unit_price_q": CHANNEL_PRICE_Q}
            for index in range(item_count)
        ]
        ops.append({
            "op": "set_data",
            "path": "customer",
            "value": {"ref": "CUST-VIP", "price_tier": "vip", "name": "Ana"},
        })
        sessions.modify_session(session_key=session.session_key, channel_ref="web", ops=ops)
        with CaptureQueriesContext(connection) as captured:
            cart_service.reprice(session_key=session.session_key, channel_ref="web")
        return len(captured.captured_queries)

    one_item = price_query_count(1)
    six_items = price_query_count(6)

    # Medição para o relatório (rode com -s): o número NÃO cresce com os itens.
    print(f"\n[preco-por-grupo] consultas no reprice: 1 item={one_item}, 6 itens={six_items}")
    assert six_items == one_item, f"1 item={one_item} consultas, 6 itens={six_items}"
