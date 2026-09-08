"""Stock-back alerts ("Me avise quando disponível") — subscribe + notify.

Subscribe is open to anonymous shoppers (phone only) and logged-in customers.
The notify path is triggered by a stock-arrival receiver and is idempotent: it
only fires for *pending* subscriptions of a SKU that is *now* available, and
stamps ``notified_at`` so each subscription notifies exactly once.
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

logger = logging.getLogger(__name__)

STOCK_ALERT_DISCLOSURE_VERSION = "stock-availability-pt-BR-v1"
STOCK_ALERT_DISCLOSURE = (
    "Quero receber um aviso por WhatsApp sobre este produto. A assinatura termina "
    "no primeiro aviso, quando eu cancelar ou em 30 dias."
)


def has_pending(sku: str, *, alert_type: str = "") -> bool:
    """Cheap guard for the arrival/bake receivers (indexed exists())."""
    from shopman.storefront.models import StockAlertSubscription

    qs = StockAlertSubscription.objects.active().filter(sku=sku)
    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    return qs.exists()


def subscribed_skus(*, customer=None, phone: str = "") -> set[str]:
    """SKUs com inscrição PENDENTE para este viewer (cliente logado e/ou telefone).

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
    return set(
        StockAlertSubscription.objects.active()
        .filter(cond)
        .values_list("sku", flat=True)
    )


def has_pending_for(*, sku: str, customer=None, phone: str = "", alert_type: str = "") -> bool:
    """True when this customer/contact still has a pending alert for ``sku``."""
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


