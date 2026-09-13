"""Checkout identity and payment policy are enforced before any cart mutation."""

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.orderman.models import Order, Session
from shopman.stockman.models import Hold

from shopman.shop.models import Channel
from shopman.storefront.services.pickup_slots import get_slots
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface
from shopman.storefront.tests.security.conftest import login_as_customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def checkout_case(client):
    cache.clear()
    _seed_surface(stock_qty=Decimal("10"))
    Channel.objects.filter(ref="web").update(config={"payment": {"method": ["pix", "card"]}})
    owner = Customer.objects.create(ref="CHECKOUT-OWNER", first_name="Owner", phone="+5543999990011")
    victim = Customer.objects.create(ref="CHECKOUT-VICTIM", first_name="Victim", phone="+5543999990022")
    other = Client()
    login_as_customer(other, victim)
    assert other.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 2}, content_type="application/json").status_code == 200
    victim_cart = Session.objects.get(session_key=other.session["cart_session_key"])
    victim_cart.handle_type, victim_cart.handle_ref = "phone", victim.phone
    victim_cart.save(update_fields=["handle_type", "handle_ref"])
    assert Hold.objects.filter(metadata__reference=victim_cart.session_key).exists()
    assert client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1}, content_type="application/json").status_code == 200
    payload = with_baseline(
        client,
        {
            "name": "Owner",
            "phone": victim.phone,
            "payment_method": "pix",
            "fulfillment_type": "pickup",
            "delivery_date": timezone.localdate().isoformat(),
            "delivery_time_slot": get_slots()[-1]["ref"],
            "idempotency_key": "checkout-principal-boundary",
        },
    )
    return owner, victim_cart, payload


def cart_state(cart):
    cart.refresh_from_db()
    return (
        cart.state,
        cart.rev,
        cart.data,
        list(Hold.objects.filter(metadata__reference=cart.session_key).values("id", "status")),
    )


def test_anonymous_cannot_mutate_another_phone_cart(client, checkout_case):
    _, victim_cart, payload = checkout_case
    before = cart_state(victim_cart)
    response = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["error_code"] == "authentication_required"
    assert not Order.objects.exists()
    assert cart_state(victim_cart) == before


def test_authenticated_phone_wins_and_replay_ignores_payload_phone(client, checkout_case):
    owner, victim_cart, payload = checkout_case
    login_as_customer(client, owner)
    before = cart_state(victim_cart)
    response = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert response.status_code == 201, response.content
    order = Order.objects.get(ref=response.json()["order_ref"])
    assert order.handle_ref == owner.phone
    assert order.data["customer"]["phone"] == owner.phone
    assert cart_state(victim_cart) == before
    Channel.objects.filter(ref="web").update(config={"payment": {"method": ["card"]}})
    replay = client.post("/api/v1/checkout/", {**payload, "phone": "+5543999990033"}, content_type="application/json")
    assert replay.status_code == 201, replay.content
    assert replay.json()["order_ref"] == order.ref
    assert Order.objects.count() == 1


@pytest.mark.parametrize("method", ["", "cash", "external", "unknown", None])
def test_invalid_payment_has_no_order_or_victim_effect(client, checkout_case, method):
    owner, victim_cart, payload = checkout_case
    login_as_customer(client, owner)
    before = cart_state(victim_cart)
    own_cart = Session.objects.get(session_key=client.session["cart_session_key"])
    own_before = cart_state(own_cart)
    payload["payment_method"] = method
    if method is None:
        payload.pop("payment_method")
    response = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert response.status_code == 400, response.content
    assert "payment_method" in response.json() or response.json().get("field") == "payment_method"
    assert not Order.objects.exists()
    assert cart_state(victim_cart) == before
    assert cart_state(own_cart) == own_before


def test_phone_can_be_omitted_by_authenticated_customer(client, checkout_case):
    owner, victim_cart, payload = checkout_case
    login_as_customer(client, owner)
    payload.pop("phone")
    before = cart_state(victim_cart)
    response = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert response.status_code == 201, response.content
    assert Order.objects.get(ref=response.json()["order_ref"]).handle_ref == owner.phone
    assert cart_state(victim_cart) == before


@pytest.mark.parametrize("inactive", [True, False])
def test_invalid_authenticated_customer_cannot_commit(client, checkout_case, inactive):
    owner, victim_cart, payload = checkout_case
    login_as_customer(client, owner)
    if inactive:
        owner.is_active = False
    else:
        owner.phone = ""
    owner.save()
    if not inactive:
        owner.contact_points.filter(type__in=["phone", "whatsapp"]).delete()
    response = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert response.status_code == 403, response.content
    assert not Order.objects.exists()


@pytest.mark.parametrize("payload", [[], ["unexpected"], "unexpected", None])
def test_authenticated_non_object_payload_is_rejected_cleanly(client, checkout_case, payload):
    import json

    owner, victim_cart, _ = checkout_case
    login_as_customer(client, owner)
    before = cart_state(victim_cart)
    response = client.post("/api/v1/checkout/", json.dumps(payload), content_type="application/json")
    assert response.status_code == 400, response.content
    assert "detail" in response.json()
    assert not Order.objects.exists()
    assert cart_state(victim_cart) == before
