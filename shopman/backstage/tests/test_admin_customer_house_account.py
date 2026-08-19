"""A conta na casa é um checkbox no Admin do cliente, não JSON (WP-10 do CASHMAN-PLAN)."""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.admin_unfold.admin import CustomerForm
from shopman.guestman.models import Customer

from shopman.shop.services import house_account

pytestmark = pytest.mark.django_db


def _form_data(customer: Customer, **over) -> dict:
    data = {
        "ref": customer.ref,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "customer_type": customer.customer_type,
        "document": customer.document or "",
        "email": customer.email or "",
        "phone": customer.phone or "",
        "price_tier": customer.price_tier_id or "",
        "tags": "",
        "notes": customer.notes or "",
        "is_active": "on" if customer.is_active else "",
        "metadata": '{"fidelidade": "ouro"}',
        "created_by": customer.created_by or "",
        "source_system": customer.source_system or "",
    }
    data.update(over)
    return data


def test_o_checkbox_liga_e_desliga_a_conta_preservando_o_resto_do_metadata():
    customer = Customer.objects.create(ref="CLI-1", first_name="Ana", phone="+5543999990001")
    assert not house_account.is_eligible("CLI-1")

    form = CustomerForm(data=_form_data(customer, house_account="on"), instance=customer)
    assert form.is_valid(), form.errors
    form.save()
    customer.refresh_from_db()
    assert customer.metadata == {"fidelidade": "ouro", "house_account": True}
    assert house_account.is_eligible("CLI-1")
    assert CustomerForm(instance=customer).fields["house_account"].initial is True

    form = CustomerForm(data=_form_data(customer), instance=customer)
    assert form.is_valid(), form.errors
    form.save()
    customer.refresh_from_db()
    assert customer.metadata == {"fidelidade": "ouro"}
    assert not house_account.is_eligible("CLI-1")
