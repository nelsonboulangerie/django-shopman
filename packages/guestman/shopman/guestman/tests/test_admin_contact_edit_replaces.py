"""Editar ``phone``/``email`` no Admin troca o principal; o antigo sai (A4-1)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.contrib import admin
from django.test import RequestFactory
from shopman.guestman.admin import CustomerAdmin as LegacyCustomerAdmin
from shopman.guestman.contrib.admin_unfold.admin import CustomerAdmin
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services.identity import replace_primary_contact

pytestmark = pytest.mark.django_db

ANTIGO = "+5543999995001"
NOVO = "+5543999995002"
SECUNDARIO = "+5543999995003"


@pytest.fixture
def customer():
    customer = Customer.objects.create(ref="CUS-TROCA-01", first_name="Ana", phone=ANTIGO)
    ContactPoint.objects.create(
        customer=customer, type=ContactPoint.Type.WHATSAPP, value_normalized=ANTIGO, is_primary=True,
    )
    ContactPoint.objects.create(
        customer=customer, type=ContactPoint.Type.PHONE, value_normalized=SECUNDARIO,
    )
    CustomerIdentifier.objects.create(
        customer=customer, identifier_type=IdentifierType.PHONE, identifier_value=ANTIGO,
    )
    return customer


def _phones(customer) -> set[tuple[str, str, bool]]:
    return set(
        ContactPoint.objects.filter(customer=customer).values_list("type", "value_normalized", "is_primary")
    )


def test_replace_primary_contact_tira_o_antigo_e_mantem_o_secundario(customer):
    replace_primary_contact(customer, field="phone", new_value=NOVO)

    customer.refresh_from_db()
    assert customer.phone == NOVO
    assert _phones(customer) == {("phone", NOVO, True), ("phone", SECUNDARIO, False)}
    assert not CustomerIdentifier.objects.filter(identifier_value=ANTIGO).exists()


def test_replace_primary_contact_vazio_so_retira_o_principal(customer):
    replace_primary_contact(customer, field="phone", new_value="")

    customer.refresh_from_db()
    assert customer.phone == ""
    assert _phones(customer) == {("phone", SECUNDARIO, False)}


@pytest.mark.parametrize("admin_class", (LegacyCustomerAdmin, CustomerAdmin))
def test_admin_troca_o_telefone_pelo_campo(customer, admin_class):
    obj = Customer.objects.get(pk=customer.pk)
    obj.phone = "(43) 99999-5002"
    request = RequestFactory().post("/admin/guestman/customer/change/")

    admin_class(Customer, admin.site).save_model(request, obj, form=Mock(), change=True)

    customer.refresh_from_db()
    assert customer.phone == NOVO
    assert obj.phone == NOVO
    assert _phones(customer) == {("phone", NOVO, True), ("phone", SECUNDARIO, False)}
    assert not CustomerIdentifier.objects.filter(identifier_value=ANTIGO).exists()
