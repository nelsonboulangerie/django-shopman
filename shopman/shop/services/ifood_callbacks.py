"""iFood order status callbacks (WP-4) — push our lifecycle back to iFood.

The merchant must tell iFood how an order progresses. Verified live (routes
exist; a fake id returns ``404 OrderNotFound``):

- ``POST /order/v1.0/orders/{id}/confirm``          → accept the order.
- ``POST /order/v1.0/orders/{id}/readyToPickup``    → order is ready.
- ``POST /order/v1.0/orders/{id}/dispatch``         → order left for delivery.
- ``POST /order/v1.0/orders/{id}/requestCancellation`` → ask iFood to cancel.

Internal ``Order.Status`` → iFood action:

    CONFIRMED  → confirm
    READY      → readyToPickup (pickup or iFood delivery)
    DISPATCHED → dispatch (merchant delivery only)
    CANCELLED  → requestCancellation

``requestCancellation`` requires a valid ``cancellationCode`` and ``reason``.
A successful request is pending until the CAN event confirms cancellation.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)


class IFoodCallbackError(Exception):
    """Safe provider failure, classified for durable retries."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


# Internal status → iFood order-action path segment.
STATUS_ACTION = {
    "accepted": "confirm",
    "ready": "readyToPickup",
    "dispatched": "dispatch",
    "cancelled": "requestCancellation",
}

#: Motivo escolhido no Gestor (diálogo de cancelamento) → cancellationCode do
#: iFood. A lista oficial é descoberta em homologação via
#: ``GET /order/v1.0/orders/{id}/cancellationReasons``; o mapeamento real é
#: config-driven (``SHOPMAN_IFOOD["cancellation_reason_codes"]``). Este
#: default fica VAZIO de propósito: sem código validado, cai no
#: ``cancellation_default_code`` — código errado é pior que falhar alto.
DEFAULT_REASON_CODES: dict[str, str] = {}


def resolve_cancellation_code(reason: str, default: str = "") -> str:
    """Cancellation code for a Gestor reason, falling back to default/config.

    Os códigos oficiais só devem entrar depois da homologação; até lá o
    fallback garante que o pedido de cancelamento não morre por falta de code
    (o default configurado em ``SHOPMAN_IFOOD["cancellation_default_code"]``).
    """
    codes = dict(DEFAULT_REASON_CODES)
    codes.update(_cfg().get("cancellation_reason_codes") or {})
    return (
        codes.get(str(reason or "").strip())
        or default
        or str(_cfg().get("cancellation_default_code") or "")
    )


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def action_for_status(
    status: str,
    *,
    fulfillment_type: str | None = None,
    delivered_by: str = "",
) -> str | None:
    """Map status; supplying fulfillment applies the official Order workflow.

    The context-free form remains a pure capability lookup for existing callers.
    Actual sends always provide context, and missing delivery ownership is never
    interpreted as MERCHANT. Canonical pickup includes TAKEOUT and DINE_IN.
    https://developer.ifood.com.br/pt-BR/docs/guides/modules/order/workflow/
    """
    status = str(status or "").lower()
    action = STATUS_ACTION.get(status)
    if fulfillment_type is None or status not in {"ready", "dispatched"}:
        return action
    fulfillment = str(fulfillment_type or "").lower()
    owner = str(delivered_by or "").upper()
    if status == "ready":
        return action if fulfillment in {"pickup", "takeout", "dine_in"} or (
            fulfillment == "delivery" and owner == "IFOOD"
        ) else None
    return action if fulfillment == "delivery" and owner == "MERCHANT" else None


def workflow_context(order) -> dict[str, str]:
    """Read the same canonical fulfillment (including legacy key) as operations."""
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return {
        "fulfillment_type": get_fulfillment_type(order),
        "delivered_by": ((order.data or {}).get("ifood") or {}).get("delivered_by", ""),
    }


def remote_status_observed(order, status: str) -> bool:
    """Do not echo a confirmed remote transition, even from an older Directive."""
    remote = (order.data or {}).get("ifood") or {}
    if status == "accepted":
        return bool(remote.get("remote_confirmed") or remote.get("remote_dispatched"))
    if status in {"ready", "dispatched"}:
        return bool(remote.get("remote_dispatched"))
    return False


