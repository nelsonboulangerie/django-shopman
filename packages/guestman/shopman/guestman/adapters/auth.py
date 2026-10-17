"""Opt-in Guestman bridge implementing Doorman's identity ports."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import customer as customer_service
from shopman.guestman.services import identity as identity_service

logger = logging.getLogger(__name__)


class IdentityResolver:
    """Guestman implementation of Doorman's identifier-first identity port."""

    _CLAIMABLE_KINDS = frozenset({"email", "phone", "whatsapp"})

    def resolve(self, kind: str, value: str, *, purpose: str = "login"):
        from shopman.doorman.protocols.identity import IdentityConflict
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        normalized = self._normalize(kind, value)
        if not kind or not normalized:
            return None

        candidate_ids: set[int] = set()
        identifier_kinds = ("phone", "whatsapp") if kind in {"phone", "whatsapp"} else (kind,)
        candidate_ids.update(
            CustomerIdentifier.objects.filter(
                identifier_type__in=identifier_kinds,
                identifier_value=normalized,
            ).values_list("customer_id", flat=True)
        )

        contact_kinds = self._contact_kinds(kind)
        candidate_ids.update(
            ContactPoint.objects.filter(
                type__in=contact_kinds,
                value_normalized=normalized,
            ).values_list("customer_id", flat=True)
        )

        cache_filter = {}
        if kind == "email":
            cache_filter = {"email__iexact": normalized}
        elif kind in {"phone", "whatsapp"}:
            cache_filter = {"phone": normalized}
        if cache_filter:
            candidate_ids.update(
                Customer.objects.filter(**cache_filter).values_list("id", flat=True)
            )

        if len(candidate_ids) > 1:
            raise IdentityConflict("handle_has_multiple_subjects")
        if not candidate_ids:
            return None
        customer = Customer.objects.get(pk=next(iter(candidate_ids)))
        return self._to_view(
            customer,
            purpose=purpose,
            requested_kinds={kind},
            requested_value=normalized,
        )

    def get(self, subject_id, *, purpose: str):
        customer = customer_service.get_by_uuid(str(subject_id))
        return self._to_view(customer, purpose=purpose) if customer else None

    def lock_active(self, subject_id, *, purpose: str):
        customer = Customer.objects.select_for_update().filter(
            uuid=subject_id,
            is_active=True,
        ).first()
        return self._to_view(customer, purpose=purpose) if customer else None

    def create(self, kind: str, value: str):
        try:
            return self._create(kind, value)
        except (IntegrityError, identity_service.ContactPointOwnershipConflict) as exc:
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("identity_claim_conflict") from exc

    @transaction.atomic
    def _create(self, kind: str, value: str):
        self._assert_claimable_kind(kind)
        normalized = self._normalize(kind, value)
        kwargs = {"email": normalized} if kind == "email" else {"phone": normalized}
        customer = customer_service.create(
            ref=Customer.generate_ref(),
            first_name="",
            source_system="doorman",
            **kwargs,
        )
        contact_kind = {
            "email": ContactPoint.Type.EMAIL,
            "phone": ContactPoint.Type.PHONE,
            "whatsapp": ContactPoint.Type.WHATSAPP,
        }[kind]
        identity_service.ensure_contact_point(
            customer,
            type=contact_kind,
            value_normalized=normalized,
            is_primary=True,
        )
        return self._to_view(
            customer,
            purpose="login",
            requested_kinds={kind},
            requested_value=normalized,
        )

    def bind_verified_handle(self, subject_id, kind: str, value: str, *, proof: str):
        try:
            return self._bind_verified_handle(subject_id, kind, value, proof=proof)
        except (IntegrityError, identity_service.ContactPointOwnershipConflict) as exc:
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("verified_handle_conflict") from exc

    @transaction.atomic
    def _bind_verified_handle(self, subject_id, kind: str, value: str, *, proof: str):
        """Bind verification while preserving existing primary handles."""
        from django.utils import timezone
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        self._assert_claimable_kind(kind)
        verification_method = self._verification_method(kind, proof)
        customer = Customer.objects.select_for_update().get(uuid=subject_id, is_active=True)
        normalized = self._normalize(kind, value)
        existing = self.resolve(kind, normalized, purpose="login")
        if existing is not None and str(existing.subject_id) != str(subject_id):
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("verified_handle_belongs_to_another_subject")

        contact_kind = {
            "email": ContactPoint.Type.EMAIL,
            "phone": ContactPoint.Type.PHONE,
            "whatsapp": ContactPoint.Type.WHATSAPP,
        }[kind]
        has_primary_contact = ContactPoint.objects.filter(
            customer=customer,
            type__in=self._contact_kinds(kind),
            is_primary=True,
        ).exists()
        contact = identity_service.ensure_contact_point(
            customer,
            type=contact_kind,
            value_normalized=normalized,
            is_primary=not has_primary_contact,
            is_verified=False,
        )
        contact.mark_verified(verification_method)

        identifier, created = CustomerIdentifier.objects.get_or_create(
            identifier_type=kind,
            identifier_value=normalized,
            defaults={
                "customer": customer,
                "is_primary": not CustomerIdentifier.objects.filter(
                    customer=customer,
                    identifier_type=kind,
                    is_primary=True,
                ).exists(),
                "verified_at": timezone.now(),
                "source_system": "doorman",
            },
        )
        if identifier.customer_id != customer.id:
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("verified_identifier_belongs_to_another_subject")
        if not created and identifier.verified_at is None:
            identifier.verified_at = timezone.now()
            identifier.save(update_fields=["verified_at"])
        return self._to_view(
            customer,
            purpose="login",
            requested_kinds={kind},
            requested_value=normalized,
        )

    @staticmethod
    def _normalize(kind: str, value: str) -> str:
        from shopman.guestman.utils import normalize_phone

        if kind == "email":
            return str(value or "").strip().lower()
        if kind in {"phone", "whatsapp"}:
            return normalize_phone(value)
        return str(value or "").strip()

    @staticmethod
    def _contact_kinds(kind: str) -> tuple[str, ...]:
        if kind in {"phone", "whatsapp"}:
            return (ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP)
        return (kind,)

    @classmethod
    def _to_view(
        cls,
        customer: Customer,
        *,
        purpose: str,
        requested_kinds=None,
        requested_value: str | None = None,
    ):
        from shopman.doorman.protocols.identity import IdentityHandle, IdentityView

        allowed = set(requested_kinds or ())
        if purpose in {"session", "access_link"}:
            allowed.update({"phone", "whatsapp", "email"})
        by_key: dict[tuple[str, str], IdentityHandle] = {}
        contact_kinds: set[str] = set()
        for contact in customer.contact_points.filter(type__in=cls._expanded_kinds(allowed)):
            if purpose == "login" and requested_value != contact.value_normalized:
                continue
            contact_kinds.add(contact.type)
            handle = IdentityHandle(
                kind=contact.type,
                value=contact.value_normalized,
                verified=contact.is_verified,
                primary=contact.is_primary,
            )
            by_key[(handle.kind, handle.value)] = handle

        from django.apps import apps

        if apps.is_installed("shopman.guestman.contrib.identifiers"):
            from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

            for identifier in CustomerIdentifier.objects.filter(
                customer=customer,
                identifier_type__in=cls._expanded_kinds(allowed),
            ):
                if purpose == "login" and requested_value != identifier.identifier_value:
                    continue
                key = (identifier.identifier_type, identifier.identifier_value)
                previous = by_key.get(key)
                by_key[key] = IdentityHandle(
                    kind=key[0],
                    value=key[1],
                    verified=bool(identifier.verified_at) or bool(previous and previous.verified),
                    # ContactPoint owns primacy when both representations exist.
                    primary=previous.primary if previous else identifier.is_primary,
                )

        cache_values = {"phone": customer.phone, "email": customer.email}
        for kind, value in cache_values.items():
            if kind not in allowed or not value:
                continue
            if purpose == "login" and requested_value != cls._normalize(kind, value):
                continue
            if contact_kinds & cls._expanded_kinds({kind}):
                continue
            normalized = cls._normalize(kind, value)
            key = (kind, normalized)
            existing = by_key.get(key)
            if existing is not None:
                by_key[key] = IdentityHandle(
                    kind,
                    normalized,
                    existing.verified,
                    True,
                )
                continue
            if any(handle.kind == kind and handle.primary for handle in by_key.values()):
                continue
            by_key[key] = IdentityHandle(kind, normalized, False, True)

        for kind in {handle.kind for handle in by_key.values()}:
            if sum(handle.kind == kind and handle.primary for handle in by_key.values()) > 1:
                from shopman.doorman.protocols.identity import IdentityConflict

                raise IdentityConflict(f"multiple_primary_handles:{kind}")

        handles = tuple(sorted(by_key.values(), key=lambda h: (h.kind, not h.primary, h.value)))
        return IdentityView(
            subject_id=customer.uuid,
            name=customer.name,
            handles=handles,
            is_active=customer.is_active,
        )

    @staticmethod
    def _expanded_kinds(kinds: set[str]) -> set[str]:
        expanded = set(kinds)
        if "phone" in expanded or "whatsapp" in expanded:
            expanded.update({ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP})
        return expanded

    @classmethod
    def _assert_claimable_kind(cls, kind: str) -> None:
        if kind not in cls._CLAIMABLE_KINDS:
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("unsupported_identity_kind")

    @staticmethod
    def _verification_method(kind: str, proof: str) -> str:
        from shopman.doorman.protocols.identity import IdentityConflict

        methods = {
            ("phone", "sms"): ContactPoint.VerificationMethod.OTP_SMS,
            ("whatsapp", "sms"): ContactPoint.VerificationMethod.OTP_SMS,
            ("phone", "whatsapp"): ContactPoint.VerificationMethod.OTP_WHATSAPP,
            ("whatsapp", "whatsapp"): ContactPoint.VerificationMethod.OTP_WHATSAPP,
            ("email", "email"): ContactPoint.VerificationMethod.OTP_EMAIL,
        }
        try:
            return methods[(kind, proof)]
        except KeyError as exc:
            raise IdentityConflict("unsupported_verification_proof") from exc


