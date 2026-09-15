"""Explicit authenticated setup for checkout API contract tests."""

from shopman.guestman.models import Customer

from shopman.storefront.tests.security.conftest import login_as_customer


def authenticate_checkout(client, *, phone="+5543999990001", ref="CHECKOUT-TEST"):
    customer, _ = Customer.objects.get_or_create(phone=phone, defaults={"ref": ref, "first_name": "Ana"})
    login_as_customer(client, customer)
    return customer