def send_action(order_id: str, action: str, *, body: dict | None = None) -> None:
    """POST a status action to iFood. Raises :class:`IFoodCallbackError` on failure."""
    headers = ifood_auth.authorized_headers({"Content-Type": "application/json"})
    if not headers:
        raise IFoodCallbackError("iFood OAuth is not configured (client_id/client_secret)")

    url = f"{_base_url()}/order/v1.0/orders/{order_id}/{action}"
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodCallbackError(f"iFood {action} request failed") from exc

    # iFood returns 202 Accepted for status actions.
    if resp.status_code not in (200, 202):
        retryable = resp.status_code in (408, 429) or resp.status_code >= 500
        if resp.status_code == 403:
            # The edge can return HTML "Access Denied" intermittently. That is
            # not a marketplace decision: preserve the pending request and retry.
            # Only a structured API response supports treating 403 as a definite
            # authorization/configuration failure. Never retain its raw body.
            try:
                structured_error = isinstance(resp.json(), (dict, list))
            except ValueError:
                structured_error = False
            content_type = str(resp.headers.get("Content-Type", "")).lower()
            retryable = "html" in content_type or not structured_error
        raise IFoodCallbackError(
            f"iFood {action} HTTP {resp.status_code}",
            retryable=retryable,
        )
    logger.info("ifood_callbacks: %s ok for order %s", action, order_id)


def confirm(order_id: str) -> None:
    send_action(order_id, "confirm")


def ready_to_pickup(order_id: str) -> None:
    send_action(order_id, "readyToPickup")


def dispatch(order_id: str) -> None:
    send_action(order_id, "dispatch")


def fetch_cancellation_reasons(order_id: str) -> list[dict]:
    """Fetch the cancellation codes iFood accepts for a specific order.

    ``GET /order/v1.0/orders/{id}/cancellationReasons`` → list of
    ``{"cancelCodeId": "...", "description": "..."}``. Use it to discover the
    valid codes to configure ``cancellation_default_code``.
    """
    headers = ifood_auth.authorized_headers()
    if not headers:
        raise IFoodCallbackError("iFood OAuth is not configured (client_id/client_secret)")
    url = f"{_base_url()}/order/v1.0/orders/{order_id}/cancellationReasons"
    try:
        resp = requests.get(url, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodCallbackError(f"iFood cancellationReasons request failed: {exc}") from exc
    if resp.status_code != 200:
        raise IFoodCallbackError(
            f"iFood cancellationReasons HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        reasons = resp.json()
    except ValueError as exc:
        raise IFoodCallbackError("iFood cancellationReasons response was not JSON") from exc
    if not isinstance(reasons, list) or any(not isinstance(r, dict) or not r.get("cancelCodeId") for r in reasons):
        raise IFoodCallbackError("iFood cancellationReasons response has invalid shape")
    return reasons


def request_cancellation(order_id: str, *, code: str = "", description: str = "") -> None:
    """Ask iFood to cancel an order with a valid cancellation code.

    The code must come from iFood's fixed list (see
    :func:`fetch_cancellation_reasons`). It is config-driven
    (``cancellation_default_code``) rather than guessed — sending a wrong code
    is worse than failing loudly.
    """
    code = str(code or _cfg().get("cancellation_default_code") or "").strip()
    if not code:
        raise IFoodCallbackError(
            "no iFood cancellation code — set SHOPMAN_IFOOD['cancellation_default_code'] "
            "(discover valid codes with fetch_cancellation_reasons)"
        )
    # iFood rejects requestCancellation with 400 when `reason` is empty
    # (verified live 2026-07-01) — it is required alongside the code.
    reason = (
        str(description or "").strip()
        or str(_cfg().get("cancellation_default_reason") or "").strip()
        or "Cancelado pela loja"
    )
    send_action(
        order_id,
        "requestCancellation",
        body={"reason": reason, "cancellationCode": code},
    )


def send_for_status(
    order_id: str,
    status: str,
    *,
    cancellation_reason: str = "",
    cancellation_code: str = "",
    fulfillment_type: str = "",
    delivered_by: str = "",
) -> bool:
    """Send a workflow-valid action; missing ownership never authorizes dispatch."""
    if str(order_id).upper().startswith("IFOOD-SIM-"):
        return False
    action = action_for_status(status, fulfillment_type=fulfillment_type, delivered_by=delivered_by)
    if not action:
        return False
    if action == "requestCancellation":
        code = cancellation_code or resolve_cancellation_code(cancellation_reason)
        request_cancellation(order_id, code=code, description=cancellation_reason)
    else:
        send_action(order_id, action)
    return True


__all__ = [
    "confirm",
    "ready_to_pickup",
    "dispatch",
    "request_cancellation",
    "fetch_cancellation_reasons",
    "send_action",
    "send_for_status",
    "action_for_status",
    "workflow_context",
    "remote_status_observed",
    "resolve_cancellation_code",
    "STATUS_ACTION",
    "IFoodCallbackError",
]
