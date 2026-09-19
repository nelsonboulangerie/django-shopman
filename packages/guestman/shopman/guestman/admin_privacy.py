"""Canonical Customer privacy fence for Django Admin implementations."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from shopman.guestman.models import Customer


class CustomerPrivacyFenceAdminMixin:
    """Keep Customer Admin writes behind the canonical active-owner lock.

    Django wraps change-form POSTs in one transaction.  ``save_model`` is the
    first write hook, so the Customer row lock acquired there remains held
    while ``form.save_m2m()`` writes tags and ``save_formset`` writes inlines.
    The request marker lets an intentional deactivation finish its related
    writes: the customer was active and locked before this same POST changed it.
    """

    _privacy_fence_request_attr = "_guestman_customer_privacy_fence_pk"

    @staticmethod
    def _lock_active_customer(customer_pk):
        try:
            return Customer.objects.select_for_update().get(
                pk=customer_pk,
                is_active=True,
            )
        except Customer.DoesNotExist as exc:
            raise PermissionDenied(
                "Este cadastro não está mais ativo e não pode ser alterado."
            ) from exc

    def save_model(self, request, obj, form, change):
        if change:
            self._lock_active_customer(obj.pk)
        super().save_model(request, obj, form, change)
        if not change:
            self._lock_active_customer(obj.pk)
        setattr(request, self._privacy_fence_request_attr, obj.pk)

    def save_formset(self, request, form, formset, change):
        customer = form.instance
        if getattr(request, self._privacy_fence_request_attr, None) != customer.pk:
            self._lock_active_customer(customer.pk)
            setattr(request, self._privacy_fence_request_attr, customer.pk)
        return super().save_formset(request, form, formset, change)

    def has_delete_permission(self, request, obj=None):
        """Physical deletion must only happen through the privacy workflow."""
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied(
            "Use o fluxo de privacidade para excluir dados deste cliente."
        )

    def delete_queryset(self, request, queryset):
        raise PermissionDenied(
            "Use o fluxo de privacidade para excluir dados destes clientes."
        )


class CustomerOwnedPrivacyFenceAdminMixin:
    """Serialize a child Admin mutation behind its active Customer owner.

    The default relationship is a direct ``customer`` foreign key/one-to-one.
    Admins for deeper relationships should either override the lookup helpers or
    expose the model as read-only.  Both the currently persisted owner and the
    owner selected in the submitted form are locked, so reassignment cannot
    evade a concurrent privacy deletion.
    """

    privacy_customer_lookup = "customer_id"

    @staticmethod
    def _deny_inactive_owner():
        raise PermissionDenied(
            "O cliente deste registro não está mais ativo e o registro não pode ser alterado."
        )

    def _privacy_customer_id_from_object(self, obj):
        return getattr(obj, self.privacy_customer_lookup, None)

    def _privacy_persisted_customer_ids(self, *, pks) -> set:
        return set(
            self.model._default_manager.filter(pk__in=pks).values_list(
                self.privacy_customer_lookup,
                flat=True,
            )
        )

    def _privacy_lock_active_customers(self, customer_ids) -> None:
        expected = {customer_id for customer_id in customer_ids if customer_id is not None}
        if not expected:
            self._deny_inactive_owner()
        locked = set(
            Customer.objects.select_for_update()
            .filter(pk__in=expected, is_active=True)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if locked != expected:
            self._deny_inactive_owner()

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            proposed_owner = self._privacy_customer_id_from_object(obj)
            persisted_owners = (
                self._privacy_persisted_customer_ids(pks=(obj.pk,))
                if change and obj.pk is not None
                else set()
            )
            owners = persisted_owners | {proposed_owner}
            self._privacy_lock_active_customers(owners)

            # Re-read only after the Customer locks.  A canonical concurrent
            # reassignment must acquire one of the same locks and cannot slip
            # between the initial owner hint and this validation.
            if change:
                current_owners = self._privacy_persisted_customer_ids(pks=(obj.pk,))
                if not current_owners or not current_owners.issubset(owners):
                    self._deny_inactive_owner()
            return super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        with transaction.atomic():
            owners = self._privacy_persisted_customer_ids(pks=(obj.pk,))
            self._privacy_lock_active_customers(owners)
            current_owners = self._privacy_persisted_customer_ids(pks=(obj.pk,))
            if not current_owners or current_owners != owners:
                self._deny_inactive_owner()
            return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            pks = tuple(queryset.values_list("pk", flat=True))
            owners = self._privacy_persisted_customer_ids(pks=pks)
            self._privacy_lock_active_customers(owners)
            current_owners = self._privacy_persisted_customer_ids(pks=pks)
            if current_owners != owners:
                self._deny_inactive_owner()
            return super().delete_queryset(request, queryset)


class PrivacyReadOnlyAdminMixin:
    """Make a derived/append-only privacy surface genuinely read-only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied("Este registro é somente leitura.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Este registro é somente leitura.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Estes registros são somente leitura.")
