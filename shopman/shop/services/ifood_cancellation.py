"""Durable cancellation requests; only iFood CAN closes a live order."""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.directives import IFOOD_STATUS_CALLBACK, create_deduped

KEY = "ifood_cancellation_request"
TERMINAL_STATUSES = {"cancelled", "completed", "returned"}


def requires_remote_decision(order) -> bool:
    if order.channel_ref != "ifood":
        return False
    if (order.data or {}).get(KEY):
        return True
    # Credentials affect delivery of a request, never the authority to cancel
    # a marketplace order. Missing references fail closed in enqueue_locked.
    external_ref = str(order.external_ref or (order.data or {}).get("external_order_code") or "").strip()
    return not external_ref.upper().startswith("IFOOD-SIM-")


def is_pending(order) -> bool:
    request = (order.data or {}).get(KEY) or {}
    return order.status not in TERMINAL_STATUSES and (
        request.get("state") in {"queued", "sent"}
        or (request.get("state") == "error" and request.get("retryable") is True)
    )


def enqueue_locked(order, *, reason: str, actor: str, extra_data: dict | None) -> bool:
    """Caller holds the Order row lock and transaction until Directive commit."""
    if is_pending(order):
        return True
    external_ref = str(order.external_ref or (order.data or {}).get("external_order_code") or "").strip()
    if not external_ref:
        raise ValueError("Referência iFood ausente. Confira a integração deste pedido.")
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    code = str((extra_data or {}).get("ifood_cancellation_code") or cfg.get("cancellation_default_code") or "").strip()
    if not code:
        raise ValueError("Escolha um motivo permitido pelo iFood antes de solicitar o cancelamento.")
    request_id = uuid4().hex
    data = dict(order.data or {})
    data[KEY] = {
        "id": request_id, "state": "queued", "requested_at": timezone.now().isoformat(),
        "actor": actor, "reason": reason, "code": code, "context": dict(extra_data or {}),
    }
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    create_deduped(
        IFOOD_STATUS_CALLBACK,
        payload={
            "order_ref": order.ref, "ifood_order_id": external_ref, "status": "cancelled",
            "cancellation_reason": reason, "cancellation_code": code,
            "cancellation_request_id": request_id,
        },
        dedupe_key=f"{IFOOD_STATUS_CALLBACK}:{order.ref}:cancellation:{request_id}",
    )
    return True


def should_send(payload) -> bool:
    order = Order.objects.filter(ref=payload.get("order_ref"), channel_ref="ifood").first()
    if order is None or order.status in TERMINAL_STATUSES or (order.data or {}).get("ifood_cancelled"):
        return False
    request = (order.data or {}).get(KEY) or {}
    return request.get("id") == payload.get("cancellation_request_id") and (
        request.get("state") == "queued" or (request.get("state") == "error" and request.get("retryable"))
    )


@transaction.atomic
def record_result(payload, *, state: str, retryable: bool = False) -> None:
    order = Order.objects.select_for_update().filter(ref=payload.get("order_ref"), channel_ref="ifood").first()
    if order is None or order.status in TERMINAL_STATUSES or (order.data or {}).get("ifood_cancelled"):
        return
    data = dict(order.data or {})
    request = dict(data.get(KEY) or {})
    if request.get("id") != payload.get("cancellation_request_id") or request.get("state") == "confirmed":
        return
    request.update(state=state, retryable=retryable, updated_at=timezone.now().isoformat())
    request["last_error"] = (
        "Falha temporária no envio ao iFood. A confirmação continua pendente." if retryable else
        "O iFood não aceitou a solicitação. Consulte os motivos e tente novamente."
    ) if state == "error" else ""
    data[KEY] = request
    order.data = data
    order.save(update_fields=["data", "updated_at"])
