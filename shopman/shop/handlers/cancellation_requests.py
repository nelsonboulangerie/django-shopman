"""Close cancellation-request alerts when the order reaches the outcome."""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def _resolve(order_ref: str, actor: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.cancellation_requests import ALERT_TYPE

    try:
        alert_adapter.resolve(ALERT_TYPE, order_ref=order_ref, actor=actor)
    except Exception:
        logger.exception("cancellation_request.alert_resolution_failed order=%s", order_ref)


def on_order_changed(sender, order, event_type, actor, **kwargs) -> None:
    if event_type != "status_changed" or order.status not in {"cancelled", "returned"}:
        return
    resolution_actor = f"order-status:{actor or 'system'}"
    transaction.on_commit(lambda: _resolve(order.ref, resolution_actor))


def connect() -> None:
    from shopman.orderman.signals import order_changed

    order_changed.connect(
        on_order_changed,
        dispatch_uid="shopman.shop.cancellation_requests.on_order_changed",
        weak=False,
    )
