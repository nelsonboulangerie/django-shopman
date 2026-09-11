"""Persistent stock/bake alerts with occurrence-scoped delivery.

Subscribe is open to anonymous shoppers (phone only) and logged-in customers.
The opt-in stays active until pause, expiry or revocation.  Each real occurrence
gets a semantic identity and one durable delivery receipt per subscription.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from shopman.utils.phone import normalize_phone

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

logger = logging.getLogger(__name__)

STOCK_ALERT_DISCLOSURE_VERSION = "stock-availability-pt-BR-v2"
STOCK_ALERT_DISCLOSURE = (
    "Quero receber avisos por WhatsApp sobre novas ocorrências deste produto. "
    "Posso pausar ou cancelar este aviso; a proteção atual expira em 30 dias."
)


def has_pending(sku: str, *, alert_types: tuple[str, ...] = ()) -> bool:
    """Cheap guard for the arrival/bake receivers (indexed exists())."""
    from shopman.storefront.models import StockAlertSubscription

    qs = StockAlertSubscription.objects.active().filter(sku=sku)
    if alert_types:
        qs = qs.filter(alert_type__in=alert_types)
    return qs.exists()


def needs_stock_reconciliation(sku: str) -> bool:
    """Keep an open stock cycle accurate even when its last opt-in disappears."""
    from shopman.storefront.models import StockAlertOccurrence

    return has_pending(sku, alert_types=("stock_back",)) or StockAlertOccurrence.objects.filter(
        sku=sku,
        event_type="stock_back",
        closed_at__isnull=True,
    ).exists()


def default_alert_type(sku: str) -> str:
    """Que aviso o cliente está pedindo quando toca o sino deste produto?

    ⚠️ Quem decide é o SERVIDOR, e a natureza do produto é o critério — a tela
    diz só "me avise sobre este produto", porque o cliente não sabe (nem
    deveria saber) que existem dois eixos de aviso.

    - Item de fornada → ``production_ready``: quem quer pão quer saber quando
      sai do forno.
    - Item de prateleira → ``stock_back``: quem quer um item de prateleira quer
      saber quando ele volta.

    Antes desta derivação a loja mandava o POST sem ``alert_type``, todo mundo
    caía em ``stock_back`` e o eixo ``production_ready`` era código órfão: o
    receptor de fornada nunca achava ninguém, e o público de "Fornada pronta"
    do Marketing prometia gente que a loja não sabia criar.
    """
    from shopman.shop.projections import catalog_context
    from shopman.storefront.models import StockAlertSubscription

    try:
        if catalog_context.comes_out_of_the_oven(sku):
            return StockAlertSubscription.AlertType.PRODUCTION_READY
    except Exception:
        logger.warning("stock_alerts: alert_type derivation failed sku=%s", sku, exc_info=True)
    return StockAlertSubscription.AlertType.STOCK_BACK


def subscribed_skus(*, customer=None, phone: str = "") -> set[str]:
    """SKUs com inscrição ativa para este viewer (cliente logado e/ou telefone).

    Usado pela projeção para persistir o estado do sino "Me avise" entre reloads.
    """
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not customer_ref and not contact:
        return set()

    cond = Q()
    if customer_ref:
        cond |= Q(customer_ref=customer_ref)
    if contact:
        cond |= Q(contact_phone=contact)
    return set(StockAlertSubscription.objects.active().filter(cond).values_list("sku", flat=True))


def has_pending_for(*, sku: str, customer=None, phone: str = "", alert_type: str = "") -> bool:
    """True when this customer/contact still has an active alert for ``sku``."""
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not sku or (not customer_ref and not contact):
        return False

    qs = StockAlertSubscription.objects.active().filter(sku=sku)
    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    cond = Q()
    if customer_ref:
        cond |= Q(customer_ref=customer_ref)
    if contact:
        cond |= Q(contact_phone=contact)
    return qs.filter(cond).exists()


@transaction.atomic
def subscribe(
    sku: str,
    *,
    channel_ref: str = STOREFRONT_CHANNEL_REF,
    customer=None,
    phone: str = "",
    alert_type: str = "",
    disclosure_text: str = STOCK_ALERT_DISCLOSURE,
    disclosure_version: str = STOCK_ALERT_DISCLOSURE_VERSION,
):
    """Register or resume a persistent alert. Returns it or ``None``.

    ``alert_type`` vazio NÃO é ``stock_back``: é "decida você", e a decisão sai
    de :func:`default_alert_type`, pela natureza do produto. Quem passa o tipo
    explicitamente manda — é o caso do endpoint quando o corpo escolhe.

    Dedupes an active alert per (sku, alert_type, target): os dois eixos podem
    coexistir para o mesmo contato sem um sobrescrever o outro. Ninguém cria os
    dois de propósito — quem faz isso é um pedido explícito, ou uma linha
    antiga; ``_notify`` garante que ainda assim sai UMA mensagem por pessoa.

    ``customer`` is a Guestman Customer (or None for anonymous); ``phone`` is
    the anonymous contact.
    """
    from shopman.storefront.models import StockAlertSubscription

    alert_type = alert_type or default_alert_type(sku)
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = normalize_phone(phone or getattr(customer, "phone", "") or "")
    disclosure_text = (disclosure_text or "").strip()
    disclosure_version = (disclosure_version or "").strip()
    if not contact or not disclosure_text or not disclosure_version:
        return None

    now = timezone.now()
    channel_ref = channel_ref or "web"
    _lock_channel_if_configured(channel_ref)
    target_key = _target_key(customer_ref=customer_ref, phone=contact)
    selector = {
        "sku": sku,
        "alert_type": alert_type,
        "channel_ref": channel_ref,
        "target_key": target_key,
        "revoked_at__isnull": True,
    }
    stale = StockAlertSubscription.objects.filter(
        **selector,
        expires_at__lte=now,
    )
    for old in stale.only("pk", "ref"):
        old.revoked_at = now
        old.revoke_reason = "expired"
        old.revocation_evidence_hash = _revocation_hash(old.ref, now, "expired")
        old.save(update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"])

    existing = StockAlertSubscription.objects.filter(
        **selector,
        proof_status="verified",
    ).first()
    if existing:
        if existing.paused_at is not None:
            existing.paused_at = None
            existing.pause_reason = ""
            existing.save(update_fields=["paused_at", "pause_reason"])
        return existing

    # An old row without evidence cannot silently become proof. Close it and create
    # a fresh subscription carrying the text the shopper has just accepted.
    legacy = StockAlertSubscription.objects.filter(**selector).first()
    if legacy:
        legacy.revoked_at = now
        legacy.revoke_reason = "reconfirmed_with_evidence"
        legacy.revocation_evidence_hash = _revocation_hash(legacy.ref, now, legacy.revoke_reason)
        legacy.save(update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"])

    subscription_ref = uuid.uuid4()
    disclosure_hash = hashlib.sha256(disclosure_text.encode()).hexdigest()
    evidence_hash = _subscription_evidence_hash(
        subscription_ref=subscription_ref,
        sku=sku,
        alert_type=alert_type,
        channel_ref=channel_ref,
        target_key=target_key,
        disclosure_hash=disclosure_hash,
        disclosure_version=disclosure_version,
        occurred_at=now,
    )
    try:
        with transaction.atomic():
            return StockAlertSubscription.objects.create(
                ref=subscription_ref,
                sku=sku,
                alert_type=alert_type,
                channel_ref=channel_ref,
                delivery_channel="whatsapp",
                purpose="stock_availability",
                customer_ref=customer_ref,
                contact_phone=contact,
                target_key=target_key,
                disclosure_text=disclosure_text,
                disclosure_version=disclosure_version,
                disclosure_hash=disclosure_hash,
                evidence_hash=evidence_hash,
                proof_status="verified",
                expires_at=now + timedelta(days=30),
            )
    except IntegrityError:
        # The database unique is the race winner. A simultaneous equivalent click
        # receives that same subscription instead of surfacing a transient 500.
        return StockAlertSubscription.objects.active().get(**selector)


@transaction.atomic
def revoke(
    subscription_ref,
    *,
    sku: str = "",
    customer=None,
    phone: str = "",
    reason: str = "customer_request",
) -> bool:
    """Cancel one subscription after checking ownership; safe to repeat."""

    from shopman.storefront.models import StockAlertSubscription

    _lock_channel_if_configured(
        StockAlertSubscription.objects.filter(ref=subscription_ref).values_list("channel_ref", flat=True).first()
        or STOREFRONT_CHANNEL_REF
    )

    subscriptions = StockAlertSubscription.objects.select_for_update().filter(ref=subscription_ref)
    if sku:
        subscriptions = subscriptions.filter(sku=sku)
    sub = subscriptions.first()
    if sub is None:
        return False
    if not _owned_by(sub, customer=customer, phone=phone):
        return False
    if sub.revoked_at is not None:
        return True
    now = timezone.now()
    sub.revoked_at = now
    sub.revoke_reason = (reason or "customer_request")[:100]
    sub.revocation_evidence_hash = _revocation_hash(sub.ref, now, sub.revoke_reason)
    sub.save(update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"])
    return True


@transaction.atomic
def set_paused(
    subscription_ref,
    *,
    paused: bool,
    sku: str = "",
    customer=None,
    phone: str = "",
    reason: str = "customer_request",
) -> bool:
    """Pause/resume one opt-in after the same ownership check used by revoke."""
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    _lock_channel_if_configured(
        StockAlertSubscription.objects.filter(ref=subscription_ref).values_list("channel_ref", flat=True).first()
        or STOREFRONT_CHANNEL_REF
    )

    now = timezone.now()
    qs = StockAlertSubscription.objects.select_for_update().filter(
        ref=subscription_ref,
        revoked_at__isnull=True,
        proof_status="verified",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    if sku:
        qs = qs.filter(sku=sku)
    sub = qs.first()
    if sub is None or not _owned_by(sub, customer=customer, phone=phone):
        return False
    sub.paused_at = timezone.now() if paused else None
    sub.pause_reason = (reason or "customer_request")[:100] if paused else ""
    sub.save(update_fields=["paused_at", "pause_reason"])
    return True


def notify_back_in_stock(sku: str, *, source_ref: str = "", also_bake_waiters: bool = False) -> int:
    """Reconcile one stock cycle and queue the unavailable→available occurrence.

    ``also_bake_waiters`` remains accepted for rollout compatibility but never
    crosses event purposes: an arrival is not a bake.
    """
    del also_bake_waiters
    return _record_occurrences(sku, event_type="stock_back", source_ref=source_ref, close_when_unavailable=True)


def notify_bake_ready(sku: str, *, source_ref: str = "") -> int:
    """Compatibility name for releasing a manager-reviewed bake occurrence."""
    return review_bake_ready(sku, source_ref=source_ref)


def record_bake_pending(sku: str, *, source_ref: str) -> int:
    """Record a finished bake without authorizing communication yet."""
    from shopman.storefront.models import StockAlertSubscription

    channels = set(
        StockAlertSubscription.objects.active().filter(
            sku=sku,
            alert_type="production_ready",
            revoked_at__isnull=True,
        )
        .values_list("channel_ref", flat=True)
        .distinct()
    )
    created = 0
    for channel_ref in sorted(channels):
        if _create_pending_bake_occurrence(
            sku=sku,
            channel_ref=channel_ref,
            source_ref=source_ref,
        ):
            created += 1
    return created


def review_bake_ready(sku: str, *, source_ref: str) -> int:
    """Release one bake only after canonical manager QC and channel checks."""
    from shopman.shop.services import quality as quality_service
    from shopman.storefront.models import StockAlertOccurrence, StockAlertSubscription
    from shopman.storefront.services import sku_state

    channels = set(
        StockAlertSubscription.objects.active().filter(
            sku=sku,
            alert_type="production_ready",
            revoked_at__isnull=True,
        )
        .values_list("channel_ref", flat=True)
        .distinct()
    )
    channels.update(
        StockAlertOccurrence.objects.filter(
            sku=sku,
            event_type="production_ready",
            source_ref=source_ref,
        ).values_list("channel_ref", flat=True)
    )
    queued = 0
    for channel_ref in sorted(channels):
        try:
            reviewed_qty = quality_service.reviewed_saleable_quantity(
                source_ref,
                channel_ref=channel_ref,
            )
            state = sku_state.resolve(sku=sku, channel_ref=channel_ref)
        except Exception:
            logger.warning(
                "stock_alerts: bake review evaluation failed sku=%s source=%s",
                sku,
                source_ref,
                exc_info=True,
            )
            continue
        if reviewed_qty is None:
            _create_pending_bake_occurrence(
                sku=sku,
                channel_ref=channel_ref,
                source_ref=source_ref,
            )
            continue
        if reviewed_qty <= 0:
            _create_blocked_occurrence(
                sku=sku,
                event_type="production_ready",
                channel_ref=channel_ref,
                source_ref=source_ref,
                reason="quality_not_sellable_for_channel",
            )
            continue
        if not state.can_add_to_cart:
            _create_blocked_occurrence(
                sku=sku,
                event_type="production_ready",
                channel_ref=channel_ref,
                source_ref=source_ref,
                reason="unavailable_after_quality_review",
            )
            continue
        queued += _create_eligible_occurrence(
            sku=sku,
            event_type="production_ready",
            channel_ref=channel_ref,
            source_ref=source_ref,
            available_qty=(
                reviewed_qty
                if state.available_qty is None
                else min(reviewed_qty, state.available_qty)
            ),
        )
    return queued


@transaction.atomic
def _create_pending_bake_occurrence(*, sku: str, channel_ref: str, source_ref: str) -> bool:
    from shopman.storefront.models import StockAlertOccurrence

    _lock_channel_if_configured(channel_ref)
    occurrence, created = StockAlertOccurrence.objects.get_or_create(
        semantic_key=_occurrence_key("production_ready", sku, channel_ref, source_ref),
        defaults={
            "sku": sku,
            "event_type": "production_ready",
            "channel_ref": channel_ref,
            "source_ref": source_ref,
            "status_reason": "awaiting_quality_review",
        },
    )
    if not created and occurrence.status == StockAlertOccurrence.Status.PENDING:
        updates = []
        if occurrence.status_reason != "awaiting_quality_review":
            occurrence.status_reason = "awaiting_quality_review"
            updates.append("status_reason")
        if occurrence.closed_at is not None:
            occurrence.closed_at = None
            updates.append("closed_at")
        if updates:
            occurrence.save(update_fields=[*updates, "updated_at"])
    return created


def _record_occurrences(
    sku: str,
    *,
    event_type: str,
    source_ref: str,
    close_when_unavailable: bool = False,
) -> int:
    """Evaluate every subscribed channel and atomically queue new deliveries."""
    from shopman.storefront.models import StockAlertOccurrence, StockAlertSubscription
    from shopman.storefront.services import sku_state

    channels = set(
        StockAlertSubscription.objects.filter(sku=sku, alert_type=event_type, revoked_at__isnull=True)
        .values_list("channel_ref", flat=True)
        .distinct()
    )
    if close_when_unavailable:
        channels.update(
            StockAlertOccurrence.objects.filter(
                sku=sku,
                event_type=event_type,
                closed_at__isnull=True,
            ).values_list("channel_ref", flat=True)
        )
    if not channels:
        return 0
    queued = 0
    for channel_ref in sorted(channels):
        try:
            state = sku_state.resolve(sku=sku, channel_ref=channel_ref)
        except Exception:
            logger.warning("stock_alerts: occurrence evaluation failed sku=%s", sku, exc_info=True)
            continue
        if not state.can_add_to_cart:
            if close_when_unavailable:
                StockAlertOccurrence.objects.filter(
                    sku=sku,
                    event_type=event_type,
                    channel_ref=channel_ref,
                    closed_at__isnull=True,
                ).update(
                    status=StockAlertOccurrence.Status.CLOSED,
                    status_reason="unavailable_cycle_closed",
                    closed_at=timezone.now(),
                )
            elif source_ref:
                _create_blocked_occurrence(
                    sku=sku,
                    event_type=event_type,
                    channel_ref=channel_ref,
                    source_ref=source_ref,
                    reason="not_sellable_after_qc",
                )
            continue
        queued += _create_eligible_occurrence(
            sku=sku,
            event_type=event_type,
            channel_ref=channel_ref,
            source_ref=source_ref,
            available_qty=state.available_qty,
        )
    return queued


@transaction.atomic
def _create_eligible_occurrence(*, sku: str, event_type: str, channel_ref: str, source_ref: str, available_qty) -> int:
    from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence, StockAlertSubscription

    _lock_channel_if_configured(channel_ref)
    if event_type == "stock_back":
        existing = (
            StockAlertOccurrence.objects.select_for_update()
            .filter(sku=sku, event_type=event_type, channel_ref=channel_ref, closed_at__isnull=True)
            .first()
        )
        if existing:
            return 0
        semantic_key = _occurrence_key("stock_back", sku, channel_ref, source_ref)
    else:
        semantic_key = _occurrence_key("production_ready", sku, channel_ref, source_ref)
    try:
        with transaction.atomic():
            occurrence, created = StockAlertOccurrence.objects.get_or_create(
                semantic_key=semantic_key,
                defaults={
                    "sku": sku,
                    "event_type": event_type,
                    "channel_ref": channel_ref,
                    "source_ref": source_ref,
                    "available_qty": available_qty,
                },
            )
    except IntegrityError:
        # Two distinct positive Move rows can observe the same newly-available
        # cycle. The partial unique constraint picks its one occurrence.
        if (
            event_type == "stock_back"
            and StockAlertOccurrence.objects.filter(
                sku=sku, event_type=event_type, channel_ref=channel_ref, closed_at__isnull=True
            ).exists()
        ):
            return 0
        raise
    if not created:
        occurrence = StockAlertOccurrence.objects.select_for_update().get(pk=occurrence.pk)
        if event_type != "production_ready" or occurrence.deliveries.exists():
            return 0
        if occurrence.status not in {
            StockAlertOccurrence.Status.PENDING,
            StockAlertOccurrence.Status.BLOCKED,
        }:
            return 0
    occurrence.status = StockAlertOccurrence.Status.ELIGIBLE
    occurrence.status_reason = (
        "quality_reviewed_sellable" if event_type == "production_ready" else "sellable_after_event"
    )
    occurrence.available_qty = available_qty
    occurrence.closed_at = timezone.now() if event_type == "production_ready" else None
    occurrence.save(update_fields=["status", "status_reason", "available_qty", "closed_at", "updated_at"])
    subscriptions = StockAlertSubscription.objects.active().filter(
        sku=sku, alert_type=event_type, channel_ref=channel_ref
    )
    queued = 0
    for sub in subscriptions.iterator():
        delivery, delivery_created = StockAlertDelivery.objects.get_or_create(
            subscription=sub,
            occurrence=occurrence,
            purpose=sub.purpose,
            delivery_channel=sub.delivery_channel,
        )
        if delivery_created:
            _queue_delivery(delivery)
            queued += 1
    return queued


@transaction.atomic
def _create_blocked_occurrence(*, sku, event_type, channel_ref, source_ref, reason) -> None:
    from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence

    _lock_channel_if_configured(channel_ref)
    semantic_key = _occurrence_key(event_type, sku, channel_ref, source_ref)
    occurrence, _created = StockAlertOccurrence.objects.get_or_create(
        semantic_key=semantic_key,
        defaults={
            "sku": sku,
            "event_type": event_type,
            "channel_ref": channel_ref,
            "source_ref": source_ref,
        },
    )
    occurrence = StockAlertOccurrence.objects.select_for_update().get(pk=occurrence.pk)
    accepted = occurrence.deliveries.filter(status=StockAlertDelivery.Status.ACCEPTED).count()
    occurrence.status = StockAlertOccurrence.Status.BLOCKED
    occurrence.status_reason = reason
    occurrence.available_qty = None
    occurrence.closed_at = timezone.now()
    occurrence.save(update_fields=["status", "status_reason", "available_qty", "closed_at", "updated_at"])
    occurrence.deliveries.filter(
        status__in=(
            StockAlertDelivery.Status.QUEUED,
            StockAlertDelivery.Status.CLAIMED,
            StockAlertDelivery.Status.RETRYABLE,
        )
    ).update(
        status=StockAlertDelivery.Status.SUPPRESSED,
        last_error_code=reason[:100],
        updated_at=timezone.now(),
    )
    if accepted:
        transaction.on_commit(
            lambda: _alert_quality_changed_after_delivery(
                source_ref=source_ref,
                accepted=accepted,
            )
        )


def _alert_quality_changed_after_delivery(*, source_ref: str, accepted: int) -> None:
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="production_quality_communication",
        severity="warning",
        message=(
            f"O QC de {source_ref} deixou a fornada inelegível depois de "
            f"{accepted} aviso(s) aceito(s). Confira a fornada e o histórico de comunicação."
        ),
        order_ref=source_ref,
        dedupe_key=f"stock-alert-quality:{source_ref}",
    )


def _queue_delivery(delivery) -> None:
    from shopman.shop.directives import (
        STOCK_ALERT_DELIVER,
        STOCK_ALERT_DELIVERY_RECEIPT_SCOPE,
        create_persistently_deduped,
    )

    key = f"stock-alert-delivery:{delivery.ref}"
    directive = create_persistently_deduped(
        STOCK_ALERT_DELIVER,
        payload={"delivery_id": delivery.pk},
        dedupe_key=key,
        receipt_scope=STOCK_ALERT_DELIVERY_RECEIPT_SCOPE,
    )
    if directive is not None:
        delivery.directive_id = directive.pk
        delivery.save(update_fields=["directive_id", "updated_at"])


def _globally_opted_out(sub) -> bool:
    if not sub.customer_ref:
        return False
    from shopman.shop.services.communication_consent import customer_is_opted_out

    return customer_is_opted_out(sub.customer_ref, sub.delivery_channel)


def _owned_by(sub, *, customer=None, phone: str = "") -> bool:
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = normalize_phone(phone or getattr(customer, "phone", "") or "")
    return bool((customer_ref and sub.customer_ref == customer_ref) or (contact and sub.contact_phone == contact))


# ── private ──────────────────────────────────────────────────────────


def product_name(sku: str) -> str:
    # Read through the shop projection (surface modules don't import kernels).
    from shopman.shop.projections import catalog_context

    product = catalog_context.get_product(sku)
    return product.name if product is not None else sku


# Compatibility for callers deployed before the public projection helper existed.
_product_name = product_name


def _image_url(sku: str) -> str:
    """Foto do produto pelo orquestrador — superfície não fala com o kernel."""
    try:
        from shopman.shop.services import campaign as campaign_service

        return campaign_service.product_image_url(sku)
    except Exception:
        logger.debug("stock_alerts: foto não resolveu sku=%s", sku, exc_info=True)
        return ""


def _first_name(sub) -> str:
    """Primeiro nome de quem assinou, ou vazio.

    Vazio é resultado legítimo: assinante anônimo tem só telefone. O template trata a
    ausência (a saudação some), então nunca sai "Oi ," na cara do cliente.
    """
    ref = (getattr(sub, "customer_ref", "") or "").strip()
    if not ref:
        return ""
    # Pelo orquestrador, nunca pelo guestman direto: superfície é adaptador de HTTP e
    # read-model, e a fronteira tem teste (`test_import_boundaries`).
    try:
        from shopman.shop.services import customer as customer_service

        return customer_service.first_name_for(ref)
    except Exception:
        logger.debug("stock_alerts: first name lookup failed for %s", ref, exc_info=True)
        return ""


def _deliver(
    sub,
    *,
    product_name: str,
    event: str = "stock_arrived",
    available_qty: int | None = None,
):
    """Send through the configured adapter and return its acceptance result."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.notifications import notify
    from shopman.shop.services import storefront_links
    from shopman.shop.services.availability_copy import availability_phrase

    # subscribe() stores contact_phone = phone OR the customer's phone, so a
    # bare customer_ref without phone has no reachable recipient.
    recipient = (sub.contact_phone or "").strip()
    if not recipient:
        logger.debug("stock_alerts: no recipient for sub=%s", sub.pk)
        from shopman.shop.protocols import NotificationResult

        return NotificationResult(success=False, error="missing_recipient")

    try:
        backend = (
            ChannelConfig.for_channel(sub.channel_ref or STOREFRONT_CHANNEL_REF).notifications.backend
        ) or "manychat"
    except Exception:
        logger.debug("stock_alerts: backend resolve failed, default manychat", exc_info=True)
        backend = "manychat"

    try:
        return notify(
            event=event,
            recipient=recipient,
            context={
                "sku": sub.sku,
                # Nome que a mensagem usa: o sufixo que o template gruda no fim do link
                # do botão. Ver o gêmeo em `handlers/_stock_receivers.py`.
                "product_sku": sub.sku,
                # Foto do produto. Prefixo `product_` por namespacing: o campo vive no
                # perfil do assinante no ManyChat.
                "product_image_url": _image_url(sub.sku),
                "product_name": product_name,
                "customer_name": _first_name(sub),
                "product_url": storefront_links.product_url(sub.sku),
                # Placeholders do template compartilhado de stock_arrived: aqui
                # não há reserva nem prazo — cliente sem hold ("Me avise").
                "reserve_note": "",
                "deadline_note": "",
                # Quantidade REAL, já resolvida na checagem de disponibilidade acima.
                # Vazio quando o canal não sabe contar (`available_qty=None`): a
                # mensagem então não fala em número, em vez de inventar um.
                "available_qty": _quantity_text(available_qty),
                # Frase pronta para template aprovado do WhatsApp. O ManyChat não
                # deve montar gramática com pedaços soltos: campo vazio ou valor
                # antigo no perfil do assinante vira FOMO falso.
                "availability_phrase": availability_phrase(available_qty),
                "cta": "Garanta o seu:",
                "action_url": storefront_links.product_url(sub.sku),
            },
            backend=backend,
        )
    except Exception:
        logger.warning("stock_alerts: delivery failed sub=%s sku=%s", sub.pk, sub.sku, exc_info=True)
        from shopman.shop.protocols import NotificationResult

        return NotificationResult(success=False, error="notification_adapter_error", outcome_unknown=True)


