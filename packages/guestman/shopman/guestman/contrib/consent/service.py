"""Consent service — immutable evidence plus a rebuildable current projection."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    CommunicationConsentEvent,
    ConsentEventType,
    ConsentProofStatus,
    ConsentPurpose,
    ConsentStatus,
)
from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)

DEFAULT_MARKETING_DISCLOSURE_VERSION = "marketing-general-pt-BR-v1"
DEFAULT_MARKETING_DISCLOSURE = (
    "Quero receber novidades e ofertas pelo canal escolhido. Posso cancelar a "
    "qualquer momento em Minha conta e consultar a Política de Privacidade."
)
CONSENT_STATUS_BATCH_SIZE = 20_000


class ConsentService:
    """Public API for consent changes and reads.

    Every change first appends evidence and then updates ``CommunicationConsent``
    in the same transaction. The mutable row is only a read projection; it can be
    reconstructed from the immutable event stream.
    """

    @classmethod
    @transaction.atomic
    def grant_consent(
        cls,
        customer_ref: str,
        channel: str,
        source: str = "",
        legal_basis: str = "consent",
        ip_address: str | None = None,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
        disclosure_text: str = DEFAULT_MARKETING_DISCLOSURE,
        disclosure_version: str = DEFAULT_MARKETING_DISCLOSURE_VERSION,
        locale: str = "pt-BR",
        actor_ref: str = "",
        occurred_at: datetime | None = None,
    ) -> CommunicationConsent:
        """Append verified opt-in evidence and refresh the current projection."""

        customer = Customer.objects.select_for_update().get(ref=customer_ref, is_active=True)
        occurred_at = occurred_at or timezone.now()
        disclosure_text = (disclosure_text or "").strip()
        disclosure_version = (disclosure_version or "").strip()
        if not disclosure_text or not disclosure_version:
            raise ValueError("opt-in exige texto e versão do disclosure")

        event = cls._append_event(
            customer=customer,
            channel=channel,
            purpose=purpose,
            event_type=ConsentEventType.GRANTED,
            resulting_status=ConsentStatus.OPTED_IN,
            legal_basis=legal_basis,
            source=source,
            disclosure_text=disclosure_text,
            disclosure_version=disclosure_version,
            proof_status=ConsentProofStatus.VERIFIED,
            locale=locale,
            ip_address=ip_address,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
        consent, _ = CommunicationConsent.objects.update_or_create(
            customer=customer,
            channel=channel,
            defaults={
                "purpose": purpose,
                "status": ConsentStatus.OPTED_IN,
                "source": source,
                "legal_basis": legal_basis,
                "ip_address": ip_address,
                "consented_at": occurred_at,
                "revoked_at": None,
                "policy_version": disclosure_version,
                "disclosure_hash": event.disclosure_hash,
                "evidence_hash": event.evidence_hash,
                "locale": locale,
                "proof_status": ConsentProofStatus.VERIFIED,
                "last_event_ref": event.ref,
            },
        )
        return consent

    @classmethod
    @transaction.atomic
    def revoke_consent(
        cls,
        customer_ref: str,
        channel: str,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
        source: str = "customer_request",
        locale: str = "pt-BR",
        ip_address: str | None = None,
        actor_ref: str = "",
        occurred_at: datetime | None = None,
    ) -> CommunicationConsent:
        """Append a revocation; opt-out is valid even without an earlier opt-in."""

        customer = Customer.objects.select_for_update().get(ref=customer_ref, is_active=True)
        occurred_at = occurred_at or timezone.now()
        event = cls._append_event(
            customer=customer,
            channel=channel,
            purpose=purpose,
            event_type=ConsentEventType.REVOKED,
            resulting_status=ConsentStatus.OPTED_OUT,
            legal_basis="consent",
            source=source,
            disclosure_text="",
            disclosure_version="",
            proof_status=ConsentProofStatus.VERIFIED,
            locale=locale,
            ip_address=ip_address,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )
        consent, _ = CommunicationConsent.objects.update_or_create(
            customer=customer,
            channel=channel,
            defaults={
                "purpose": purpose,
                "status": ConsentStatus.OPTED_OUT,
                "source": source,
                "legal_basis": "consent",
                "ip_address": ip_address,
                "revoked_at": occurred_at,
                "evidence_hash": event.evidence_hash,
                "locale": locale,
                "last_event_ref": event.ref,
            },
        )
        return consent

    @classmethod
    def _append_event(
        cls,
        *,
        customer: Customer,
        channel: str,
        purpose: str,
        event_type: str,
        resulting_status: str,
        legal_basis: str,
        source: str,
        disclosure_text: str,
        disclosure_version: str,
        proof_status: str,
        locale: str,
        ip_address: str | None,
        actor_ref: str,
        occurred_at: datetime,
    ) -> CommunicationConsentEvent:
        event_ref = uuid.uuid4()
        disclosure_hash = _sha256(disclosure_text) if disclosure_text else ""
        customer_ref_hash = _keyed_hash(customer.ref)
        evidence = {
            "ref": str(event_ref),
            "subject": customer_ref_hash,
            "channel": channel,
            "purpose": purpose,
            "event_type": event_type,
            "resulting_status": resulting_status,
            "legal_basis": legal_basis,
            "source": source,
            "disclosure_hash": disclosure_hash,
            "disclosure_version": disclosure_version,
            "proof_status": proof_status,
            "locale": locale,
            "occurred_at": occurred_at.isoformat(),
        }
        evidence_hash = _keyed_hash(
            json.dumps(evidence, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
        return CommunicationConsentEvent.objects.create(
            ref=event_ref,
            customer=customer,
            customer_ref_hash=customer_ref_hash,
            channel=channel,
            purpose=purpose,
            event_type=event_type,
            resulting_status=resulting_status,
            legal_basis=legal_basis,
            source=source,
            disclosure_text=disclosure_text,
            disclosure_version=disclosure_version,
            disclosure_hash=disclosure_hash,
            evidence_hash=evidence_hash,
            proof_status=proof_status,
            locale=locale,
            ip_address=ip_address,
            actor_ref=actor_ref,
            occurred_at=occurred_at,
        )

    @classmethod
    @transaction.atomic
    def rebuild_current_state(
        cls,
        customer_ref: str,
        channel: str,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
    ) -> CommunicationConsent:
        """Rebuild one current row from its latest event, proving history suffices."""

        customer = Customer.objects.select_for_update().get(ref=customer_ref, is_active=True)
        event = (
            CommunicationConsentEvent.objects.filter(
                customer=customer,
                channel=channel,
                purpose=purpose,
            )
            .order_by("-occurred_at", "-pk")
            .first()
        )
        if event is None:
            raise CommunicationConsentEvent.DoesNotExist
        consent, _ = CommunicationConsent.objects.update_or_create(
            customer=customer,
            channel=channel,
            defaults={
                "purpose": purpose,
                "status": event.resulting_status,
                "source": event.source,
                "legal_basis": event.legal_basis,
                "ip_address": event.ip_address,
                "consented_at": (
                    event.occurred_at
                    if event.resulting_status == ConsentStatus.OPTED_IN
                    else None
                ),
                "revoked_at": (
                    event.occurred_at
                    if event.resulting_status == ConsentStatus.OPTED_OUT
                    else None
                ),
                "policy_version": event.disclosure_version,
                "disclosure_hash": event.disclosure_hash,
                "evidence_hash": event.evidence_hash,
                "locale": event.locale,
                "proof_status": event.proof_status,
                "last_event_ref": event.ref,
            },
        )
        return consent

    @classmethod
    def has_consent(
        cls,
        customer_ref: str,
        channel: str,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
    ) -> bool:
        return CommunicationConsent.objects.filter(
            customer__ref=customer_ref,
            customer__is_active=True,
            channel=channel,
            purpose=purpose,
            status=ConsentStatus.OPTED_IN,
            proof_status=ConsentProofStatus.VERIFIED,
        ).exists()

    @classmethod
    def get_consents(cls, customer_ref: str) -> list[CommunicationConsent]:
        return list(
            CommunicationConsent.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
            )
        )

    @classmethod
    @transaction.atomic
    def redact_expired_ip(cls, *, days: int | None = None) -> dict[str, int]:
        """Remove IP bruto vencido sem apagar a prova imutável do consentimento.

        Finalidade, texto apresentado, hashes, estado e instante continuam
        append-only. A única mutação admitida aqui é a minimização programada
        do identificador auxiliar, limitada a no máximo 90 dias.
        """

        configured = (
            days
            if days is not None
            else getattr(settings, "SHOPMAN_CONSENT_IP_RETENTION_DAYS", 90)
        )
        retention_days = min(90, max(1, int(configured)))
        cutoff = timezone.now() - timedelta(days=retention_days)

        current = CommunicationConsent.objects.filter(
            ip_address__isnull=False,
            updated_at__lt=cutoff,
        )
        current_count = current.update(ip_address=None)

        events = CommunicationConsentEvent.objects.filter(
            ip_address__isnull=False,
            occurred_at__lt=cutoff,
        )
        # O QuerySet público recusa update para proteger a trilha. A chamada à
        # implementação base existe só neste boundary purpose-bound de retenção.
        event_count = models.QuerySet.update(events, ip_address=None)
        return {"current": current_count, "events": event_count}

    @classmethod
    def get_opted_in_channels(
        cls,
        customer_ref: str,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
    ) -> list[str]:
        return list(
            CommunicationConsent.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
                purpose=purpose,
                status=ConsentStatus.OPTED_IN,
                proof_status=ConsentProofStatus.VERIFIED,
            ).values_list("channel", flat=True)
        )

    @classmethod
    def get_marketable_customers(
        cls,
        channel: str,
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
    ) -> list[str]:
        return list(
            CommunicationConsent.objects.filter(
                channel=channel,
                purpose=purpose,
                status=ConsentStatus.OPTED_IN,
                proof_status=ConsentProofStatus.VERIFIED,
                customer__is_active=True,
            ).values_list("customer__ref", flat=True)
        )

    @classmethod
    def get_customer_statuses(
        cls,
        channel: str,
        customer_refs: set[str] | list[str] | tuple[str, ...],
        *,
        purpose: str = ConsentPurpose.MARKETING_GENERAL,
    ) -> dict[str, str]:
        refs = tuple({str(ref).strip() for ref in customer_refs if str(ref).strip()})
        if not refs:
            return {}
        statuses = {}
        for offset in range(0, len(refs), CONSENT_STATUS_BATCH_SIZE):
            rows = CommunicationConsent.objects.filter(
                channel=channel,
                purpose=purpose,
                customer__ref__in=refs[offset : offset + CONSENT_STATUS_BATCH_SIZE],
                customer__is_active=True,
            ).values_list("customer__ref", "status", "proof_status")
            for customer_ref, status, proof_status in rows:
                if status == ConsentStatus.OPTED_OUT:
                    # Revocation is authoritative even when historical opt-in proof
                    # was incomplete. Never weaken a do-not-contact tombstone.
                    statuses[customer_ref] = ConsentStatus.OPTED_OUT
                elif (
                    status == ConsentStatus.OPTED_IN
                    and proof_status == ConsentProofStatus.VERIFIED
                ):
                    statuses[customer_ref] = ConsentStatus.OPTED_IN
                else:
                    statuses[customer_ref] = ConsentStatus.PENDING
        return statuses


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _keyed_hash(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
