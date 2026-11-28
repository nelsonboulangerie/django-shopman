from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import pytest
from django import forms
from django.contrib.admin.sites import AdminSite
from django.db import close_old_connections, connection, connections, transaction
from django.test import RequestFactory
from shopman.guestman.admin import (
    ContactPointAdmin as DjangoContactPointAdmin,
)
from shopman.guestman.admin import (
    ContactPointInline as DjangoContactPointInline,
)
from shopman.guestman.admin_forms import (
    ContactPointAdminForm,
    ContactPointInlineFormSet,
)
from shopman.guestman.contrib.admin_unfold.admin import (
    ContactPointAdmin as UnfoldContactPointAdmin,
)
from shopman.guestman.contrib.admin_unfold.admin import (
    ContactPointInline as UnfoldContactPointInline,
)
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import identity as identity_service

ADMIN_CLASSES = (DjangoContactPointAdmin, UnfoldContactPointAdmin)
INLINE_CLASSES = (DjangoContactPointInline, UnfoldContactPointInline)


def _customer(ref: str) -> Customer:
    return Customer.objects.create(ref=ref, first_name=ref)


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_claims_canonical_phone_for_whatsapp(db, admin_class):
    customer = _customer(f"ADMIN-{admin_class.__module__.split('.')[-1]}")
    contact = ContactPoint(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized="+5541999991111",
        value_display="(41) 99999-1111",
        is_primary=True,
    )

    admin_instance = admin_class(ContactPoint, AdminSite())
    admin_instance.save_model(
        RequestFactory().post("/admin/guestman/contactpoint/add/"),
        contact,
        Mock(),
        change=False,
    )

    owners = set(
        ContactPoint.objects.filter(
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
            value_normalized="+5541999991111",
        ).values_list("customer_id", flat=True)
    )
    assert owners == {customer.pk}
    assert ContactPoint.objects.filter(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized="+5541999991111",
    ).exists()


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_never_splits_phone_family_ownership(db, admin_class):
    incumbent = _customer(f"OWNER-{admin_class.__module__.split('.')[-1]}")
    contender = _customer(f"OTHER-{admin_class.__module__.split('.')[-1]}")
    identity_service.ensure_contact_point(
        incumbent,
        type=ContactPoint.Type.PHONE,
        value_normalized="+5541999992222",
    )
    contact = ContactPoint(
        customer=contender,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized="+5541999992222",
    )

    admin_instance = admin_class(ContactPoint, AdminSite())
    with pytest.raises(identity_service.ContactPointOwnershipConflict):
        admin_instance.save_model(
            RequestFactory().post("/admin/guestman/contactpoint/add/"),
            contact,
            Mock(),
            change=False,
        )

    assert set(
        ContactPoint.objects.filter(
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
            value_normalized="+5541999992222",
        ).values_list("customer_id", flat=True)
    ) == {incumbent.pk}


def test_contact_point_admin_form_rejects_foreign_family_owner(db):
    incumbent = _customer("FORM-OWNER")
    contender = _customer("FORM-OTHER")
    identity_service.ensure_contact_point(
        incumbent,
        type=ContactPoint.Type.PHONE,
        value_normalized="+5541999993333",
    )

    form = ContactPointAdminForm(
        data={
            "customer": contender.pk,
            "type": ContactPoint.Type.WHATSAPP,
            "value_normalized": "+55 (41) 99999-3333",
            "value_display": "",
            "is_primary": False,
            "is_verified": False,
            "verification_method": ContactPoint.VerificationMethod.UNVERIFIED,
            "verified_at": "",
            "verification_ref": "",
        }
    )

    assert form.is_valid() is False
    assert "value_normalized" in form.errors
    assert ContactPoint.objects.filter(customer=contender).count() == 0


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_does_not_expose_verification_proof_for_edit(admin_class):
    readonly = set(admin_class.readonly_fields)
    assert {
        "is_primary",
        "is_verified",
        "verification_method",
        "verified_at",
        "verification_ref",
    }.issubset(readonly)
    assert admin_class.form is ContactPointAdminForm


@pytest.mark.parametrize("inline_class", INLINE_CLASSES)
def test_contact_point_inline_uses_same_claim_form_and_readonly_proof(inline_class):
    assert inline_class.form is ContactPointAdminForm
    assert inline_class.formset is ContactPointInlineFormSet
    assert {
        "is_primary",
        "is_verified",
        "verification_method",
        "verified_at",
    }.issubset(set(inline_class.readonly_fields))


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_blocks_phone_delete_while_whatsapp_depends_on_it(
    db,
    admin_class,
):
    owner = _customer(f"DELETE-{admin_class.__module__.split('.')[-1]}")
    contender = _customer(f"CLAIM-{admin_class.__module__.split('.')[-1]}")
    value = "+5541999995555"
    identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
    )
    canonical = ContactPoint.objects.get(
        customer=owner,
        type=ContactPoint.Type.PHONE,
        value_normalized=value,
    )

    with pytest.raises(forms.ValidationError, match="WhatsApp"):
        admin_class(ContactPoint, AdminSite()).delete_model(
            RequestFactory().post("/admin/guestman/contactpoint/delete/"),
            canonical,
        )

    assert ContactPoint.objects.filter(pk=canonical.pk).exists()
    with pytest.raises(identity_service.ContactPointOwnershipConflict):
        identity_service.ensure_contact_point(
            contender,
            type=ContactPoint.Type.PHONE,
            value_normalized=value,
        )


