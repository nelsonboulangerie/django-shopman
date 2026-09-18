"""Closed-customer behavior for Guestman's public personal-data mutators."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import RequestFactory
from shopman.guestman.admin import (
    ContactPointAdmin as LegacyContactPointAdmin,
)
from shopman.guestman.admin import (
    CustomerAddressAdmin as LegacyCustomerAddressAdmin,
)
from shopman.guestman.admin import (
    CustomerAdmin as LegacyCustomerAdmin,
)
from shopman.guestman.admin import (
    ExternalIdentityAdmin as LegacyExternalIdentityAdmin,
)
from shopman.guestman.admin_privacy import (
    CustomerOwnedPrivacyFenceAdminMixin,
    PrivacyReadOnlyAdminMixin,
)
from shopman.guestman.contrib.admin_unfold.admin import (
    ContactPointAdmin,
    CustomerAddressAdmin,
    CustomerAdmin,
    ExternalIdentityAdmin,
    LoyaltyAccountAdmin,
    LoyaltyTransactionAdmin,
)
from shopman.guestman.contrib.consent.admin import CommunicationConsentAdmin
from shopman.guestman.contrib.consent.models import CommunicationConsent
from shopman.guestman.contrib.identifiers.admin import CustomerIdentifierAdmin
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.identifiers.service import IdentifierService
from shopman.guestman.contrib.insights.admin import CustomerInsightAdmin
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.contrib.insights.service import InsightService
from shopman.guestman.contrib.loyalty.admin import (
    LoyaltyAccountAdmin as LegacyLoyaltyAccountAdmin,
)
from shopman.guestman.contrib.loyalty.admin import (
    LoyaltyTransactionAdmin as LegacyLoyaltyTransactionAdmin,
)
from shopman.guestman.contrib.loyalty.models import LoyaltyAccount, LoyaltyTransaction
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.contrib.preferences.admin import CustomerPreferenceAdmin
from shopman.guestman.contrib.preferences.models import CustomerPreference
from shopman.guestman.contrib.preferences.service import PreferenceService
from shopman.guestman.contrib.timeline.admin import TimelineEventAdmin
from shopman.guestman.contrib.timeline.models import TimelineEvent
from shopman.guestman.contrib.timeline.service import TimelineService
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    CustomerTag,
    ExternalIdentity,
)

pytestmark = pytest.mark.django_db


def _deactivate(customer: Customer) -> None:
    customer.is_active = False
    customer.save(update_fields=["is_active", "updated_at"])


@pytest.mark.parametrize("method_name", ("add_identifier", "ensure_identifier"))
def test_identifier_writers_refuse_inactive_customer(customer, method_name):
    _deactivate(customer)

    with pytest.raises(Customer.DoesNotExist):
        getattr(IdentifierService, method_name)(
            customer.ref,
            IdentifierType.INSTAGRAM,
            "privacy-fence",
        )

    assert not CustomerIdentifier.objects.filter(customer=customer).exists()


def test_preference_writers_refuse_inactive_customer(customer):
    _deactivate(customer)

    with pytest.raises(Customer.DoesNotExist):
        PreferenceService.set_preference(
            customer.ref,
            "alimentar",
            "sem_lactose",
            True,
        )
    assert PreferenceService.delete_preference(
        customer.ref,
        "alimentar",
        "sem_lactose",
    ) is False
    assert not CustomerPreference.objects.filter(customer=customer).exists()


def test_timeline_writer_refuses_inactive_customer(customer):
    _deactivate(customer)

    with pytest.raises(Customer.DoesNotExist):
        TimelineService.log_event(customer.ref, "note", "Não pode voltar")

    assert not TimelineEvent.objects.filter(customer=customer).exists()


def test_insight_writer_refuses_inactive_customer(customer):
    _deactivate(customer)

    with pytest.raises(Customer.DoesNotExist):
        InsightService.recalculate(customer.ref)

    assert not CustomerInsight.objects.filter(customer=customer).exists()


def test_loyalty_enrollment_refuses_inactive_customer(customer):
    _deactivate(customer)

    with pytest.raises(Customer.DoesNotExist):
        LoyaltyService.enroll(customer.ref)

    assert not LoyaltyAccount.objects.filter(customer=customer).exists()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda ref: LoyaltyService.earn_points(ref, 10, "Compra"),
        lambda ref: LoyaltyService.redeem_points(ref, 10, "Resgate"),
        lambda ref: LoyaltyService.adjust_points(ref, 10, "Ajuste"),
        lambda ref: LoyaltyService.add_stamp(ref, "Compra"),
    ),
    ids=("earn", "redeem", "adjust", "stamp"),
)
def test_loyalty_mutations_refuse_inactive_customer(customer, mutation):
    LoyaltyService.enroll(customer.ref)
    _deactivate(customer)

    with pytest.raises(CustomerError) as exc:
        mutation(customer.ref)

    assert exc.value.code == "LOYALTY_NOT_ENROLLED"
    account = LoyaltyAccount.objects.get(customer=customer)
    assert account.points_balance == 0
    assert account.stamps_current == 0
    assert not LoyaltyTransaction.objects.filter(account=account).exists()


def test_bulk_tag_action_does_not_recreate_link_for_inactive_customer(
    customer,
    monkeypatch,
):
    _deactivate(customer)
    request = RequestFactory().post(
        "/admin/guestman/customer/",
        {
            "_tag_confirm": "1",
            "tags": "cliente antigo",
            "mode": "add",
        },
    )
    model_admin = CustomerAdmin(Customer, admin.site)
    monkeypatch.setattr(model_admin, "message_user", lambda *args, **kwargs: None)

    result = model_admin.tag_selected(
        request,
        Customer.objects.filter(pk=customer.pk),
    )

    assert result is None
    assert not customer.tags.exists()
    assert not CustomerTag.objects.filter(slug="cliente-antigo").exists()


@pytest.mark.parametrize("admin_class", (LegacyCustomerAdmin, CustomerAdmin))
def test_customer_admin_stale_save_cannot_restore_anonymized_pii(
    customer,
    admin_class,
):
    stale = Customer.objects.get(pk=customer.pk)
    Customer.objects.filter(pk=customer.pk).update(
        first_name="Anonimizado",
        last_name="",
        phone="",
        email="",
        is_active=False,
    )
    stale.first_name = "Nome antigo"
    stale.phone = "+5543999990999"
    stale.is_active = True
    request = RequestFactory().post("/admin/guestman/customer/change/")
    model_admin = admin_class(Customer, admin.site)

    with pytest.raises(PermissionDenied), transaction.atomic():
        model_admin.save_model(request, stale, form=Mock(), change=True)

    customer.refresh_from_db()
    assert customer.is_active is False
    assert customer.first_name == "Anonimizado"
    assert customer.phone == ""


@pytest.mark.parametrize("admin_class", (LegacyCustomerAdmin, CustomerAdmin))
def test_customer_admin_inline_save_revalidates_active_owner(
    customer,
    admin_class,
):
    _deactivate(customer)
    request = RequestFactory().post("/admin/guestman/customer/change/")
    formset = Mock()
    model_admin = admin_class(Customer, admin.site)

    with pytest.raises(PermissionDenied), transaction.atomic():
        model_admin.save_formset(
            request,
            SimpleNamespace(instance=customer),
            formset,
            change=True,
        )

    formset.save.assert_not_called()


@pytest.mark.parametrize("admin_class", (LegacyCustomerAdmin, CustomerAdmin))
def test_customer_admin_disables_and_blocks_physical_delete(customer, admin_class):
    request = RequestFactory().post("/admin/guestman/customer/delete/")
    model_admin = admin_class(Customer, admin.site)

    assert model_admin.has_delete_permission(request, customer) is False
    with pytest.raises(PermissionDenied):
        model_admin.delete_model(request, customer)
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(
            request,
            Customer.objects.filter(pk=customer.pk),
        )

    assert Customer.objects.filter(pk=customer.pk).exists()


_MUTABLE_CHILD_ADMINS = (
    LegacyCustomerAddressAdmin,
    LegacyContactPointAdmin,
    LegacyExternalIdentityAdmin,
    CustomerAddressAdmin,
    ContactPointAdmin,
    ExternalIdentityAdmin,
    CustomerIdentifierAdmin,
    CustomerPreferenceAdmin,
    CommunicationConsentAdmin,
    TimelineEventAdmin,
    LegacyLoyaltyAccountAdmin,
    LoyaltyAccountAdmin,
)


@pytest.mark.parametrize("admin_class", _MUTABLE_CHILD_ADMINS)
def test_mutable_child_admins_use_customer_first_fence(admin_class):
    assert issubclass(admin_class, CustomerOwnedPrivacyFenceAdminMixin)


@pytest.mark.parametrize(
    ("admin_class", "model", "build"),
    (
        (
            CustomerAddressAdmin,
            CustomerAddress,
            lambda customer: CustomerAddress(
                customer=customer,
                formatted_address="Rua da Privacidade, 1",
            ),
        ),
        (
            ContactPointAdmin,
            ContactPoint,
            lambda customer: ContactPoint(
                customer=customer,
                type=ContactPoint.Type.EMAIL,
                value_normalized="inativo@example.com",
            ),
        ),
        (
            ExternalIdentityAdmin,
            ExternalIdentity,
            lambda customer: ExternalIdentity(
                customer=customer,
                provider=ExternalIdentity.Provider.OTHER,
                provider_uid="privacy-fence",
            ),
        ),
        (
            CustomerIdentifierAdmin,
            CustomerIdentifier,
            lambda customer: CustomerIdentifier(
                customer=customer,
                identifier_type=IdentifierType.EMAIL,
                identifier_value="inativo@example.com",
            ),
        ),
        (
            CustomerPreferenceAdmin,
            CustomerPreference,
            lambda customer: CustomerPreference(
                customer=customer,
                category="privacidade",
                key="inativo",
                value=True,
            ),
        ),
        (
            CommunicationConsentAdmin,
            CommunicationConsent,
            lambda customer: CommunicationConsent(
                customer=customer,
                channel="email",
            ),
        ),
        (
            TimelineEventAdmin,
            TimelineEvent,
            lambda customer: TimelineEvent(
                customer=customer,
                event_type="note",
                title="Não recriar",
            ),
        ),
        (
            LoyaltyAccountAdmin,
            LoyaltyAccount,
            lambda customer: LoyaltyAccount(customer=customer),
        ),
    ),
)
def test_child_admin_create_refuses_inactive_owner(
    customer,
    admin_class,
    model,
    build,
):
    original_count = model.objects.filter(customer=customer).count()
    _deactivate(customer)
    request = RequestFactory().post("/admin/guestman/child/add/")
    model_admin = admin_class(model, admin.site)

    with pytest.raises(PermissionDenied):
        model_admin.save_model(request, build(customer), form=Mock(), change=False)

    assert model.objects.filter(customer=customer).count() == original_count


def test_child_admin_delete_refuses_inactive_owner(customer):
    address = CustomerAddress.objects.create(
        customer=customer,
        formatted_address="Rua da Privacidade, 2",
    )
    _deactivate(customer)
    request = RequestFactory().post("/admin/guestman/address/delete/")
    model_admin = CustomerAddressAdmin(CustomerAddress, admin.site)

    with pytest.raises(PermissionDenied):
        model_admin.delete_model(request, address)
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(
            request,
            CustomerAddress.objects.filter(pk=address.pk),
        )

    assert CustomerAddress.objects.filter(pk=address.pk).exists()


def test_child_admin_cannot_reassign_record_away_from_inactive_owner(customer):
    address = CustomerAddress.objects.create(
        customer=customer,
        formatted_address="Rua da Privacidade, 3",
    )
    new_owner = Customer.objects.create(
        ref="CUST-PRIVACY-ACTIVE",
        first_name="Cliente ativo",
    )
    _deactivate(customer)
    address.customer = new_owner
    request = RequestFactory().post("/admin/guestman/address/change/")
    model_admin = CustomerAddressAdmin(CustomerAddress, admin.site)

    with pytest.raises(PermissionDenied):
        model_admin.save_model(request, address, form=Mock(), change=True)

    address.refresh_from_db()
    assert address.customer_id == customer.pk


@pytest.mark.parametrize(
    "admin_class",
    (CustomerInsightAdmin, LegacyLoyaltyTransactionAdmin, LoyaltyTransactionAdmin),
)
def test_derived_and_append_only_admins_are_strictly_read_only(customer, admin_class):
    request = RequestFactory().post("/admin/guestman/derived/change/")
    if admin_class is CustomerInsightAdmin:
        model = CustomerInsight
        obj = CustomerInsight(customer=customer)
    else:
        model = LoyaltyTransaction
        account = LoyaltyAccount.objects.create(customer=customer)
        obj = LoyaltyTransaction(
            account=account,
            transaction_type="earn",
            points=1,
            balance_after=1,
            description="Imutável",
        )
    model_admin = admin_class(model, admin.site)

    assert issubclass(admin_class, PrivacyReadOnlyAdminMixin)
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request, obj) is False
    assert model_admin.has_delete_permission(request, obj) is False
    with pytest.raises(PermissionDenied):
        model_admin.save_model(request, obj, form=Mock(), change=False)
