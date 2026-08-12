"""Persona 3 — funcionário da Nelson (desconto de staff).

DECISÃO (2026-08-11, Pablo): o funcionário **tem** o desconto na loja pública,
mas **só na retirada**. O benefício é dele; com entrega, o preço de funcionário
viajaria para qualquer endereço e viraria canal de preço para terceiros, sem
ninguém ver — no balcão isso não acontece porque alguém entrega na mão.

A política mora na regra (``EmployeeRule.pickup_only``, default ``True``), não em
código de superfície, então o dono muda pelo admin.

⚠️ A versão anterior deste arquivo afirmava o contrário ("a loja nunca escreve
``customer.price_tier``") e **passava por cobertura falsa**: o fixture não criava
``RuleConfig`` da regra, então o teste provava "regra não configurada", não a
fronteira. Quando `da69c714` fez a regra voltar a carregar, a fronteira caiu e
ninguém foi avisado. Por isso agora o fixture cria a regra de verdade.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, PriceTier
from shopman.orderman.models import Order, Session

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-STAFF"


def _seed():
    J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão", 1000, collection=collection, stock_qty=20)


def _staff_customer():
    tier = PriceTier.objects.create(ref="staff", name="Funcionários")
    return Customer.objects.create(
        ref="CUST-STAFF-1", first_name="Carlos", last_name="Silva",
        phone=J.DEFAULT_PHONE, price_tier=tier,
    )


@pytest.fixture
def employee_rule():
    """A regra LIGADA de verdade — sem isto o teste prova "regra não configurada"."""
    from shopman.shop.models import RuleConfig
    from shopman.shop.rules import engine

    RuleConfig.objects.create(
        ref="employee_discount",
        rule_path="shopman.shop.rules.pricing.EmployeeRule",
        label="Desconto Funcionário",
        params={"discount_percent": 20, "price_tier": "staff", "pickup_only": True},
        enabled=True,
        priority=60,
    )
    try:
        engine.get_active_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    yield
    try:
        engine.get_active_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


# ── the boundary, through the storefront ─────────────────────────────────────


def test_staff_customer_gets_the_discount_on_pickup(client, employee_rule):
    """Retirada: o funcionário paga R$ 8,00 (20% off) e o pedido FECHA.

    O que a tela mostra é o que o commit cobra — a `expected_total_q` do helper
    vem da projeção, então se os dois discordassem o pedido seria recusado com
    `total_changed`. Foi exatamente essa discordância que quebrava a persona.
    """
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)

    J.set_cart_qty(client, SKU, 1)
    status, order_resp = J.checkout(client, name="Carlos Silva", payment_method="cash")
    assert status == 201, order_resp

    order = Order.objects.get(ref=order_resp["order_ref"])
    assert order.total_q == 800
    # A faixa sobrevive ao commit — é ela que autoriza o preço cobrado.
    assert (order.data.get("customer") or {}).get("price_tier") == "staff"


def test_staff_customer_loses_the_discount_on_delivery(client, employee_rule):
    """Entrega: paga cheio. O benefício é do funcionário, não um canal de preço.

    Com entrega o preço de staff viajaria para qualquer endereço, sem ninguém
    ver. Retirando, alguém entrega o pacote na mão — é essa a testemunha que o
    balcão sempre teve.
    """
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


def test_the_store_warns_before_the_price_changes(client, employee_rule):
    """A dica aparece ANTES da escolha, senão o preço "muda sozinho".

    Sem isto o funcionário troca para entrega, vê o total subir e lê como
    defeito. O aviso mora no ``delivery_hint``, ao lado da própria opção.
    """
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)
    J.set_cart_qty(client, SKU, 1)

    resp = client.get("/api/v1/storefront/checkout/")
    checkout = resp.json()["checkout"]
    assert checkout["delivery_hint"] == "Sem o desconto de funcionário"

    # Cliente comum não vê aviso nenhum — a dica é sobre o benefício dele.
    other = client.__class__()
    assert other.get("/api/v1/storefront/checkout/").json()["checkout"]["delivery_hint"] == ""


# ── the mechanism, driven the way the POS drives it ──────────────────────────


def test_employee_discount_applies_when_session_carries_staff_group(client):
    """The modifier discounts every line when the session data marks the
    customer as staff — this is what the POS attach-customer path produces."""
    from shopman.shop.models import Channel
    from shopman.shop.modifiers import EmployeeDiscountModifier

    _seed()
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={"payment": {"method": "cash"}})
    session = Session.objects.create(
        session_key="POS-STAFF-1",
        channel_ref="pdv",
        state="open",
        rev=1,
        items=[{"line_id": "L1", "sku": SKU, "qty": 1, "unit_price_q": 1000, "line_total_q": 1000}],
        data={"customer": {"name": "Carlos", "price_tier": "staff"}},
        pricing={},
    )

    EmployeeDiscountModifier(discount_percent=20).apply(channel=pdv, session=session, ctx={})

    session.refresh_from_db()
    assert session.items[0]["unit_price_q"] == 800  # 20% off R$10,00
    assert session.pricing["employee_discount"]["total_discount_q"] == 200
    assert session.pricing["employee_discount"]["label"] == "Desconto funcionário"


def test_non_staff_group_gets_no_employee_discount(client):
    """A non-staff tier leaves prices untouched."""
    from shopman.shop.models import Channel
    from shopman.shop.modifiers import EmployeeDiscountModifier

    _seed()
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={"payment": {"method": "cash"}})
    session = Session.objects.create(
        session_key="POS-REG-1",
        channel_ref="pdv",
        state="open",
        rev=1,
        items=[{"line_id": "L1", "sku": SKU, "qty": 1, "unit_price_q": 1000, "line_total_q": 1000}],
        data={"customer": {"name": "Ana", "price_tier": "regular"}},
        pricing={},
    )

    EmployeeDiscountModifier(discount_percent=20).apply(channel=pdv, session=session, ctx={})

    session.refresh_from_db()
    assert session.items[0]["unit_price_q"] == 1000  # untouched
    assert "employee_discount" not in (session.pricing or {})
