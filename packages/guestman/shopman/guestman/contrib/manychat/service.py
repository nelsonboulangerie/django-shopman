"""Manychat sync service."""

import logging

from django.db import transaction
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.models import Customer

logger = logging.getLogger("guestman.manychat")


# Recusa de identificação. O texto sai no corpo do 409 e é lido por gente e pelo
# fluxo do ManyChat, então ele não pode falar de `whatsapp_id`: quem cai aqui é,
# tipicamente, alguém que chegou pela Instagram e cujo assinante não carrega
# telefone nenhum. Dizer "faltou whatsapp_id" mandava procurar o campo errado.
UNIDENTIFIED_SUBSCRIBER = (
    "Nao foi possivel identificar este assinante: nenhum telefone conhecido. "
    "Assinante sem telefone (ex.: contato que chegou pelo Instagram) precisa "
    "entrar pelo site, com o proprio numero."
)


class ManychatService:
    """
    Service for Manychat integration.

    Uses @classmethod for extensibility (see spec 000 section 12.1).
    """

    @classmethod
    def sync_subscriber(
        cls,
        subscriber_data: dict,
        source_system: str = "manychat",
    ) -> tuple[Customer, bool]:
        """
        Sync a Manychat subscriber to Guestman.

        Args:
            subscriber_data: Manychat subscriber data with fields like:
                - id: Manychat subscriber ID
                - first_name: First name
                - last_name: Last name
                - whatsapp_id: WhatsApp channel identifier (canonical)
                - email: Email
                - ig_id: Instagram ID (optional)
                - ig_username: Instagram username (optional)
                - fb_id: Facebook ID (optional)
                - custom_fields: Dict of custom fields (optional)
            source_system: Source identifier

        Returns:
            Tuple of (Customer, created: bool)
        """
        manychat_id = subscriber_data.get("id")
        if not manychat_id:
            raise ValueError("Subscriber data must contain 'id' field")
        incoming_phone = cls._preferred_phone(subscriber_data)

        with transaction.atomic():
            # Try to find existing customer by Manychat ID
            customer = cls._find_by_manychat_id(manychat_id)

            if customer:
                if not customer.phone and not incoming_phone:
                    raise ValueError(UNIDENTIFIED_SUBSCRIBER)
                # Update existing customer
                cls._update_customer(customer, subscriber_data)
                cls.sync_consent(customer, subscriber_data)
                return customer, False

            # Try to find by other identifiers
            customer = cls._find_by_identifiers(subscriber_data)

            if customer:
                if not customer.phone and not incoming_phone:
                    raise ValueError(UNIDENTIFIED_SUBSCRIBER)
                # Link Manychat ID to existing customer
                cls._add_manychat_identifiers(customer, subscriber_data, source_system)
                cls._update_customer(customer, subscriber_data)
                cls.sync_consent(customer, subscriber_data)
                return customer, False

            if not incoming_phone:
                raise ValueError(UNIDENTIFIED_SUBSCRIBER)

            # Create new customer
            customer = cls._create_customer(subscriber_data, source_system)
            cls._add_manychat_identifiers(customer, subscriber_data, source_system)
            cls.sync_consent(customer, subscriber_data)
            return customer, True

    #: Campo de opt-in do ManyChat → canal de ``CommunicationConsent``.
    #:
    #: O ManyChat manda o ESTADO do opt-in no payload, não um evento de "saiu". Isso é
    #: melhor do que parecer: sincronizar estado é idempotente e cobre os dois sentidos
    #: — a pessoa que responde SAIR e a que volta depois. Um handler de evento só cobriria
    #: a saída, e a volta ficaria presa.
    OPTIN_FIELD_TO_CHANNEL = {
        "optin_whatsapp": "whatsapp",
        "optin_email": "email",
        "optin_phone": "sms",
    }

    @classmethod
    def sync_consent(cls, customer: Customer, subscriber_data: dict) -> dict[str, bool]:
        """Refletir o opt-in do ManyChat no ``CommunicationConsent`` do guestman.

        Existe porque o rodapé das mensagens promete "responda SAIR para parar", e o
        flow nativo do ManyChat cumpre isso **lá** — sem isto, a pessoa saía no ManyChat
        e continuava consentida aqui, e a próxima campanha a alcançaria de novo. Promessa
        que o sistema não cumpre é pior do que promessa que ele não faz.

        Devolve ``{canal: consentido}`` só para o que veio no payload. Campo ausente NÃO
        é tratado como revogação: webhook parcial é comum, e assumir "ausente = não
        consente" apagaria consentimento por silêncio.
        """
        from shopman.guestman.contrib.consent.service import ConsentService

        applied: dict[str, bool] = {}
        for field, channel in cls.OPTIN_FIELD_TO_CHANNEL.items():
            if field not in subscriber_data:
                continue
            value = subscriber_data.get(field)
            if value is None:
                continue
            opted_in = bool(value)
            try:
                if opted_in:
                    ConsentService.grant_consent(customer.ref, channel, source="manychat")
                else:
                    ConsentService.revoke_consent(customer.ref, channel)
            except Exception:
                logger.warning(
                    "manychat.consent_sync_failed customer=%s channel=%s",
                    customer.ref, channel, exc_info=True,
                )
                continue
            applied[channel] = opted_in
        return applied

    @classmethod
    def sync_customer(
        cls,
        customer: Customer,
        subscriber_data: dict,
        source_system: str = "manychat",
    ) -> Customer:
        """Bind trusted ManyChat/access-link identity data to a known customer."""
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer.pk)
            cls._add_manychat_identifiers(customer, subscriber_data, source_system)
            cls._update_customer(customer, subscriber_data, source_system=source_system)
            customer.refresh_from_db()
            return customer

    @classmethod
    def _find_by_manychat_id(cls, manychat_id: str) -> Customer | None:
        """Find customer by Manychat ID."""
        try:
            ident = CustomerIdentifier.objects.select_related("customer").get(
                identifier_type=IdentifierType.MANYCHAT,
                identifier_value=manychat_id,
            )
            return ident.customer if ident.customer.is_active else None
        except CustomerIdentifier.DoesNotExist:
            return None

    @classmethod
    def _find_by_identifiers(cls, data: dict) -> Customer | None:
        """Try to find customer by phone, email, or other identifiers."""
        # Try phone
        for phone in cls._normalized_phone_values(data):
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.PHONE,
                    identifier_value=phone,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass
            customer = Customer.objects.filter(phone=phone, is_active=True).first()
            if customer:
                return customer
            from shopman.guestman.services import customer as customer_service
            customer = customer_service.get_by_phone(phone)
            if customer:
                return customer

        # Try email
        if data.get("email"):
            email = data["email"].lower().strip()
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.EMAIL,
                    identifier_value=email,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass
            customer = Customer.objects.filter(email=email, is_active=True).first()
            if customer:
                return customer

        # Try WhatsApp phone
        for phone in cls._normalized_phone_values(data):
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.WHATSAPP,
                    identifier_value=phone,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass
            customer = Customer.objects.filter(phone=phone, is_active=True).first()
            if customer:
                return customer
            from shopman.guestman.services import customer as customer_service
            customer = customer_service.get_by_phone(phone)
            if customer:
                return customer

        return None

    @classmethod
    def _create_customer(cls, data: dict, source_system: str) -> Customer:
        """Create new customer from Manychat data."""
        import hashlib

        # Generate ref from Manychat ID
        hash_value = hashlib.md5(data["id"].encode()).hexdigest()[:8].upper()
        ref = f"MC-{hash_value}"

        customer = Customer.objects.create(
            ref=ref,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            phone=cls._preferred_phone(data),
            source_system=source_system,
            metadata={"manychat_custom_fields": data.get("custom_fields", {})},
        )
        cls._sync_contact_points(customer, data, source_system)
        return customer

    @classmethod
    def _update_customer(
        cls,
        customer: Customer,
        data: dict,
        source_system: str = "manychat",
    ) -> None:
        """Update customer with Manychat data."""
        updated = False

        if data.get("first_name") and not customer.first_name:
            customer.first_name = data["first_name"]
            updated = True

        if data.get("last_name") and not customer.last_name:
            customer.last_name = data["last_name"]
            updated = True

        if data.get("email") and not customer.email:
            customer.email = data["email"]
            updated = True

        phone = cls._preferred_phone(data)
        if phone and not customer.phone:
            if cls._phone_conflicts(customer, phone):
                raise ValueError("Phone is already linked to another customer.")
            customer.phone = phone
            updated = True

        # Update custom fields in metadata
        if data.get("custom_fields"):
            if "manychat_custom_fields" not in customer.metadata:
                customer.metadata["manychat_custom_fields"] = {}
            customer.metadata["manychat_custom_fields"].update(data["custom_fields"])
            updated = True

        if updated:
            customer.save()
        cls._sync_contact_points(customer, data, source_system)

    @classmethod
    def _add_manychat_identifiers(
        cls,
        customer: Customer,
        data: dict,
        source_system: str,
    ) -> None:
        """Add Manychat-related identifiers to customer."""
        identifiers_to_add = []

        # Manychat ID
        if data.get("id"):
            identifiers_to_add.append(
                (IdentifierType.MANYCHAT, data["id"], True)
            )

        # Phone
        phone = cls._preferred_phone(data)
        if phone:
            identifiers_to_add.append(
                (IdentifierType.PHONE, phone, False)
            )

        # Email
        if data.get("email"):
            identifiers_to_add.append(
                (IdentifierType.EMAIL, data["email"].lower().strip(), False)
            )

        # Instagram
        if data.get("ig_id"):
            identifiers_to_add.append(
                (IdentifierType.INSTAGRAM, data["ig_id"], False)
            )

        # Facebook
        if data.get("fb_id"):
            identifiers_to_add.append(
                (IdentifierType.FACEBOOK, data["fb_id"], False)
            )

        # WhatsApp
        contact_phone = cls._contact_phone(data, source_system)
        if contact_phone:
            identifiers_to_add.append(
                (IdentifierType.WHATSAPP, contact_phone, False)
            )

        # Telegram
        if data.get("tg_id"):
            identifiers_to_add.append(
                (IdentifierType.TELEGRAM, data["tg_id"], False)
            )

        for id_type, id_value, is_primary in identifiers_to_add:
            if not id_value:
                continue
            identifier, _created = CustomerIdentifier.objects.get_or_create(
                identifier_type=id_type,
                identifier_value=id_value,
                defaults={
                    "customer": customer,
                    "is_primary": is_primary,
                    "source_system": source_system,
                },
            )
            if identifier.customer_id != customer.id:
                raise ValueError("Identifier is already linked to another customer.")

    @classmethod
    def _sync_contact_points(
        cls,
        customer: Customer,
        data: dict,
        source_system: str,
    ) -> None:
        from shopman.guestman.models import ContactPoint

        verification_ref = data.get("id") or ""
        phone = cls._preferred_phone(data)
        if phone:
            cls._ensure_verified_contact(
                customer,
                ContactPoint.Type.PHONE,
                phone,
                verification_ref,
            )

        contact_phone = cls._contact_phone(data, source_system)
        if contact_phone:
            cls._ensure_verified_contact(
                customer,
                ContactPoint.Type.WHATSAPP,
                contact_phone,
                verification_ref,
            )

        if data.get("email"):
            cls._ensure_verified_contact(
                customer,
                ContactPoint.Type.EMAIL,
                data["email"],
                verification_ref,
            )

    @classmethod
    def _ensure_verified_contact(
        cls,
        customer: Customer,
        contact_type: str,
        raw_value: str,
        verification_ref: str = "",
    ) -> None:
        from django.utils import timezone
        from shopman.guestman.models import ContactPoint
        from shopman.guestman.services import identity as identity_service

        value = ContactPoint.normalize_value(raw_value, contact_type)
        if not value:
            return

        existing = ContactPoint.objects.filter(
            type=contact_type,
            value_normalized=value,
        ).first()
        if existing and existing.customer_id != customer.id:
            raise ValueError("Contact point is already linked to another customer.")

        has_other_primary = ContactPoint.objects.filter(
            customer=customer,
            type=contact_type,
            is_primary=True,
        ).exclude(value_normalized=value).exists()
        contact = identity_service.ensure_contact_point(
            customer,
            type=contact_type,
            value_normalized=value,
            is_primary=not has_other_primary,
            is_verified=True,
        )

        updates: list[str] = []
        if contact.verification_method != ContactPoint.VerificationMethod.CHANNEL_ASSERTED:
            contact.verification_method = ContactPoint.VerificationMethod.CHANNEL_ASSERTED
            updates.append("verification_method")
        if contact.verified_at is None:
            contact.verified_at = timezone.now()
            updates.append("verified_at")
        if verification_ref and contact.verification_ref != verification_ref:
            contact.verification_ref = verification_ref
            updates.append("verification_ref")
        if updates:
            contact.save(update_fields=[*updates, "updated_at"])

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number. Delegates to centralized normalize_phone."""
        from shopman.guestman.utils import normalize_phone

        return normalize_phone(str(phone)) if phone else ""

    @classmethod
    def _preferred_phone(cls, data: dict) -> str:
        values = cls._normalized_phone_values(data)
        return values[0] if values else ""

    @classmethod
    def _contact_phone(cls, data: dict, source_system: str) -> str:
        return cls._preferred_phone(data) if source_system == "manychat" else ""

    @classmethod
    def _normalized_phone_values(cls, data: dict) -> list[str]:
        phone = cls._normalize_phone(data.get("whatsapp_id", ""))
        return [phone] if phone else []

    @classmethod
    def _phone_conflicts(cls, customer: Customer, phone: str) -> bool:
        from shopman.guestman.models import ContactPoint

        normalized = cls._normalize_phone(phone)
        if not normalized:
            return False
        if (
            Customer.objects.filter(phone=normalized, is_active=True)
            .exclude(pk=customer.pk)
            .exists()
        ):
            return True
        return ContactPoint.objects.filter(
            type__in=[ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP],
            value_normalized=normalized,
        ).exclude(customer=customer).exists()
