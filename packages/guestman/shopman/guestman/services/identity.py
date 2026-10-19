"""Guestman identity services."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from shopman.guestman.models import ContactPoint, Customer, ExternalIdentity


class ContactPointOwnershipConflict(RuntimeError):
    """A normalized contact value is already owned by another customer."""


def _claim_contact_point(
    customer: Customer,
    *,
    type: str,
    value_normalized: str,
    is_primary: bool,
    is_verified: bool,
) -> tuple[ContactPoint, bool]:
    """Claim one globally unique contact value, translating write races."""
    existing = (
        ContactPoint.objects.select_for_update()
        .filter(type=type, value_normalized=value_normalized)
        .first()
    )
    if existing is not None:
        if existing.customer_id != customer.pk:
            raise ContactPointOwnershipConflict("contact_value_has_another_owner")
        return existing, False

    try:
        with transaction.atomic():
            return ContactPoint.objects.get_or_create(
                customer=customer,
                type=type,
                value_normalized=value_normalized,
                defaults={
                    # Promotion happens only after ownership is established.
                    # ContactPoint.save still makes the first row of a type
                    # primary, which is safe because no incumbent exists.
                    "is_primary": False,
                    "is_verified": is_verified,
                },
            )
    except IntegrityError as exc:
        # The unique (type, value) constraint arbitrates writers that locked
        # different Customer rows.  Keep the database exception inside a
        # savepoint, then expose a domain conflict from the Guestman boundary.
        owner_id = ContactPoint.objects.filter(
            type=type,
            value_normalized=value_normalized,
        ).values_list("customer_id", flat=True).first()
        if owner_id != customer.pk:
            raise ContactPointOwnershipConflict("contact_value_has_another_owner") from exc
        raise


@transaction.atomic
def ensure_contact_point(
    customer: Customer,
    *,
    type: str,
    value_normalized: str,
    is_primary: bool = True,
    is_verified: bool = False,
) -> ContactPoint:
    """Ensure a normalized contact point exists for the customer.

    PHONE is the ownership claim for the phone/WhatsApp family.  A WhatsApp
    contact therefore claims (or validates) the matching PHONE row first, so
    all supported writers arbitrate the same globally unique database key.
    Direct model writes are intentionally not an ownership API.
    """
    customer = Customer.objects.select_for_update().get(
        pk=customer.pk,
        is_active=True,
    )
    value_normalized = ContactPoint.normalize_value(value_normalized, type)
    family_primary_value = None
    if type in {ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP}:
        foreign_family_owner = (
            ContactPoint.objects.select_for_update()
            .filter(
                type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
                value_normalized=value_normalized,
            )
            .exclude(customer=customer)
            .exists()
        )
        if foreign_family_owner:
            raise ContactPointOwnershipConflict("contact_value_has_another_owner")
        family_primary_values = set(
            ContactPoint.objects.filter(
                customer=customer,
                type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
                is_primary=True,
            ).values_list("value_normalized", flat=True)
        )
        if len(family_primary_values) > 1:
            raise ContactPointOwnershipConflict("phone_family_has_multiple_primaries")
        family_primary_value = next(iter(family_primary_values), None)

    def preserve_family_primary(contact: ContactPoint, *, created: bool) -> None:
        if (
            created
            and not is_primary
            and family_primary_value
            and family_primary_value != value_normalized
            and contact.is_primary
        ):
            # ContactPoint.save promotes the first row of each concrete type.
            # The authentication invariant is family-wide: claiming a PHONE
            # row for a secondary WhatsApp handle must not silently replace
            # the established phone/WhatsApp primary or its Customer cache.
            ContactPoint.objects.filter(pk=contact.pk).update(is_primary=False)
            Customer.objects.filter(pk=customer.pk).update(phone=family_primary_value)
            contact.is_primary = False

    if type == ContactPoint.Type.WHATSAPP:
        canonical, canonical_created = _claim_contact_point(
            customer,
            type=ContactPoint.Type.PHONE,
            value_normalized=value_normalized,
            is_primary=False,
            is_verified=False,
        )
        preserve_family_primary(canonical, created=canonical_created)

    contact_point, created = _claim_contact_point(
        customer,
        type=type,
        value_normalized=value_normalized,
        is_primary=is_primary,
        is_verified=is_verified,
    )
    preserve_family_primary(contact_point, created=created)
    updates: list[str] = []
    if is_primary and not contact_point.is_primary:
        contact_point.set_as_primary()
    if not created:
        if is_verified and not contact_point.is_verified:
            contact_point.is_verified = True
            updates.append("is_verified")
        if updates:
            contact_point.save(update_fields=updates)
    return contact_point


@transaction.atomic
def ensure_external_identity(
    customer: Customer,
    *,
    provider: str,
    external_id: str,
    metadata: dict | None = None,
) -> ExternalIdentity:
    """Ensure an external identity is linked to the customer."""
    customer = Customer.objects.select_for_update().get(
        pk=customer.pk,
        is_active=True,
    )
    identity, created = ExternalIdentity.objects.get_or_create(
        provider=provider,
        provider_uid=external_id,
        defaults={
            "customer": customer,
            "provider_meta": metadata or {},
        },
    )
    if identity.customer_id != customer.id:
        raise ValueError("External identity is already linked to another customer.")
    if not created and metadata is not None and identity.provider_meta != metadata:
        identity.provider_meta = metadata
        identity.save(update_fields=["provider_meta"])
    return identity


#: Campo de cache do Customer → (tipo do principal, família que ele espelha).
#: Telefone e WhatsApp dividem o número.
_CACHE_FAMILIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "phone": (ContactPoint.Type.PHONE, (ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP)),
    "email": (ContactPoint.Type.EMAIL, (ContactPoint.Type.EMAIL,)),
}


@transaction.atomic
def replace_primary_contact(customer: Customer, *, field: str, new_value: str) -> None:
    """TROCA o telefone ou o e-mail principal: o novo entra, o antigo SAI.

    É o gesto de editar o campo ``phone``/``email`` do cadastro (decisão da
    coordenação, A4-1). O principal de hoje, e o valor que o cache guardava,
    deixam de ser contato do cadastro: o ``ContactPoint`` é apagado, e o
    ``post_delete`` do contrib de identificadores leva junto a chave de login
    do mesmo valor. Sem isso o número antigo, que a operadora recicla, seguiria
    abrindo a conta por OTP.

    Contatos secundários adicionados de propósito ficam: adicionar é outro
    gesto. ``new_value`` vazio só retira o principal. ``new_value`` chega
    normalizado.
    """
    primary_type, family = _CACHE_FAMILIES[field]
    customer = Customer.objects.select_for_update().get(pk=customer.pk, is_active=True)

    old_values = set(
        ContactPoint.objects.filter(
            customer=customer,
            type__in=family,
            is_primary=True,
        ).values_list("value_normalized", flat=True)
    )
    cached = getattr(customer, field, "") or ""
    if cached:
        old_values.add(cached)
    old_values.discard(new_value)

    if new_value:
        ensure_contact_point(
            customer,
            type=primary_type,
            value_normalized=new_value,
            is_primary=True,
        )

    ContactPoint.objects.filter(
        customer=customer,
        type__in=family,
        value_normalized__in=old_values,
    ).delete()
    Customer.objects.filter(pk=customer.pk).update(**{field: new_value})
