"""Um pedido, uma data, de ponta a ponta: sacola real, ``POST /api/v1/checkout/``.

Beta 09/11 (NB-261109-Y61/N40/G46): o Kuro Pan entrou na sacola pela fila da
fornada de quarta e o checkout fechou um pedido para retirar HOJE. Aqui a
reserva nasce pelo caminho da sacola (``PUT /api/v1/cart/skus/``), a recusa
atravessa o ``CommitService`` e chega ao cliente no dialeto
``{detail, field, errors}``; para o dia da fornada o pedido fecha e fica com a
vaga que a sacola já guardava.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

SKU = "KURO-PAN-E2E"
PHONE = "+5543999990002"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """O teto de 3 fechamentos por minuto mora no cache do processo: não herda nem deixa conta."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _world(batch_date, *, batch_qty: int = 1):
    from shopman.offerman.models import Listing, ListingItem, Product
    from shopman.stockman.service import Stock

    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Casa", brand_name="Casa", short_name="Casa", phone="554333231997")
    Channel.objects.create(
        ref="web", name="Loja online", is_active=True,
        config={"waitlist": {"enabled": True, "horizon_days": 3}},
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    product = Product.objects.create(
        sku=SKU, name="Kuro Pan", base_price_q=2200, is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing, product=product, price_q=2200, is_published=True, is_sellable=True,
    )
    Stock.plan(Decimal(str(batch_qty)), product, batch_date)


def _client_with_kuro_pan_waiting(batch_date) -> tuple[Client, str]:
    """Cliente com 1 Kuro Pan na sacola, preso à fornada de ``batch_date``."""
    from shopman.guestman.models import Customer
    from shopman.stockman.models import Hold

    from shopman.storefront.tests.security.conftest import login_as_customer

    client = Client()
    login_as_customer(client, Customer.objects.create(ref="CUST-BIA", first_name="Bia", phone=PHONE))
    resp = client.put(f"/api/v1/cart/skus/{SKU}/", data=json.dumps({"qty": 1}), content_type="application/json")
    assert resp.status_code in (200, 201), resp.content[:400]
    [hold] = Hold.objects.filter(sku=SKU)
    assert hold.quant is not None and hold.quant.target_date == batch_date
    return client, hold.hold_id


def _checkout(client: Client, *, delivery_date, slot: str):
    from shopman.storefront.tests._checkout_baseline import with_baseline

    payload = with_baseline(client, {
        "name": "Bia", "phone": PHONE,
        "fulfillment_type": "pickup",
        "delivery_date": delivery_date.isoformat(),
        "delivery_time_slot": slot,
        "payment_method": "cash",
    })
    return client.post("/api/v1/checkout/", data=payload, content_type="application/json")


def test_pedido_de_hoje_com_a_sacola_presa_a_fornada_futura_e_recusado_no_campo_da_data():
    from shopman.orderman.models import Order
    from shopman.stockman.models import Hold

    from shopman.shop.policies.order_date_before_batch import batch_day_phrase
    from shopman.storefront.tests._pickup_today import today_pickup_slot

    today = timezone.localdate()
    batch_date = today + timedelta(days=2)
    _world(batch_date)
    client, hold_id = _client_with_kuro_pan_waiting(batch_date)

    resp = _checkout(client, delivery_date=today, slot=today_pickup_slot())

    assert resp.status_code == 400, resp.content[:600]
    body = resp.json()
    expected = f"Kuro Pan sai {batch_day_phrase(batch_date)}. Escolha essa data ou uma depois dela."
    assert body["field"] == "delivery_date"
    assert body["detail"] == expected
    assert body["errors"] == {"delivery_date": expected}
    assert not Order.objects.exists()
    # A vaga na fornada continua da sacola: nada foi adotado nem solto.
    hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    assert hold.is_active and hold.quant.target_date == batch_date


def test_pedido_para_o_dia_da_fornada_fecha_e_fica_com_a_vaga_da_sacola():
    from shopman.orderman.models import Order
    from shopman.stockman.models import Hold

    from shopman.storefront.tests._pickup_today import today_pickup_slot

    today = timezone.localdate()
    batch_date = today + timedelta(days=2)
    # A fornada só tem a unidade que a sacola já guardou.
    _world(batch_date, batch_qty=1)
    client, hold_id = _client_with_kuro_pan_waiting(batch_date)
    today_pickup_slot()  # garante o expediente da loja de teste

    resp = _checkout(client, delivery_date=batch_date, slot="slot-12")

    assert resp.status_code == 201, resp.content[:600]
    order = Order.objects.get()
    assert order.data["delivery_date"] == batch_date.isoformat()
    assert order.data["hold_ids"] == [{"sku": SKU, "hold_id": hold_id, "qty": 1.0}]
    hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    assert hold.is_active and hold.quant.target_date == batch_date
    assert hold.metadata["reference"] == f"order:{order.ref}"