def subscribe(
    sku: str,
    *,
    channel_ref: str = "web",
    customer=None,
    phone: str = "",
    alert_type: str = "",
    disclosure_text: str = STOCK_ALERT_DISCLOSURE,
    disclosure_version: str = STOCK_ALERT_DISCLOSURE_VERSION,
):
    """Register a pending alert. Returns the subscription or None.

    Dedupes a pending alert per (sku, alert_type, target) — quem quer saber da
    reposição e da próxima fornada assina os dois, sem um sobrescrever o outro.
    ``customer`` is a Guestman Customer (or None for anonymous); ``phone`` is
    the anonymous contact.
    """
    from shopman.storefront.models import StockAlertSubscription

    alert_type = alert_type or StockAlertSubscription.AlertType.STOCK_BACK
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = normalize_phone(phone or getattr(customer, "phone", "") or "")
    disclosure_text = (disclosure_text or "").strip()
    disclosure_version = (disclosure_version or "").strip()
    if not contact or not disclosure_text or not disclosure_version:
        return None

    now = timezone.now()
    channel_ref = channel_ref or "web"
    target_key = _target_key(customer_ref=customer_ref, phone=contact)
    selector = {
        "sku": sku,
        "alert_type": alert_type,
        "channel_ref": channel_ref,
        "target_key": target_key,
        "notified_at__isnull": True,
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
        old.save(
            update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"]
        )

    existing = StockAlertSubscription.objects.active(now=now).filter(**selector).first()
    if existing:
        return existing

    # An old row without evidence cannot silently become proof. Close it and create
    # a fresh subscription carrying the text the shopper has just accepted.
    legacy = StockAlertSubscription.objects.filter(**selector).first()
    if legacy:
        legacy.revoked_at = now
        legacy.revoke_reason = "reconfirmed_with_evidence"
        legacy.revocation_evidence_hash = _revocation_hash(
            legacy.ref, now, legacy.revoke_reason
        )
        legacy.save(
            update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"]
        )

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

    subscriptions = StockAlertSubscription.objects.select_for_update().filter(
        ref=subscription_ref
    )
    if sku:
        subscriptions = subscriptions.filter(sku=sku)
    sub = subscriptions.first()
    if sub is None:
        return False
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = normalize_phone(phone or getattr(customer, "phone", "") or "")
    owned = (customer_ref and sub.customer_ref == customer_ref) or (
        contact and sub.contact_phone == contact
    )
    if not owned:
        return False
    if sub.revoked_at is not None:
        return True
    if sub.notified_at is not None:
        return False

    now = timezone.now()
    sub.revoked_at = now
    sub.revoke_reason = (reason or "customer_request")[:100]
    sub.revocation_evidence_hash = _revocation_hash(
        sub.ref, now, sub.revoke_reason
    )
    sub.save(update_fields=["revoked_at", "revoke_reason", "revocation_evidence_hash"])
    return True


def notify_back_in_stock(sku: str) -> int:
    """Notify pending ``stock_back`` subscribers once ``sku`` is available again.

    Idempotent: marks ``notified_at`` only on a successful send, so a failed
    delivery is retried on the next stock arrival. Returns count notified.
    """
    from shopman.storefront.models import StockAlertSubscription

    return _notify(sku, alert_type=StockAlertSubscription.AlertType.STOCK_BACK)


def notify_bake_ready(sku: str) -> int:
    """Notify pending ``production_ready`` subscribers quando sai uma fornada.

    Mesmo gate de disponibilidade do ``stock_back``: fornada concluída que ainda
    não virou estoque vendável no canal não vira aviso, porque o aviso promete
    "pode pedir agora". Frustrar quem pediu para ser avisado é pior que calar.
    """
    from shopman.storefront.models import StockAlertSubscription

    return _notify(sku, alert_type=StockAlertSubscription.AlertType.PRODUCTION_READY)


#: Cada gatilho tem sua copy: "chegou" e "saiu do forno" prometem coisas diferentes.
_EVENT_BY_ALERT_TYPE = {
    "stock_back": "stock_arrived",
    "production_ready": "production_ready",
}


def _notify(sku: str, *, alert_type: str) -> int:
    from shopman.storefront.models import StockAlertSubscription
    from shopman.storefront.services import sku_state

    pending = list(StockAlertSubscription.objects.active().filter(sku=sku, alert_type=alert_type))
    if not pending:
        return 0

    product_name = _product_name(sku)
    event = _EVENT_BY_ALERT_TYPE.get(alert_type, "stock_arrived")
    notified = 0
    for sub in pending:
        try:
            state = sku_state.resolve(sku=sku, channel_ref=sub.channel_ref or "web")
        except Exception:
            logger.debug("stock_alerts: availability check failed sku=%s", sku, exc_info=True)
            continue
        if not state.can_add_to_cart:
            continue  # still unavailable for this channel — keep pending
        if _deliver_if_still_active(
            sub.pk,
            product_name=product_name,
            event=event,
            available_qty=state.available_qty,
        ):
            notified += 1
    if notified:
        logger.info(
            "stock_alerts: notified %s subscriber(s) for sku=%s type=%s",
            notified, sku, alert_type,
        )
    return notified


@transaction.atomic
def _deliver_if_still_active(
    subscription_pk: int,
    *,
    product_name: str,
    event: str,
    available_qty: int | None,
) -> bool:
    """Lock, recheck revocation/expiry/global opt-out, then deliver once.

    This intentionally holds the row lock across the legacy adapter call. WP-03
    replaces that temporary boundary with a persisted DeliveryAttempt, without
    weakening this revoke-before-send guarantee in the meantime.
    """

    from shopman.storefront.models import StockAlertSubscription

    sub = (
        StockAlertSubscription.objects.select_for_update()
        .active()
        .filter(pk=subscription_pk)
        .first()
    )
    if sub is None or _globally_opted_out(sub):
        return False
    if not _deliver(
        sub,
        product_name=product_name,
        event=event,
        available_qty=available_qty,
    ):
        return False
    sub.notified_at = timezone.now()
    sub.save(update_fields=["notified_at"])
    return True


def _globally_opted_out(sub) -> bool:
    if not sub.customer_ref:
        return False
    try:
        from shopman.guestman import ConsentService

        statuses = ConsentService.get_customer_statuses(
            sub.delivery_channel,
            {sub.customer_ref},
        )
    except Exception:
        logger.warning(
            "stock_alerts: consent recheck failed sub=%s",
            sub.pk,
            exc_info=True,
        )
        return True
    return statuses.get(sub.customer_ref) == "opted_out"


# ── private ──────────────────────────────────────────────────────────


def _product_name(sku: str) -> str:
    # Read through the shop projection (surface modules don't import kernels).
    from shopman.shop.projections import catalog_context

    product = catalog_context.get_product(sku)
    return product.name if product is not None else sku


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
    sub, *, product_name: str, event: str = "stock_arrived", available_qty: int | None = None,
) -> bool:
    """Send the subscription's notification via the channel's backend. True on success."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.notifications import notify
    from shopman.shop.services import storefront_links
    from shopman.shop.services.availability_copy import availability_phrase

    # subscribe() stores contact_phone = phone OR the customer's phone, so a
    # bare customer_ref without phone has no reachable recipient.
    recipient = (sub.contact_phone or "").strip()
    if not recipient:
        logger.debug("stock_alerts: no recipient for sub=%s", sub.pk)
        return False

    try:
        backend = (ChannelConfig.for_channel(sub.channel_ref or "web").notifications.backend) or "manychat"
    except Exception:
        logger.debug("stock_alerts: backend resolve failed, default manychat", exc_info=True)
        backend = "manychat"

    try:
        result = notify(
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
                "available_qty": "" if available_qty is None else str(available_qty),
                # Frase pronta para template aprovado do WhatsApp. O ManyChat não
                # deve montar gramática com pedaços soltos: campo vazio ou valor
                # antigo no perfil do assinante vira FOMO falso.
                "availability_phrase": availability_phrase(available_qty),
                "cta": "Garanta o seu:",
                "action_url": storefront_links.product_url(sub.sku),
            },
            backend=backend,
        )
        return bool(getattr(result, "success", False))
    except Exception:
        logger.warning("stock_alerts: delivery failed sub=%s sku=%s", sub.pk, sub.sku, exc_info=True)
        return False


def _target_key(*, customer_ref: str, phone: str) -> str:
    identity = f"customer:{customer_ref}" if customer_ref else f"phone:{phone}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        identity.encode(),
        hashlib.sha256,
    ).hexdigest()


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
    return hmac.new(
        settings.SECRET_KEY.encode(), evidence.encode(), hashlib.sha256
    ).hexdigest()


def _revocation_hash(subscription_ref, occurred_at, reason: str) -> str:
    value = f"{subscription_ref}:{occurred_at.isoformat()}:{reason}"
    return hmac.new(
        settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256
    ).hexdigest()
