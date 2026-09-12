"""iFood Order Module event polling loop (WP-2).

Verified live (2026-06-30):

- Poll: ``GET /order/v1.0/events:polling`` → ``200`` with an events array, or
  ``204`` when there is nothing to process.
- Acknowledge: ``POST /order/v1.0/events/acknowledgment`` with body
  ``[{"id": "<eventId>"}, ...]`` → ``202``. An empty body is rejected ``400``.

Each event is lightweight (``id``, ``code`` / ``fullCode``, ``orderId``). This
service turns a ``PLACED`` event into a real ``Order`` by fetching the full
order (:mod:`shopman.shop.services.ifood_orders`) and handing the canonical
payload to :func:`shopman.shop.services.ifood_ingest.ingest`.

Robustness contract
-------------------

- Dedupe is durable, via :mod:`shopman.shop.services.webhook_idempotency`
  (scope ``webhook:ifood``, one claim per event id) — the same event never
  ingests twice, even across worker restarts.
- An event is **acknowledged only after it is handled** (ingested, deduped, or
  an ignorable code). A processing failure leaves the event un-acked so iFood
  re-delivers it — the same at-least-once guarantee the webhook path has.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth, ifood_ingest, ifood_orders, webhook_idempotency

logger = logging.getLogger(__name__)

_IDEMPOTENCY_SCOPE = "webhook:ifood"
# Event codes that create a new order. iFood sends both a short ``code`` (PLC)
# and a ``fullCode`` (PLACED); we accept either.
_PLACED_CODES = {"PLC", "PLACED"}
# Cancelamento originado no iFood (cliente desistiu no app / iFood cancelou):
# refletir no Order local para o Gestor nao tratar pedido ja cancelado pelo iFood.
_CANCELLATION_CODES = {"CAN", "CANCELLED"}
_CONCLUSION_CODES = {"CON", "CONCLUDED"}
_ACK_BATCH = 100  # iFood acknowledges in batches.


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def poll() -> list[dict]:
    """Poll the iFood event stream. Returns the events list (``[]`` on 204/idle)."""
    headers = ifood_auth.authorized_headers()
    if not headers:
        logger.warning("ifood_events.poll: OAuth not configured — skipping")
        return []

    url = f"{_base_url()}/order/v1.0/events:polling"
    timeout = int(_cfg().get("timeout") or 30)
    merchant_id = str(_cfg().get("merchant_id") or "").strip()
    poll_headers = {**headers, "x-polling-merchants": merchant_id} if merchant_id else headers

    try:
        resp = requests.get(url, headers=poll_headers, timeout=timeout)
        # Never broaden merchant scope on a rejected filter: the same app may
        # authorize other stores, including production stores during testing.
        if resp.status_code == 400 and merchant_id:
            logger.warning(
                "ifood_events.poll: iFood rejeitou x-polling-merchants (400) — "
                "IFOOD_MERCHANT_ID provavelmente errado. Filtro preservado; "
                "confira o Merchant ID no portal iFood."
            )
    except requests.RequestException as exc:
        logger.warning("ifood_events.poll: request failed: %s", exc)
        return []

    if resp.status_code == 204:
        return []
    if resp.status_code != 200:
        logger.warning("ifood_events.poll: HTTP %s: %s", resp.status_code, resp.text[:200])
        return []
    try:
        events = resp.json()
    except ValueError:
        logger.warning("ifood_events.poll: response was not JSON")
        return []
    return events if isinstance(events, list) else []


def acknowledge(event_ids: list[str]) -> bool:
    """Acknowledge processed events so iFood stops re-delivering them."""
    event_ids = [e for e in event_ids if e]
    if not event_ids:
        return True
    headers = ifood_auth.authorized_headers({"Content-Type": "application/json"})
    if not headers:
        return False

    ok = True
    url = f"{_base_url()}/order/v1.0/events/acknowledgment"
    for start in range(0, len(event_ids), _ACK_BATCH):
        batch = [{"id": eid} for eid in event_ids[start:start + _ACK_BATCH]]
        try:
            resp = requests.post(url, json=batch, headers=headers, timeout=int(_cfg().get("timeout") or 30))
        except requests.RequestException as exc:
            logger.warning("ifood_events.acknowledge: request failed: %s", exc)
            ok = False
            continue
        if resp.status_code not in (200, 202):
            logger.warning("ifood_events.acknowledge: HTTP %s: %s", resp.status_code, resp.text[:200])
            ok = False
    return ok


def process_events(events: list[dict]) -> dict:
    """Handle a batch of events; acknowledge the ones that were handled.

    Returns a small summary dict: ``{polled, ingested, deduped, ignored, failed, acked}``.
    """
    ingested = deduped = ignored = failed = 0
    handled_ids: list[str] = []
    merchant_id = str(_cfg().get("merchant_id") or "").strip()

    for event in events:
        event_id = str(event.get("id") or "").strip()
        code = str(event.get("fullCode") or event.get("code") or "").upper()
        order_id = str(event.get("orderId") or "").strip()

        # Check before handling even ignorable codes: acknowledging an event
        # from another merchant would consume it for that store's integration.
        # Legacy event fixtures/providers can omit merchantId; retain support
        # for those while rejecting explicit mismatches.
        event_merchant_id = str(event.get("merchantId") or "").strip()
        if merchant_id and event_merchant_id and event_merchant_id != merchant_id:
            logger.warning("ifood_events: event %s belongs to another merchant; leaving unacknowledged", event_id)
            failed += 1
            continue

        if not event_id:
            logger.warning("ifood_events: event without id, skipping: %s", event)
            failed += 1
            continue

        # Remote terminal events reconcile only after the order exists.
        if code in _CANCELLATION_CODES or code in _CONCLUSION_CODES:
            processor = _process_cancellation if code in _CANCELLATION_CODES else _process_conclusion
            outcome = processor(event_id, order_id)
            if outcome == "ingested":
                ingested += 1
                handled_ids.append(event_id)
            elif outcome == "deduped":
                deduped += 1
                handled_ids.append(event_id)
            else:  # failed — sem ack, iFood reentrega
                failed += 1
            continue

        # Non-order-creating codes are acknowledged and ignored (WP-2 scope).
        if code not in _PLACED_CODES:
            ignored += 1
            handled_ids.append(event_id)
            continue

        outcome = _process_placed(event_id, order_id)
        if outcome == "ingested":
            ingested += 1
            handled_ids.append(event_id)
        elif outcome == "deduped":
            deduped += 1
            handled_ids.append(event_id)
        else:  # "failed" — leave un-acked for redelivery
            failed += 1

    acked = acknowledge(handled_ids) if handled_ids else True
    summary = {
        "polled": len(events),
        "ingested": ingested,
        "deduped": deduped,
        "ignored": ignored,
        "failed": failed,
        "acked": acked,
    }
    logger.info("ifood_events.process_events: %s", summary)
    return summary


def _process_placed(event_id: str, order_id: str) -> str:
    """Ingest one PLACED event. Returns 'ingested' | 'deduped' | 'failed'."""
    if not order_id:
        logger.warning("ifood_events: PLACED event %s without orderId", event_id)
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"  # já ingerido antes (done) — seguro ackar
    if claim.in_progress:
        # Outra instância (ex.: rolling deploy) está processando ESTE evento agora.
        # NÃO ackar: se ela concluir, o próximo poll vê replayed e acka; se ela
        # morrer, o iFood reentrega. Ackar aqui perderia o pedido caso a outra
        # instância falhasse no meio.
        return "failed"

    # Order already ingested via another event/webhook for the same orderId.
    from shopman.orderman.models import Order

    if Order.objects.filter(
        channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id
    ).exists():
        webhook_idempotency.mark_done(claim, response_body={"status": "already_processed"})
        return "deduped"

    try:
        order = ifood_orders.fetch_order(order_id)
        payload = ifood_orders.map_order(order)
        created = ifood_ingest.ingest(payload)
    except Exception:
        logger.exception("ifood_events: failed to ingest order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"

    webhook_idempotency.mark_done(claim, response_body={"status": "accepted", "order_ref": created.ref})
    return "ingested"


def _process_cancellation(event_id: str, order_id: str) -> str:
    """Reflect an iFood-originated cancellation into our Order.

    Mesma disciplina do PLACED: claim por event id (idempotente), ack só
    quando tratado, sem ack em falha (o iFood reentrega). Usa o serviço
    canônico de cancelamento (grava cancellation_reason/cancelled_by antes
    da transição) com a marca ifood_cancelled para o ifood_status não
    responder requestCancellation de volta para quem já cancelou.
    """
    if not order_id:
        logger.warning("ifood_events: CAN event %s without orderId", event_id)
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from shopman.orderman.models import Order

    order = Order.objects.filter(
        channel_ref=ifood_ingest.IFOOD_CHANNEL_REF,
        external_ref=order_id,
    ).first()
    if order is None:
        # CAN can arrive before PLACED, including earlier in the same batch.
        # Release the claim and leave CAN unacknowledged so redelivery applies
        # the cancellation after the order has been materialized.
        webhook_idempotency.mark_failed(claim)
        return "failed"
    if order.status == "cancelled":
        # Legacy versions cancelled locally before sending requestCancellation.
        # CAN still confirms remote ownership, so queued legacy callbacks must
        # be suppressed even when no further local transition is needed.
        if not (order.data or {}).get("ifood_cancelled"):
            order.data = {**(order.data or {}), "ifood_cancelled": True}
            order.save(update_fields=["data", "updated_at"])
        webhook_idempotency.mark_done(claim, response_body={"status": "already_cancelled"})
        return "deduped"

    try:
        from shopman.shop.services import cancellation

        cancelled = cancellation.cancel(
            order,
            reason="Cancelamento confirmado pelo iFood",
            actor="system:ifood",
            extra_data={"ifood_cancelled": True},
        )
        outcome = "ingested" if cancelled else "deduped"
    except Exception:
        logger.exception("ifood_events: failed to cancel order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"

    webhook_idempotency.mark_done(claim, response_body={"status": "cancelled", "order_ref": order.ref})
    return outcome


def _process_conclusion(event_id: str, order_id: str) -> str:
    """Close an order through its canonical handoff flow, without inventing work.

    CON can precede PLACED or the operator's dispatch. Keep it retryable until
    the local order can conclude legally; never manufacture preparation or
    dispatch transitions (and their outbound iFood callbacks).
    """
    if not order_id:
        return "failed"

    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE,
        f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services import operator_orders
    from shopman.shop.services.order_helpers import get_fulfillment_type

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
            ).first()
            if order is None:
                webhook_idempotency.mark_failed(claim)
                return "failed"
            if order.status in Order.TERMINAL_STATUSES:
                # A later CON must not reopen a cancellation or a return.
                webhook_idempotency.mark_done(claim, response_body={"status": "already_terminal"})
                return "deduped"

            fulfillment_type = get_fulfillment_type(order)
            delivery = fulfillment_type == "delivery"
            allowed = (
                order.status in (Order.Status.DISPATCHED, Order.Status.DELIVERED)
                if delivery else fulfillment_type == "pickup" and order.status == Order.Status.READY
            )
            if not allowed:
                logger.warning("ifood_events: CON awaiting local handoff for order %s (status %s)", order_id, order.status)
                webhook_idempotency.mark_failed(claim)
                return "failed"

            if delivery and order.status == Order.Status.DISPATCHED:
                operator_orders.confirm_received(order, actor="system:ifood")
                order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                operator_orders.advance_order(order, actor="system:ifood")
                order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                raise ValueError("iFood conclusion did not complete the local order")
            webhook_idempotency.mark_done(claim, response_body={"status": "concluded", "order_ref": order.ref})
    except Exception:
        logger.exception("ifood_events: failed to conclude order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "ingested"


def run_once() -> dict:
    """Poll once and process. Used by the management command / cron tick."""
    return process_events(poll())


__all__ = ["poll", "acknowledge", "process_events", "run_once"]
