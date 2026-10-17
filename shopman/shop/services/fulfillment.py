"""
Fulfillment service.

Core: orderman.models.Fulfillment
"""

from __future__ import annotations

import logging

from django.db import transaction
from shopman.orderman.models import Fulfillment, Order

logger = logging.getLogger(__name__)

# Tracking URL patterns for known carriers
CARRIER_TRACKING_URLS = {
    "correios": "https://rastreamento.correios.com.br/app/index.php?objetos={code}",
    "sedex": "https://rastreamento.correios.com.br/app/index.php?objetos={code}",
    "jadlog": "https://www.jadlog.com.br/tracking?code={code}",
    "loggi": "https://www.loggi.com/rastreio/{code}",
}


def create(order) -> Fulfillment | None:
    """
    Create a fulfillment record for the order.

    Idempotent — checks order.data["fulfillment_created"] flag.

    SYNC — creates the record immediately.
    """
    if (order.data or {}).get("fulfillment_created"):
        return None

    # O snapshot do caller pode anteceder outro worker. Trava o owner canônico
    # e grava o registro e seu marcador no mesmo commit, sem rede sob o lock.
    with transaction.atomic():
        current = Order.objects.select_for_update().get(pk=order.pk)
        if (current.data or {}).get("fulfillment_created"):
            order.data = current.data
            return None
        existing = Fulfillment.objects.filter(order=current).order_by("pk").first()
        record = existing or Fulfillment.objects.create(order=current)
        current.data = {**(current.data or {}), "fulfillment_created": True}
        current.save(update_fields=["data", "updated_at"])
        order.data = current.data

    logger.info("fulfillment.create: recorded for order %s", order.ref)
    return record


def update(fulfillment, status, tracking_code=None, carrier=None) -> None:
    """
    Update fulfillment status with optional tracking info.

    Auto-enriches tracking URL for known carriers (Correios, JadLog, etc.).

    SYNC — updates the record immediately.
    """
    if tracking_code:
        fulfillment.tracking_code = tracking_code
    if carrier:
        fulfillment.carrier = carrier

    # Auto-enrich tracking URL
    effective_carrier = carrier or fulfillment.carrier
    effective_code = tracking_code or fulfillment.tracking_code
    if effective_carrier and effective_code and not fulfillment.tracking_url:
        fulfillment.tracking_url = _enrich_tracking_url(effective_carrier, effective_code)

    fulfillment.status = status
    fulfillment.save()

    logger.info(
        "fulfillment.update: %s → %s for order %s",
        fulfillment.pk, status, fulfillment.order.ref,
    )


def _enrich_tracking_url(carrier: str, tracking_code: str) -> str:
    """Generate tracking URL for known carriers."""
    pattern = CARRIER_TRACKING_URLS.get(carrier.lower())
    if pattern and tracking_code:
        return pattern.format(code=tracking_code)
    return ""
