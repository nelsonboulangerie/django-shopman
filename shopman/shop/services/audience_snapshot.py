"""Sealed audience cohorts and subtract-only late materialization."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from shopman.utils.phone import normalize_phone

from shopman.shop.models import AudienceSnapshot, AudienceSnapshotMember
from shopman.shop.services.audience import AudienceResult, Recipient
from shopman.shop.services.marketing_contracts import MarketingContractError

SNAPSHOT_RETENTION = timedelta(days=90)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotAudience:
    recipients: tuple[Recipient, ...] = ()
    excluded_by_reason: dict[str, int] = field(default_factory=dict)
    degraded_sources: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.recipients)


@transaction.atomic
def create_snapshot(
    resolution: AudienceResult,
    *,
    rules: dict | None,
    announcement=None,
    version: int = 1,
    now: datetime | None = None,
) -> AudienceSnapshot:
    """Seal exactly the eligible set; no recipient contact is persisted."""

    now = now or timezone.now()
    if resolution.degraded_sources:
        raise MarketingContractError(
            code="audience_degraded",
            detail="Não foi possível conferir todas as fontes da audiência.",
        )
    if resolution.expires_at and resolution.expires_at <= now:
        raise MarketingContractError(
            code="audience_preview_expired",
            detail="A contagem da audiência venceu. Atualize antes de aprovar.",
        )

    recipients = resolution.all_recipients()
    customer_refs = {recipient.customer_ref for recipient in recipients if recipient.customer_ref}
    from shopman.guestman.models import Customer

    customer_ids = dict(
        Customer.objects.filter(ref__in=customer_refs, is_active=True).values_list("ref", "pk")
    )
    full_rules = dict(rules or {})
    rule_hash = _keyed_hash(_canonical_json(full_rules))
    summary = resolution.summary()

    if announcement is not None:
        existing = AudienceSnapshot.objects.filter(
            announcement=announcement,
            version=version,
        ).first()
        if existing:
            if existing.rule_hash != rule_hash or existing.cohort_hash != resolution.cohort_hash:
                raise MarketingContractError(
                    code="snapshot_version_conflict",
                    detail="Esta versão já possui outro snapshot de audiência.",
                    current_version=version,
                )
            return existing

    snapshot = AudienceSnapshot.objects.create(
        announcement=announcement,
        version=version,
        summary=summary,
        rule_summary=_sanitized_rule_summary(full_rules),
        rule_hash=rule_hash,
        cohort_hash=resolution.cohort_hash,
        policy_version=resolution.policy_version,
        calculated_at=resolution.calculated_at or now,
        expires_at=resolution.expires_at or now,
        retention_until=now + SNAPSHOT_RETENTION,
    )
    members = []
    for recipient in recipients:
        customer_id = customer_ids.get(recipient.customer_ref)
        subscription_ref = recipient.source_subscription_ref or None
        if customer_id is None and subscription_ref is None:
            raise MarketingContractError(
                code="audience_member_identity_missing",
                detail="Um membro da audiência não possui identidade protegida.",
            )
        members.append(
            AudienceSnapshotMember(
                snapshot=snapshot,
                customer_id=customer_id,
                subscription_ref=subscription_ref,
                target_key=_target_key(recipient),
                reasons=sorted(recipient.reasons),
                is_vip=recipient.is_vip,
                preferred_hour=recipient.preferred_hour,
            )
        )
    AudienceSnapshotMember.objects.bulk_create(members)
    return snapshot


def materialize_active_recipients(
    snapshot: AudienceSnapshot,
    *,
    now: datetime | None = None,
) -> SnapshotAudience:
    """Resolve contacts from sealed members and only remove newly ineligible ones."""

    now = now or timezone.now()
    members = list(snapshot.members.select_related("customer"))
    customer_refs = {
        member.customer.ref
        for member in members
        if member.customer_id and member.customer and member.customer.is_active
    }
    try:
        from shopman.guestman import ConsentService

        statuses = ConsentService.get_customer_statuses("whatsapp", customer_refs)
    except Exception:
        logger.warning("marketing.snapshot_consent_source_unavailable")
        return SnapshotAudience(
            excluded_by_reason={"consent_unavailable": len(members)},
            degraded_sources=("consent",),
        )

    subscription_refs = {
        member.subscription_ref for member in members if member.subscription_ref
    }
    from shopman.shop.adapters.audience_sources import active_alert_subscriptions

    subscriptions = {
        sub.ref: sub
        for sub in active_alert_subscriptions(subscription_refs, now=now)
    }
    excluded: dict[str, int] = {}
    by_phone: dict[str, Recipient] = {}

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for member in members:
        reasons = frozenset(member.reasons or [])
        subscription = subscriptions.get(member.subscription_ref)
        if member.subscription_ref and subscription is None:
            exclude("subscription_inactive")
            continue

        customer = member.customer if member.customer_id else None
        if customer is not None and not customer.is_active:
            exclude("customer_inactive")
            continue
        customer_ref = customer.ref if customer is not None else ""
        status = statuses.get(customer_ref, "")
        if status == "opted_out":
            exclude("global_optout")
            continue
        if "alerts" not in reasons and status != "opted_in":
            exclude("missing_consent")
            continue

        phone = normalize_phone(
            customer.phone if customer is not None else subscription.contact_phone
        )
        if not phone:
            exclude("invalid_contact")
            continue
        if phone in by_phone:
            exclude("late_duplicate")
            continue
        by_phone[phone] = Recipient(
            phone=phone,
            customer_ref=customer_ref,
            customer_uuid=str(getattr(customer, "uuid", "") or "") if customer else "",
            first_name=(getattr(customer, "first_name", "") or "").strip() if customer else "",
            reasons=reasons,
            is_vip=member.is_vip,
            preferred_hour=member.preferred_hour,
            source_subscription_ref=str(member.subscription_ref or ""),
        )

    return SnapshotAudience(
        recipients=tuple(by_phone.values()),
        excluded_by_reason=excluded,
    )


def _sanitized_rule_summary(rules: dict) -> dict:
    summary = {}
    for key, value in rules.items():
        if key == "customer_refs":
            summary["customer_refs_count"] = len(value) if isinstance(value, list) else 0
        else:
            summary[key] = value
    return summary


def _target_key(recipient: Recipient) -> str:
    if recipient.customer_ref:
        identity = f"customer:{recipient.customer_ref}"
    elif recipient.source_subscription_ref:
        identity = f"subscription:{recipient.source_subscription_ref}"
    else:
        identity = f"phone:{normalize_phone(recipient.phone)}"
    return _keyed_hash(identity)


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _keyed_hash(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()
