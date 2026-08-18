"""Loja online em dinheiro NÃO cria intent no Payman (ADR-022, WP-2 do CASHMAN-PLAN).

O PDV passou a liquidar ``cash``/``external`` no Payman quando a coleta é no
terminal (``payment.collection == "terminal"``). A loja online nunca escreve
``collection``: o cliente ainda não pagou nada, e o intent do dinheiro nasce no
acerto (COD na entrega, balcão na retirada), não no checkout. Este teste é a
prova de que a fronteira ficou onde estava.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent

from shopman.shop.models import DeliveryZone, Shop
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro",
    "postal_code": "86050-270",
    "neighborhood": "Centro",
}


def _checkout(client, django_capture_on_commit_callbacks, **payload) -> Order:
    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 2}, content_type="application/json")
    assert add.status_code == 200, add.content
    # O lifecycle roda em on_commit: executar aqui prova que nem o dispatch cria intent.
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(
            "/api/v1/checkout/",
            data=with_baseline(client, {"name": "Ana", "phone": "+5543999990001", **payload}),
            content_type="application/json",
        )
    assert resp.status_code == 201, resp.content
    return Order.objects.get(ref=resp.json()["order_ref"])


def test_delivery_cash_checkout_has_no_payment_intent(client, django_capture_on_commit_callbacks):
    _seed_surface()
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )

    order = _checkout(
        client,
        django_capture_on_commit_callbacks,
        fulfillment_type="delivery",
        delivery_address="Rua das Flores, 1",
        delivery_address_structured=ADDRESS,
        delivery_date=timezone.localdate().isoformat(),
        payment_method="cash",
        change_for="100,00",
    )

    payment = order.data["payment"]
    assert payment["method"] == "cash"
    assert "collection" not in payment
    assert "intent_ref" not in payment
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()


def test_pickup_cash_checkout_has_no_payment_intent(client, django_capture_on_commit_callbacks):
    from shopman.storefront.services.pickup_slots import get_slots

    _seed_surface()

    order = _checkout(
        client,
        django_capture_on_commit_callbacks,
        fulfillment_type="pickup",
        delivery_date=timezone.localdate().isoformat(),
        delivery_time_slot=get_slots()[-1]["ref"],
        payment_method="cash",
    )

    payment = order.data.get("payment") or {}
    assert payment.get("method") == "cash"
    assert "intent_ref" not in payment
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
