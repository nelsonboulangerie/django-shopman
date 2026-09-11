"""Real local effects, interrupted after their write; no external providers."""

from unittest.mock import patch

import pytest
from shopman.guestman.services import address, customer
from shopman.orderman.models import Directive, IdempotencyKey, Order

from shopman.shop import directives
from shopman.shop.services import checkout
from shopman.shop.services.checkout_defaults import CheckoutDefaultsService

pytestmark = pytest.mark.django_db


@pytest.fixture
def order():
    customer.create(ref="RECOVERY-CUSTOMER", first_name="", phone="+5543999990019")
    return Order.objects.create(
        ref="RECOVERY-ORDER",
        channel_ref="web",
        data={
            "customer": {"name": "Ana", "phone": "+5543999990019"},
            "fulfillment_type": "delivery",
            "delivery_address": "Rua Sintética, 19",
            "address_label": {"key": "home", "custom": ""},
            "payment": {"method": "cash"},
            "save_as_default": True,
        },
    )


def job(order, effect):
    return directives.create_persistently_deduped(
        directives.CHECKOUT_CONVENIENCE,
        payload={"order_ref": order.ref, "effect": effect},
        dedupe_key=f"checkout:{order.ref}:{effect}:v1",
        receipt_scope="checkout:convenience:queued",
    )


@pytest.mark.parametrize(
    "effect,function",
    [("customer", "ensure_customer"), ("address", "persist_new_address"), ("defaults", "save_defaults")],
)
def test_failure_after_local_write_rolls_back_then_recovery_and_lost_response_replay(order, effect, function):
    if effect == "defaults":
        checkout.persist_new_address(checkout._post_commit_intent(order.data, "web"))
    before_addresses = list(address.addresses("RECOVERY-CUSTOMER"))
    message = job(order, effect)
    original = getattr(checkout, function)

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic crash after local write")

    with patch.object(checkout, function, side_effect=fail_after_write), pytest.raises(RuntimeError):
        checkout.recover_convenience_effect(message)
    message.refresh_from_db()
    assert message.status != "done"
    if effect == "customer":
        assert customer.get_by_phone("+5543999990019").first_name == ""
    assert not IdempotencyKey.objects.filter(
        scope="checkout:convenience", key=message.dedupe_key, status="done"
    ).exists()
    assert list(address.addresses("RECOVERY-CUSTOMER")) == before_addresses
    assert CheckoutDefaultsService.get_defaults("RECOVERY-CUSTOMER", "web") == {}
    with patch.object(checkout, function, wraps=original) as apply:
        checkout.recover_convenience_effect(message)
        checkout.recover_convenience_effect(message)
    assert apply.call_count == 1
    message.refresh_from_db()
    assert message.status == "done"
    assert Order.objects.filter(ref=order.ref).count() == 1
    if effect == "customer":
        assert customer.get_by_phone("+5543999990019").first_name == "Ana"
    if effect == "address":
        saved = list(address.addresses("RECOVERY-CUSTOMER"))
        assert len(saved) == 1
        assert saved[0].label == "home"
    if effect == "defaults":
        assert CheckoutDefaultsService.get_defaults("RECOVERY-CUSTOMER", "web")["payment_method"] == "cash"


def test_delayed_defaults_preserve_later_explicit_choice(order):
    checkout.persist_new_address(checkout._post_commit_intent(order.data, "web"))
    message = job(order, "defaults")
    CheckoutDefaultsService.save_defaults("RECOVERY-CUSTOMER", "web", {"payment_method": "pix"})
    checkout.recover_convenience_effect(message)
    assert CheckoutDefaultsService.get_defaults("RECOVERY-CUSTOMER", "web")["payment_method"] == "pix"


def test_new_address_is_remembered_by_canonical_defaults_without_retyping(order):
    assert checkout._apply_post_commit_side_effects(order.data, "web", order_ref=order.ref) == []
    saved = list(address.addresses("RECOVERY-CUSTOMER"))
    assert len(saved) == 1
    defaults = CheckoutDefaultsService.get_defaults("RECOVERY-CUSTOMER", "web")
    assert str(defaults["delivery_address_id"]) == str(saved[0].pk)
    assert Directive.objects.filter(topic=directives.CHECKOUT_CONVENIENCE).exclude(status="done").count() == 0


def test_address_failure_defers_dependent_defaults_and_recovers_only_missing_effects(order):
    with patch.object(checkout, "persist_new_address", side_effect=RuntimeError("synthetic address failure")):
        pending = checkout._apply_post_commit_side_effects(order.data, "web", order_ref=order.ref)
    assert pending == ["address", "defaults"]
    with patch.object(checkout, "ensure_customer", side_effect=AssertionError("already confirmed effect repeated")):
        assert checkout._apply_post_commit_side_effects(order.data, "web", order_ref=order.ref) == []
    saved = list(address.addresses("RECOVERY-CUSTOMER"))
    assert len(saved) == 1
    assert str(CheckoutDefaultsService.get_defaults("RECOVERY-CUSTOMER", "web")["delivery_address_id"]) == str(
        saved[0].pk
    )
