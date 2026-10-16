"""Persona 3 — funcionário da Nelson (grupo Equipe).

DECISÃO (2026-08-11, Pablo): o funcionário **tem** o desconto na loja pública,
mas **só na retirada**. O benefício é dele; com entrega, o preço de funcionário
viajaria para qualquer endereço e viraria canal de preço para terceiros, sem
ninguém ver — no balcão isso não acontece porque alguém entrega na mão.

A aposentadoria da ``EmployeeRule`` (dono, 14/10/2026) moveu a política para a
promoção do grupo Equipe: ``Promotion.fulfillment_types = ["pickup"]``. O
desconto é automático pela faixa ``staff``, e não há mais duas regras para o
mesmo cliente.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier
from shopman.orderman.models import Order

from shopman.shop.models import Promotion

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-STAFF"


def _seed():
    J.seed_shop()
    J.seed_web_channel(allow_cash=True)
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão", 1000, collection=collection, stock_qty=20)


def _staff_customer():
    tier = PriceTier.objects.create(
        ref="staff",
        name="Equipe",
        metadata={
            "discount_kind": "equipe",
            "rounding": 50,
            "savings_message": "Hoje você economizou {amount} por ser da Equipe",
        },
    )
    return Customer.objects.create(
        ref="CUST-STAFF-1", first_name="Carlos", last_name="Silva",
        phone=J.DEFAULT_PHONE, price_tiers=tier,
    )


@pytest.fixture
def equipe_discount():
    """A promoção do grupo Equipe, como o Admin do grupo a grava."""
    now = timezone.now()
    Promotion.objects.create(
        ref="grupo-staff",
        name="Equipe",
        type=Promotion.PERCENT,
        value=30,
        valid_from=now,
        valid_until=now + timezone.timedelta(days=365),
        customer_segments=["staff"],
        fulfillment_types=["pickup"],
        is_active=True,
    )


# ── the boundary, through the storefront ─────────────────────────────────────


def test_staff_customer_gets_the_discount_on_pickup(client, equipe_discount):
    """Retirada: o funcionário paga R$ 7,00 (30% off) e o pedido FECHA.

    O que a tela mostra é o que o commit cobra — a ``expected_total_q`` do helper
    vem da projeção, então se os dois discordassem o pedido seria recusado com
    ``total_changed``.
    """
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)

    J.set_cart_qty(client, SKU, 1)
    status, order_resp = J.checkout(client, name="Carlos Silva", payment_method="cash")
    assert status == 201, order_resp

    order = Order.objects.get(ref=order_resp["order_ref"])
    assert order.total_q == 700
    # A faixa sobrevive ao commit — é ela que autoriza o preço cobrado.
    assert (order.data.get("customer") or {}).get("price_tier") == "staff"


def test_staff_customer_loses_the_discount_on_delivery(client, equipe_discount):
    """Entrega: paga cheio. O benefício é do funcionário, não um canal de preço."""
    from shopman.shop.models import DeliveryZone, Shop

    _seed()
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=0,
    )
    staff = _staff_customer()
    J.authenticate(client, staff)
    J.set_cart_qty(client, SKU, 1)

    status, order_resp = J.checkout(
        client,
        name="Carlos Silva",
        payment_method="cash",
        fulfillment_type="delivery",
        delivery_date=timezone.localdate().isoformat(),
        delivery_address="Rua das Flores, 1",
        delivery_address_structured={
            "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
            "route": "Rua das Flores",
            "street_number": "1",
            "city": "Londrina",
            "state_code": "PR",
            "postal_code": "86050-270",
            "neighborhood": "Centro",
        },
    )
    assert status == 201, order_resp

    order = Order.objects.get(ref=order_resp["order_ref"])
    assert order.total_q == 1000, "entrega não pode carregar preço de funcionário"


def test_the_store_warns_before_the_price_changes(client, equipe_discount):
    """A dica aparece ANTES da escolha, senão o preço "muda sozinho"."""
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)
    J.set_cart_qty(client, SKU, 1)

    resp = client.get("/api/v1/storefront/checkout/")
    checkout = resp.json()["checkout"]
    assert checkout["delivery_hint"] == "Sem o desconto do grupo"

    # Cliente comum não vê aviso nenhum — a dica é sobre o benefício dele.
    other = client.__class__()
    assert other.get("/api/v1/storefront/checkout/").json()["checkout"]["delivery_hint"] == ""


def test_checkout_tells_the_group_savings(client, equipe_discount):
    """Com economia > 0, o checkout diz quanto e por qual grupo."""
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)
    J.set_cart_qty(client, SKU, 1)

    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]

    # 1000 − 30% = 700; economia de R$ 3,00.
    assert checkout["group_savings_message"] == "Hoje você economizou R$ 3,00 por ser da Equipe"


def test_checkout_has_no_savings_message_without_the_group(client):
    """Cliente comum não recebe mensagem de economia de grupo."""
    _seed()
    J.set_cart_qty(client, SKU, 1)

    checkout = client.get("/api/v1/storefront/checkout/").json()["checkout"]

    assert checkout["group_savings_message"] == ""
