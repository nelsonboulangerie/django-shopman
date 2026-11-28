"""Guestman identity services."""

from __future__ import annotations

from contextvars import ContextVar

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


# ── Número que muda de dono (D3, OC-07) ──────────────────────────────
#
# O telefone é autenticador restrito, nunca identidade permanente: a operadora
# recicla o número, e quem o recebe passa no código e manda mensagem do mesmo
# WhatsApp. O Guestman, dono da posse do contato, diz em UM lugar quando o número
# deixou de ser de alguém (``contact_reassigned``), e cada dono de chave que ainda
# trata o número como desta pessoa corta a sua: o contrib de identificadores tira o
# identificador do provedor de mensagens; o orquestrador desliga a conversa.

#: Telefone e WhatsApp dividem o número; a família inteira é a posse.
PHONE_FAMILY: tuple[str, ...] = (ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP)

#: Quem percebeu que o número saiu. Os provedores entram com o próprio nome.
SOURCE_CONTACT_REMOVED = "contact_removed"
SOURCE_PROVIDER_SUBSCRIBER_MOVED = "provider_subscriber_moved"
SOURCE_CUSTOMER_NOT_ME = "customer_not_me"

#: Quem pediu a retirada em curso, para o aviso do ``post_delete`` dizer a causa
#: verdadeira em vez de "contato apagado".
_release_source: ContextVar[str] = ContextVar("guestman_contact_release_source", default="")


def announce_contact_left(
    customer_id,
    contact_type: str,
    value: str,
    *,
    source: str,
    verification_ref: str = "",
) -> bool:
    """Avisa que ``value`` deixou de ser número do cliente ``customer_id``.

    Só avisa quando o cadastro já não guarda o número em contato nenhum da
    família: apagar só o contato de voz de um número que segue como WhatsApp não
    é perda do número. Devolve se avisou.
    """
    from shopman.guestman.signals import contact_reassigned

    if contact_type not in PHONE_FAMILY or not value or customer_id is None:
        return False
    if ContactPoint.objects.filter(
        customer_id=customer_id,
        type__in=PHONE_FAMILY,
        value_normalized=value,
    ).exists():
        return False
    customer_ref = (
        Customer.objects.filter(pk=customer_id).values_list("ref", flat=True).first() or ""
    )
    # ADR-025: escrita acoplada — o número sai e, no mesmo ato, saem o assinante do
    # WhatsApp e o vínculo da conversa; depois do commit haveria uma janela em que o
    # novo titular já fala pela conversa e pelo assinante da pessoa anterior.
    contact_reassigned.send(
        sender=ContactPoint,
        customer_id=customer_id,
        customer_ref=customer_ref,
        contact_type=contact_type,
        value=value,
        verification_ref=verification_ref or "",
        source=source,
    )
    return True


def _announce_deleted_contact(sender, instance, **kwargs) -> None:
    """``post_delete`` do contato: qualquer caminho que apaga avisa, sem lembrar.

    Troca de número na conta, liberação no balcão, exclusão no Admin, unificação:
    todos apagam a linha, e todos passam por aqui, na mesma transação.
    """
    announce_contact_left(
        instance.customer_id,
        instance.type,
        instance.value_normalized,
        source=_release_source.get() or SOURCE_CONTACT_REMOVED,
        verification_ref=instance.verification_ref,
    )


def connect_signals() -> None:
    from django.db.models.signals import post_delete

    post_delete.connect(
        _announce_deleted_contact,
        sender=ContactPoint,
        dispatch_uid="guestman_identity_announce_contact_left",
    )


@transaction.atomic
def release_reassigned_contact(value: str, *, source: str) -> list[str]:
    """O número ``value`` agora é de OUTRA pessoa: ele sai do cadastro de quem o tinha.

    É a porta de entrada do sinal de troca de dono (D3c), venha ele de um provedor
    (aviso de troca de identidade do WhatsApp, API de reciclagem da operadora) ou
    da própria pessoa que recebeu o número ("não sou eu", D3d). Apaga os contatos
    da família telefone com esse valor e zera o cache ``Customer.phone`` que ainda
    o guardar; o ``post_delete`` leva junto as chaves de login e emite
    ``contact_reassigned``. Devolve os refs de quem perdeu o número.

    ⚠️ Não cria nem move nada: o novo titular entra pela porta de sempre (código no
    número, mensagem no WhatsApp) e nasce como cadastro próprio, sem herdar o
    endereço, os pedidos e a conversa de quem tinha o número.
    """
    from shopman.guestman.utils import normalize_phone

    normalized = normalize_phone(value)
    if not normalized:
        return []
    contacts = list(
        ContactPoint.objects.select_for_update()
        .filter(type__in=PHONE_FAMILY, value_normalized=normalized)
        .select_related("customer")
    )
    owners = {contact.customer_id: contact.customer.ref for contact in contacts}
    cached_only = Customer.objects.filter(phone=normalized).exclude(pk__in=owners)
    for customer_id, ref in cached_only.values_list("pk", "ref"):
        owners[customer_id] = ref
    if not owners:
        return []
    # A família inteira sai: o último contato a sair é o que dispara o aviso.
    token = _release_source.set(source)
    try:
        for contact in contacts:
            contact.delete()
    finally:
        _release_source.reset(token)
    # ``.update()`` e não ``.save()``: o save do Customer re-materializa o contato
    # a partir do cache, e o número voltaria na hora.
    Customer.objects.filter(pk__in=owners, phone=normalized).update(phone="")
    for customer_id in owners:
        if not any(contact.customer_id == customer_id for contact in contacts):
            # Número só no cache (sem contato): ninguém apagou linha, então ninguém
            # avisou. Avisa aqui.
            announce_contact_left(
                customer_id,
                ContactPoint.Type.PHONE,
                normalized,
                source=source,
            )
    return sorted(owners.values())
