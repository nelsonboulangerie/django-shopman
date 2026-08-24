"""
Loyalty points service.

Core: LoyaltyService (enroll, earn_points, redeem_points)

ASYNC — creates Directive for later processing.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

TOPIC = "loyalty.earn"
REDEEM_TOPIC = "loyalty.redeem"
REVOKE_TOPIC = "loyalty.revoke"
RESTORE_TOPIC = "loyalty.restore"


def redeem(order) -> None:
    """
    Schedule loyalty points redemption for the order, if applicable.

    Reads order.data["loyalty"]["applied_discount_q"] — o desconto efetivamente
    aplicado pelo LoyaltyRedeemModifier (clampado ao subtotal), nunca o saldo
    pedido. If >0, creates a Directive with topic="loyalty.redeem".

    ASYNC — dispatched on on_commit so points are deducted immediately after order creation.
    """
    applied_q = int((order.data or {}).get("loyalty", {}).get("applied_discount_q") or 0)
    if applied_q <= 0:
        return

    Directive.objects.create(
        topic=REDEEM_TOPIC,
        payload={
            "order_ref": order.ref,
            "points": applied_q,
        },
    )

    logger.info("loyalty.redeem: queued %d points for order %s", applied_q, order.ref)


def earn(order) -> None:
    """
    Schedule loyalty points earning for the order.

    Creates a Directive with topic="loyalty.earn". The handler that
    processes the Directive finds the customer, calculates points
    (1 point per R$1), and calls LoyaltyService.earn_points().

    ASYNC — non-critical, can fail without impacting the order.
    """
    if not order.total_q or order.total_q <= 0:
        return

    Directive.objects.create(
        topic=TOPIC,
        payload={
            "order_ref": order.ref,
        },
    )

    logger.info("loyalty.earn: queued for order %s", order.ref)


def revoke(order, reason: str) -> None:
    """
    Schedule loyalty points revocation for a cancelled/returned order.

    Creates a Directive with topic="loyalty.revoke". The handler reverses
    exactly what the earn transaction credited — if the earn never ran,
    the revoke is a no-op.

    ASYNC — non-critical, can fail without impacting the cancellation.
    """
    if not order.total_q or order.total_q <= 0:
        return

    from shopman.shop import directives

    created = directives.create_deduped(
        REVOKE_TOPIC,
        payload={
            "order_ref": order.ref,
            "reason": reason,
        },
        dedupe_key=f"loyalty.revoke:{order.ref}",
    )

    if created is not None:
        logger.info("loyalty.revoke: queued for order %s (%s)", order.ref, reason)


def restore(order, reason: str) -> None:
    """
    Schedule the return of redeemed loyalty points for a cancelled/returned order.

    Creates a Directive with topic="loyalty.restore". The handler credits back
    exactly what the redeem transaction debited — if the redeem never ran,
    the restore is a no-op.

    ASYNC — non-critical, can fail without impacting the cancellation.
    """
    applied_q = int((order.data or {}).get("loyalty", {}).get("applied_discount_q") or 0)
    if applied_q <= 0:
        return

    from shopman.shop import directives

    created = directives.create_deduped(
        RESTORE_TOPIC,
        payload={
            "order_ref": order.ref,
            "reason": reason,
        },
        dedupe_key=f"loyalty.restore:{order.ref}",
    )

    if created is not None:
        logger.info("loyalty.restore: queued for order %s (%s)", order.ref, reason)