def _target_key(*, customer_ref: str, phone: str) -> str:
    identity = f"customer:{customer_ref}" if customer_ref else f"phone:{phone}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        identity.encode(),
        hashlib.sha256,
    ).hexdigest()


def _quantity_text(value) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _occurrence_key(event_type: str, sku: str, channel_ref: str, source_ref: str) -> str:
    raw = f"{event_type}:{sku}:{channel_ref}:{source_ref or uuid.uuid4()}"
    if len(raw) <= 160:
        return raw
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{event_type}:{digest}"


def _subscription_evidence_hash(
    *,
    subscription_ref,
    sku: str,
    alert_type: str,
    channel_ref: str,
    target_key: str,
    disclosure_hash: str,
    disclosure_version: str,
    occurred_at,
) -> str:
    evidence = json.dumps(
        {
            "ref": str(subscription_ref),
            "sku": sku,
            "alert_type": alert_type,
            "channel_ref": channel_ref,
            "delivery_channel": "whatsapp",
            "purpose": "stock_availability",
            "target_key": target_key,
            "disclosure_hash": disclosure_hash,
            "disclosure_version": disclosure_version,
            "occurred_at": occurred_at.isoformat(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hmac.new(settings.SECRET_KEY.encode(), evidence.encode(), hashlib.sha256).hexdigest()


def _lock_channel_if_configured(channel_ref: str) -> bool:
    """Use the canonical Channel row as mutex when it exists.

    A missing bootstrap row must not lose the customer's opt-in. Delivery stays
    fail-closed because its handler requires the configured Channel before IO.
    """
    from shopman.shop.models import Channel

    return Channel.objects.select_for_update().filter(ref=channel_ref).exists()


def _revocation_hash(subscription_ref, occurred_at, reason: str) -> str:
    value = f"{subscription_ref}:{occurred_at.isoformat()}:{reason}"
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
