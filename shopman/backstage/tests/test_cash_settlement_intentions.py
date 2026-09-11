"""Synthetic ledger receipts preserve the observed receiving custody."""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import IdempotencyKey, Order
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Synthetic cash receipt lab")
    user = django_user_model.objects.create_user(username="cash-receipt", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    terminal = Terminal.objects.create(ref="only-lab", label="Synthetic counter")
    shift = cash.open_shift(operator=user, terminal=terminal)
    order = Order.objects.create(ref="CASH-RECEIPT", status="dispatched", total_q=1500,
        data={"fulfillment_type": "delivery", "payment": {"method": "cash", "collection": "on_delivery"}})
    detail = client.get(reverse("api-backstage-order-detail", args=[order.ref])).json()["order"]
    action = next(action for action in detail["actions"] if action["ref"] == "settle-delivery-cash")
    assert action["enabled"]
    return user, shift, order, action


def post(client, order, action, key="cash-once", **inputs):
    return client.post(reverse("api-backstage-order-settle-delivery-cash", args=[order.ref]),
        {**action["payload_schema"], "amount": "15,00", **inputs}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)


def test_lost_response_receipt_then_replay_has_one_payment_entry_event(client, context):
    _user, shift, order, action = context
    first = post(client, order, action)
    assert first.status_code == 200, first.content
    receipt = client.get(reverse("api-backstage-order-settle-delivery-cash", args=[order.ref]), {"idempotency_key": "cash-once"})
    assert receipt.json()["outcome"] == "applied"
    assert receipt.json()["amount_q"] == 1500
    replay = post(client, order, action)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert Entry.objects.filter(shift=shift, order_ref=order.ref, kind="cod_settled", amount_q=1500).count() == 1
    assert PaymentIntent.objects.filter(order_ref=order.ref, status="captured", amount_q=1500).count() == 1
    assert order.events.filter(type="payment_collected").count() == 1
    assert post(client, order, action, amount="16,00").status_code == 409


def test_replacement_shift_cannot_receive_the_old_intention(client, context):
    user, shift, order, action = context
    cash.close_shift(shift, counted_q=0, actor=user)
    cash.open_shift(operator=user, terminal=shift.terminal)
    response = post(client, order, action)
    assert response.status_code == 409, response.content
    assert not Entry.objects.filter(order_ref=order.ref).exists()
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()


def test_two_drawers_block_without_choosing_another_custodian(client, context):
    user, _shift, order, action = context
    cash.open_shift(operator=user, terminal=Terminal.objects.create(ref="second-lab", label="Second synthetic counter"))
    response = post(client, order, action)
    assert response.status_code == 409, response.content
    detail = client.get(reverse("api-backstage-order-detail", args=[order.ref])).json()["order"]
    action = next(action for action in detail["actions"] if action["ref"] == "settle-delivery-cash")
    assert not action["enabled"]
    assert "Mais de um caixa" in action["reason"]
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()


def test_receipt_failure_rolls_back_all_three_books(client, context):
    _user, _shift, order, action = context
    original = IdempotencyKey.save

    def fail_receipt(instance, *args, **kwargs):
        if instance.key == "cash-once" and instance.response_body:
            raise RuntimeError("synthetic receipt storage failure")
        return original(instance, *args, **kwargs)

    with patch.object(IdempotencyKey, "save", fail_receipt):
        with pytest.raises(RuntimeError, match="synthetic receipt"):
            post(client, order, action)
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    assert not Entry.objects.filter(order_ref=order.ref).exists()
    assert not order.events.filter(type="payment_collected").exists()
    order.refresh_from_db()
    assert "cod_settled_at" not in order.data["payment"]
