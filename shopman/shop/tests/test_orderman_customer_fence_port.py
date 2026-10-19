"""A cerca do titular do Orderman é um porto, ligado pela setting do deployment.

Laudo de soberania 18/10 (AK-1): o Orderman consultava ``guestman.Customer``
por ``apps.get_model`` no commit e na associação de titular. Agora a cerca é o
``CustomerFence`` do Orderman, implementado pelo Guestman.
"""

import pytest
from django.test import override_settings
from shopman.guestman.adapters.orderman import GuestmanCustomerFence
from shopman.guestman.models import ContactPoint, Customer
from shopman.orderman.conf import get_customer_fence
from shopman.orderman.integrations import get_channel_model
from shopman.orderman.protocols import CustomerFence, CustomerIdentityConflict

from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db


def test_deployment_wires_the_guestman_fence():
    fence = get_customer_fence()
    assert isinstance(fence, GuestmanCustomerFence)
    assert isinstance(fence, CustomerFence)


def test_without_the_port_orderman_has_no_fence():
    with override_settings(ORDERMAN={}):
        assert get_customer_fence() is None
        assert get_channel_model() is None


def test_channel_model_is_the_declared_one():
    assert get_channel_model() is Channel


def test_fence_locks_by_identity_and_reports_conflicts():
    fence = GuestmanCustomerFence()
    ana = Customer.objects.create(ref="CUST-ANA", first_name="Ana", phone="+5543999990001")
    Customer.objects.create(ref="CUST-BIA", first_name="Bia", phone="+5543999990002")

    fenced = fence.lock_by_identity(customer_ref="CUST-ANA", phone="+5543999990001")
    assert (fenced.pk, fenced.ref, fenced.phone, fenced.is_active) == (ana.pk, "CUST-ANA", "+5543999990001", True)

    with pytest.raises(CustomerIdentityConflict) as mismatch:
        fence.lock_by_identity(customer_ref="CUST-ANA", phone="+5543999990002")
    assert mismatch.value.code == "customer_identity_mismatch"

    assert fence.lock_by_identity(customer_ref="CUST-NINGUEM", phone="") is None


def test_fence_reads_secondary_phone_and_active_owner():
    fence = GuestmanCustomerFence()
    ana = Customer.objects.create(ref="CUST-ANA", first_name="Ana", phone="+5543999990001")
    ContactPoint.objects.create(customer=ana, type="whatsapp", value_normalized="+5543999990009")
    fenced = fence.lock_by_ref("CUST-ANA")

    assert fence.owns_phone(fenced, "+5543999990009") is True
    assert fence.owns_phone(fenced, "+5543999990008") is False
    assert fence.is_active_owner(fenced, "CUST-ANA") is True
    Customer.objects.filter(pk=ana.pk).update(is_active=False)
    assert fence.is_active_owner(fenced, "CUST-ANA") is False
