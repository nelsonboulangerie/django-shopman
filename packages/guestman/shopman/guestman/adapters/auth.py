"""Guestman adapter for Doorman's CustomerResolver protocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.doorman.protocols.customer import AuthCustomerInfo

from shopman.guestman.models import Customer
from shopman.guestman.services import customer as customer_service
from shopman.guestman.services import identity as identity_service

logger = logging.getLogger(__name__)


class CustomerResolver:
    """Adapter: Guestman implements Doorman's CustomerResolver."""

    def get_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        c = customer_service.get_by_phone(phone)
        return self._to_info(c) if c else None

    def get_by_email(self, email: str) -> AuthCustomerInfo | None:
        c = customer_service.get_by_email(email)
        return self._to_info(c) if c else None

    def get_by_uuid(self, uuid) -> AuthCustomerInfo | None:
        c = customer_service.get_by_uuid(str(uuid))
        return self._to_info(c) if c else None

    def get_by_identifier(self, identifier_type: str, identifier_value: str) -> AuthCustomerInfo | None:
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        if not identifier_type or not identifier_value:
            return None
        ident = (
            CustomerIdentifier.objects.select_related("customer")
            .filter(identifier_type=identifier_type, identifier_value=str(identifier_value))
            .first()
        )
        if not ident or not ident.customer.is_active:
            return None
        return self._to_info(ident.customer)

    def upsert_access_link_customer(self, customer_id, payload: dict) -> AuthCustomerInfo | None:
        c = customer_service.get_by_uuid(str(customer_id))
        if not c:
            return None

        from shopman.guestman.contrib.manychat.service import ManychatService

        source_system = "manychat" if payload.get("id") else "access_link"
        c = ManychatService.sync_customer(c, payload, source_system=source_system)
        if not c or not c.is_active:
            return None
        return self._to_info(c)

    def upsert_manychat_subscriber(self, subscriber_data: dict) -> AuthCustomerInfo | None:
        from shopman.guestman.contrib.manychat.service import ManychatService

        customer, _created = ManychatService.sync_subscriber(
            self._enriched_subscriber(subscriber_data)
        )
        if not customer or not customer.is_active:
            return None
        return self._to_info(customer)

    def manychat_last_input_text(self, subscriber_id: str) -> str:
        """A última mensagem que o contato mandou, direto do ManyChat.

        O access link precisa do `NB-XxXx` que a pessoa enviou. Pedir isso ao FLUXO
        significa depender de qual variável o seletor do ManyChat oferece naquele
        bloco — que muda por canal e por conta. Perguntar à API tira a adivinhação:
        o corpo do request passa a carregar só o `subscriber_id`.
        """
        from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        text = (info or {}).get("last_input_text")
        return text.strip() if isinstance(text, str) else ""

    @staticmethod
    def _enriched_subscriber(subscriber_data: dict) -> dict:
        """Completa o telefone do assinante consultando o ManyChat, quando falta.

        Contato de WhatsApp tem `whatsapp_phone` preenchido e `phone` NULO — medido
        num contato real. Um fluxo que mande o campo errado (ou variável não
        renderizada) chegava aqui sem telefone e a pessoa era recusada, mesmo com o
        ManyChat sabendo o número o tempo todo. Agora a gente pergunta.
        """
        payload = dict(subscriber_data or {})
        if str(payload.get("whatsapp_id") or "").strip():
            return payload

        subscriber_id = str(payload.get("id") or "").strip()
        if not subscriber_id:
            return payload

        from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        phone = ManychatSubscriberResolver.phone_from_subscriber_info(info)
        if phone:
            logger.info("manychat: telefone do assinante %s veio do getInfo", subscriber_id)
            payload["whatsapp_id"] = phone
        for key in ("ig_id", "ig_username", "first_name", "last_name", "email"):
            if not payload.get(key) and (info or {}).get(key):
                payload[key] = info[key]
        return payload

    def create_for_phone(self, phone: str) -> AuthCustomerInfo:
        c = customer_service.create(
            ref=Customer.generate_ref(),
            first_name="",
            phone=phone,
            source_system="doorman",
        )
        identity_service.ensure_contact_point(
            c,
            type="whatsapp",
            value_normalized=c.phone,
            is_primary=True,
        )
        return self._to_info(c)

    def create_for_email(self, email: str) -> AuthCustomerInfo:
        from shopman.guestman.models import ContactPoint

        c = customer_service.create(
            ref=Customer.generate_ref(),
            first_name="",
            email=email,
            source_system="doorman",
        )
        identity_service.ensure_contact_point(
            c,
            type=ContactPoint.Type.EMAIL,
            value_normalized=c.email,
            is_primary=True,
        )
        return self._to_info(c)

    @staticmethod
    def _to_info(c: Customer) -> AuthCustomerInfo:
        from shopman.doorman.protocols.customer import AuthCustomerInfo
        from shopman.guestman.models import ContactPoint

        primary_phone = (
            c.contact_points.filter(
                type__in=[ContactPoint.Type.WHATSAPP, ContactPoint.Type.PHONE],
            )
            .order_by("-is_primary", "-is_verified", "-updated_at")
            .values_list("value_normalized", flat=True)
            .first()
        )
        primary_email = (
            c.contact_points.filter(type=ContactPoint.Type.EMAIL)
            .order_by("-is_primary", "-is_verified", "-updated_at")
            .values_list("value_normalized", flat=True)
            .first()
        )

        return AuthCustomerInfo(
            uuid=c.uuid,
            name=c.name,
            phone=primary_phone or c.phone,
            email=primary_email or c.email,
            is_active=c.is_active,
        )