def test_contact_point_inline_formset_blocks_canonical_phone_delete(db):
    owner = _customer("INLINE-DELETE")
    value = "+5541999996666"
    identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
    )
    canonical = ContactPoint.objects.get(
        customer=owner,
        type=ContactPoint.Type.PHONE,
        value_normalized=value,
    )

    formset = object.__new__(ContactPointInlineFormSet)
    with pytest.raises(forms.ValidationError, match="WhatsApp"):
        formset.delete_existing(canonical, commit=True)

    assert ContactPoint.objects.filter(pk=canonical.pk).exists()


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_cannot_promote_secondary_phone_or_change_cache(
    db,
    admin_class,
):
    owner = _customer(f"PRIMARY-{admin_class.__module__.split('.')[-1]}")
    primary_value = "+5541999997777"
    secondary_value = "+5541999998888"
    identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=primary_value,
        is_primary=True,
    )
    secondary = identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.PHONE,
        value_normalized=secondary_value,
        is_primary=False,
    )
    assert secondary.is_primary is False

    secondary.is_primary = True
    admin_class(ContactPoint, AdminSite()).save_model(
        RequestFactory().post("/admin/guestman/contactpoint/change/"),
        secondary,
        Mock(),
        change=True,
    )

    secondary.refresh_from_db()
    owner.refresh_from_db()
    assert secondary.is_primary is False
    assert owner.phone == primary_value


@pytest.mark.parametrize("admin_class", ADMIN_CLASSES)
def test_contact_point_admin_stale_edit_preserves_fresh_proof_primary_and_cache(
    db,
    admin_class,
):
    owner = _customer(f"STALE-{admin_class.__module__.split('.')[-1]}")
    value = "+5541999999991"
    contact = identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
        is_primary=True,
    )
    stale = ContactPoint.objects.get(pk=contact.pk)
    fresh = ContactPoint.objects.get(pk=contact.pk)
    fresh.mark_verified(ContactPoint.VerificationMethod.OTP_WHATSAPP, ref="proof-ref")

    stale.value_display = "(41) 99999-9991"
    stale.is_primary = False
    admin_class(ContactPoint, AdminSite()).save_model(
        RequestFactory().post("/admin/guestman/contactpoint/change/"),
        stale,
        Mock(),
        change=True,
    )

    stale.refresh_from_db()
    owner.refresh_from_db()
    assert stale.value_display == "(41) 99999-9991"
    assert stale.is_verified is True
    assert stale.verification_method == ContactPoint.VerificationMethod.OTP_WHATSAPP
    assert stale.verification_ref == "proof-ref"
    assert stale.verified_at is not None
    assert stale.is_primary is True
    assert owner.phone == value


def test_contact_point_inline_form_stale_edit_preserves_fresh_proof(db):
    owner = _customer("STALE-INLINE")
    value = "+5541999999992"
    contact = identity_service.ensure_contact_point(
        owner,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=value,
        is_primary=True,
    )
    stale = ContactPoint.objects.get(pk=contact.pk)
    form = ContactPointAdminForm(
        instance=stale,
        data={
            "customer": owner.pk,
            "type": ContactPoint.Type.WHATSAPP,
            "value_normalized": value,
            "value_display": "WhatsApp balcão",
            "is_primary": False,
            "is_verified": False,
            "verification_method": ContactPoint.VerificationMethod.UNVERIFIED,
            "verified_at": "",
            "verification_ref": "",
        },
    )
    assert form.is_valid(), form.errors
    fresh = ContactPoint.objects.get(pk=contact.pk)
    fresh.mark_verified(ContactPoint.VerificationMethod.OTP_WHATSAPP, ref="inline-proof")

    saved = form.save()
    saved.refresh_from_db()
    owner.refresh_from_db()
    assert saved.value_display == "WhatsApp balcão"
    assert saved.is_verified is True
    assert saved.verification_method == ContactPoint.VerificationMethod.OTP_WHATSAPP
    assert saved.verification_ref == "inline-proof"
    assert saved.verified_at is not None
    assert saved.is_primary is True
    assert owner.phone == value


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL transactions",
)
def test_django_and_unfold_admin_race_cannot_split_phone_family():
    first = _customer("ADMIN-RACE-DJANGO")
    second = _customer("ADMIN-RACE-UNFOLD")
    value = "+5541999994444"
    ready = Barrier(2)

    def create(admin_class, customer):
        close_old_connections()
        try:
            ready.wait(timeout=10)
            contact = ContactPoint(
                customer=customer,
                type=ContactPoint.Type.WHATSAPP,
                value_normalized=value,
            )
            with transaction.atomic():
                admin_class(ContactPoint, AdminSite()).save_model(
                    RequestFactory().post("/admin/guestman/contactpoint/add/"),
                    contact,
                    Mock(),
                    change=False,
                )
            return contact.customer_id
        except identity_service.ContactPointOwnershipConflict as exc:
            return exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result(20)
            for future in (
                pool.submit(create, DjangoContactPointAdmin, first),
                pool.submit(create, UnfoldContactPointAdmin, second),
            )
        ]

    successes = [result for result in results if not isinstance(result, Exception)]
    conflicts = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert set(
        ContactPoint.objects.filter(
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
            value_normalized=value,
        ).values_list("customer_id", flat=True)
    ) == {successes[0]}
