"""Shared forms and save hooks for Guestman's Django Admin surfaces."""

from __future__ import annotations

from django import forms
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import identity as identity_service

_PHONE_FAMILY = (ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP)


class ContactPointAdminForm(forms.ModelForm):
    """Keep Admin contact writes behind Guestman's canonical ownership claim.

    Ownership coordinates are immutable after creation.  Operators retain the
    useful add/delete and primary/display workflows, while replacing a handle
    is represented honestly as deleting one claim and adding another.  Proof
    fields are never editable here: verification belongs to the flow that
    actually observed the proof.
    """

    class Meta:
        model = ContactPoint
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        if customer is None and self.instance.customer_id:
            customer = self.instance.customer

        contact_type = cleaned.get("type")
        raw_value = cleaned.get("value_normalized")
        if not customer or not contact_type or not raw_value:
            return cleaned

        normalized = ContactPoint.normalize_value(raw_value, contact_type)
        cleaned["value_normalized"] = normalized
        self.instance.value_normalized = normalized

        if self.instance.pk:
            persisted = ContactPoint.objects.filter(pk=self.instance.pk).first()
            if persisted is not None:
                changed_coordinates = (
                    persisted.customer_id != customer.pk
                    or persisted.type != contact_type
                    or persisted.value_normalized != normalized
                )
                if changed_coordinates:
                    raise forms.ValidationError(
                        _(
                            "Cliente, tipo e valor formam a titularidade do contato e "
                            "não podem ser trocados. Exclua este contato e adicione o novo."
                        )
                    )

        family = _PHONE_FAMILY if contact_type in _PHONE_FAMILY else (contact_type,)
        foreign_owner_exists = (
            ContactPoint.objects.filter(
                type__in=family,
                value_normalized=normalized,
            )
            .exclude(customer_id=customer.pk)
            .exists()
        )
        if foreign_owner_exists:
            self.add_error(
                "value_normalized",
                _("Este contato já pertence a outro cliente."),
            )
        return cleaned

    def save(self, commit=True):
        contact = super().save(commit=False)
        if commit and contact._state.adding:
            return save_new_contact_point(contact)
        if commit:
            save_existing_contact_point(contact)
            self.save_m2m()
        return contact


def save_new_contact_point(contact: ContactPoint) -> ContactPoint:
    """Persist a new Admin contact through the concurrency-safe claim service."""
    saved = identity_service.ensure_contact_point(
        contact.customer,
        type=contact.type,
        value_normalized=contact.value_normalized,
        is_primary=contact.is_primary,
        is_verified=False,
    )
    if contact.value_display and saved.value_display != contact.value_display:
        saved.value_display = contact.value_display
        saved.save(update_fields=["value_display", "updated_at"])

    # Django Admin keeps using the ModelForm instance for logging and m2m save.
    contact.__dict__.update(saved.__dict__)
    return contact


@transaction.atomic
def save_existing_contact_point(contact: ContactPoint) -> ContactPoint:
    """Persist only the Admin-editable presentation field from a fresh row."""
    owner_id = ContactPoint.objects.filter(pk=contact.pk).values_list(
        "customer_id",
        flat=True,
    ).get()
    Customer.objects.select_for_update().get(pk=owner_id, is_active=True)
    persisted = ContactPoint.objects.select_for_update().get(
        pk=contact.pk,
        customer_id=owner_id,
    )
    if persisted.value_display != contact.value_display:
        persisted.value_display = contact.value_display
        persisted.save(update_fields=["value_display", "updated_at"])

    # Admin logging and form consumers must observe the authoritative row, not
    # the stale instance that arrived before a concurrent verification write.
    contact.__dict__.update(persisted.__dict__)
    return contact


@transaction.atomic
def delete_contact_point_from_admin(contact: ContactPoint) -> None:
    """Delete an Admin contact without orphaning a WhatsApp ownership claim."""
    Customer.objects.select_for_update().get(
        pk=contact.customer_id,
        is_active=True,
    )
    persisted = ContactPoint.objects.select_for_update().get(pk=contact.pk)
    if persisted.type == ContactPoint.Type.PHONE:
        has_whatsapp_sibling = ContactPoint.objects.filter(
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=persisted.value_normalized,
        ).exists()
        if has_whatsapp_sibling:
            raise forms.ValidationError(
                _(
                    "Este telefone sustenta um contato WhatsApp. "
                    "Exclua primeiro o contato WhatsApp."
                )
            )
    persisted.delete()


class ContactPointInlineFormSet(BaseInlineFormSet):
    """Apply the same ownership-safe delete rule to both Admin inlines."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form) and form.instance.pk:
                contact = ContactPoint.objects.filter(pk=form.instance.pk).first()
                if (
                    contact is not None
                    and contact.type == ContactPoint.Type.PHONE
                    and ContactPoint.objects.filter(
                        type=ContactPoint.Type.WHATSAPP,
                        value_normalized=contact.value_normalized,
                    ).exists()
                ):
                    raise forms.ValidationError(
                        _(
                            "Um telefone vinculado ao WhatsApp não pode ser excluído "
                            "antes do contato WhatsApp."
                        )
                    )

    def delete_existing(self, obj, commit=True):
        if commit:
            delete_contact_point_from_admin(obj)


class CanonicalContactPointAdminMixin:
    """Route standalone ModelAdmin creation through the canonical claim."""

    def save_model(self, request, obj, form, change):
        if not change and obj._state.adding:
            self._privacy_lock_active_customers({obj.customer_id})
            save_new_contact_point(obj)
            return
        if change:
            save_existing_contact_point(obj)
            return
        return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        delete_contact_point_from_admin(obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            pks = tuple(queryset.values_list("pk", flat=True))
            owner_ids = set(
                ContactPoint.objects.filter(pk__in=pks).values_list(
                    "customer_id",
                    flat=True,
                )
            )
            self._privacy_lock_active_customers(owner_ids)
            contacts = list(
                ContactPoint.objects.select_for_update()
                .filter(pk__in=pks)
                .order_by("type", "pk")
            )
            # WhatsApp sorts after PHONE, so make the dependency order explicit.
            contacts.sort(key=lambda contact: contact.type == ContactPoint.Type.PHONE)
            for contact in contacts:
                delete_contact_point_from_admin(contact)
