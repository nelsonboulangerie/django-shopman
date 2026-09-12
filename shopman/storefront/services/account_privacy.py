"""Dados pessoais que pertencem à superfície pública da loja."""

from __future__ import annotations

from django.db.models import Q


def export_surface_data(*, customer_ref: str, phone: str) -> dict:
    """Completa a portabilidade sem inverter a dependência storefront → shop."""
    from shopman.storefront.models import CustomerFavorite, StockAlertSubscription

    subscription_query = Q()
    if customer_ref:
        subscription_query |= Q(customer_ref=customer_ref)
    if phone:
        subscription_query |= Q(contact_phone=phone)

    subscriptions = (
        StockAlertSubscription.objects.filter(subscription_query)
        if subscription_query.children
        else StockAlertSubscription.objects.none()
    )
    return {
        "favorites": [
            {"sku": row.sku, "created_at": row.created_at}
            for row in CustomerFavorite.objects.filter(customer_ref=customer_ref)
        ],
        "availability_alerts": [
            {
                "sku": row.sku,
                "type": row.alert_type,
                "channel": row.delivery_channel,
                "purpose": row.purpose,
                "subscribed_at": row.subscribed_at,
                "notified_at": row.notified_at,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
            }
            for row in subscriptions.order_by("-subscribed_at")
        ],
    }
