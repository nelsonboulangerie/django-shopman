"""Vínculo N:N cliente <-> grupo comercial (decisão do dono, 14/10/2026).

O cliente pode pertencer a mais de um grupo; o grupo primário (maior prioridade) é
derivado, e a lista é a fonte canônica.
"""

import pytest
from shopman.guestman.models import Customer, PriceTier

pytestmark = pytest.mark.django_db


def test_customer_belongs_to_more_than_one_group(tier_regular, tier_vip):
    customer = Customer.objects.create(
        ref="CUST-MULTI", first_name="Ana", price_tiers=[tier_regular, tier_vip]
    )

    assert set(customer.price_tiers.values_list("ref", flat=True)) == {"regular", "vip"}
    # vip tem priority 10; regular, 0.
    assert customer.primary_price_tier == tier_vip
    assert customer.primary_price_tier_id == tier_vip.pk
    # A lista de preço vem do grupo de maior prioridade que tem uma.
    assert customer.listing_ref == "vip"


def test_manager_accepts_a_single_group(tier_regular):
    customer = Customer.objects.create(ref="CUST-ONE", first_name="Bia", price_tiers=tier_regular)

    assert list(customer.price_tiers.values_list("ref", flat=True)) == ["regular"]


def test_new_customer_gets_the_default_group(tier_regular):
    customer = Customer.objects.create(ref="CUST-DEFAULT", first_name="Caio")

    assert list(customer.price_tiers.values_list("ref", flat=True)) == ["regular"]
    assert customer.primary_price_tier == tier_regular


def test_clearing_groups_leaves_no_primary(tier_regular):
    customer = Customer.objects.create(ref="CUST-NONE", first_name="Dora", price_tiers=[])

    assert list(customer.price_tiers.values_list("ref", flat=True)) == []
    assert customer.primary_price_tier is None
    assert customer.primary_price_tier_id is None
    assert customer.listing_ref is None