class ManychatIdentityBridge:
    """Explicit ManyChat capability; deliberately separate from IdentityResolver."""

    def upsert_access_link_subject(self, subject_id, payload: dict):
        from shopman.guestman.contrib.manychat.service import ManychatService

        customer = customer_service.get_by_uuid(str(subject_id))
        if not customer:
            return None
        source_system = "manychat" if payload.get("id") else "access_link"
        try:
            customer = ManychatService.sync_customer(
                customer,
                payload,
                source_system=source_system,
            )
        except (IntegrityError, identity_service.ContactPointOwnershipConflict):
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("manychat_identity_conflict") from None
        return IdentityResolver._to_view(customer, purpose="access_link") if customer and customer.is_active else None

    def upsert_subscriber(self, subscriber_data: dict):
        from shopman.guestman.contrib.manychat.service import ManychatService

        try:
            customer, _created = ManychatService.sync_subscriber(
                self._enriched_subscriber(subscriber_data)
            )
        except (IntegrityError, identity_service.ContactPointOwnershipConflict):
            from shopman.doorman.protocols.identity import IdentityConflict

            raise IdentityConflict("manychat_identity_conflict") from None
        return IdentityResolver._to_view(customer, purpose="access_link") if customer and customer.is_active else None

    def last_input_text(self, subscriber_id: str) -> str:
        from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        text = (info or {}).get("last_input_text")
        return text.strip() if isinstance(text, str) else ""

    def phone(self, subscriber_id: str) -> str:
        from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        return ManychatSubscriberResolver.phone_from_subscriber_info(info)

    @staticmethod
    def _enriched_subscriber(subscriber_data: dict) -> dict:
        from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

        payload = dict(subscriber_data or {})
        if str(payload.get("whatsapp_id") or "").strip():
            return payload
        subscriber_id = str(payload.get("id") or "").strip()
        if not subscriber_id:
            return payload
        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        phone = ManychatSubscriberResolver.phone_from_subscriber_info(info)
        if phone:
            payload["whatsapp_id"] = phone
        for key in ("ig_id", "ig_username", "first_name", "last_name", "email"):
            if not payload.get(key) and (info or {}).get(key):
                payload[key] = info[key]
        return payload
