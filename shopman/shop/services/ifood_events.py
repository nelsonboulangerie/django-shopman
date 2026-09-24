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
import threading

from django.conf import settings

from shopman.shop.services import ifood_http, ifood_ingest, ifood_orders, webhook_idempotency

logger = logging.getLogger(__name__)

_IDEMPOTENCY_SCOPE = "webhook:ifood"
# Event codes that create a new order. iFood sends both a short ``code`` (PLC)
# and a ``fullCode`` (PLACED); we accept either.
_PLACED_CODES = {"PLC", "PLACED"}
# Cancelamento originado no iFood (cliente desistiu no app / iFood cancelou):
# refletir no Order local para o Gestor nao tratar pedido ja cancelado pelo iFood.
_CANCELLATION_CODES = {"CAN", "CANCELLED"}
_CONCLUSION_CODES = {"CON", "CONCLUDED"}
_CONFIRMATION_CODES = {"CFM", "CONFIRMED"}
_DISPATCH_CODES = {"DSP", "DISPATCHED"}
_HANDSHAKE_CODES = {"HSD", "HANDSHAKE_DISPUTE", "HSS", "HANDSHAKE_SETTLEMENT"}
_ACK_BATCH = 100  # iFood acknowledges in batches.


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def poll() -> list[dict]:
    """Poll the iFood event stream. Returns the events list (``[]`` on 204/idle)."""
    merchant_id = str(_cfg().get("merchant_id") or "").strip()
    extra = {"x-polling-merchants": merchant_id} if merchant_id else None

    resp = ifood_http.request(
        "GET", "/order/v1.0/events:polling", label="poll", extra_headers=extra, idempotent=True
    )
    if resp is None:
        # Sem credencial, transporte caído ou recusa de edge que sobreviveu às
        # retentativas — `ifood_http` já registrou a forense.
        return []

    # Never broaden merchant scope on a rejected filter: the same app may
    # authorize other stores, including production stores during testing.
    if resp.status_code == 400 and merchant_id:
        logger.warning(
            "ifood_events.poll: iFood rejeitou x-polling-merchants (400) — "
            "IFOOD_MERCHANT_ID provavelmente errado. Filtro preservado; "
            "confira o Merchant ID no portal iFood."
        )
        return []

    if resp.status_code == 204:
        return []
    if resp.status_code != 200:
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
    ok = True
    for start in range(0, len(event_ids), _ACK_BATCH):
        batch = [{"id": eid} for eid in event_ids[start:start + _ACK_BATCH]]
        # Idempotente por id de evento: reconhecer o mesmo id duas vezes é
        # inócuo, então vale retentar também `5xx` e transporte. O risco aqui é
        # o inverso — um ACK que não sai faz o iFood reentregar o evento, e a
        # reentrega já é tratada pelo dedupe durável.
        resp = ifood_http.request(
            "POST",
            "/order/v1.0/events/acknowledgment",
            label="acknowledge",
            extra_headers={"Content-Type": "application/json"},
            json=batch,
            idempotent=True,
        )
        if resp is None or resp.status_code not in (200, 202):
            ok = False
    return ok


def process_events(events: list[dict]) -> dict:
    """Handle a batch of events; acknowledge the ones that were handled.

    Returns a small summary dict: ``{polled, ingested, deduped, ignored, failed, acked}``.
    """
    ingested = deduped = ignored = failed = 0
    handled_ids: list[str] = []
    merchant_id = str(_cfg().get("merchant_id") or "").strip()

    # A API entrega fora de ordem; a doc manda ordenar por ``createdAt``. Sem isso
    # um CON pode ser processado antes do DSP que o precede.
    for event in sorted(events, key=lambda e: str(e.get("createdAt") or "")):
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

        # Remote state changes reconcile only after the order exists.
        if code in _CANCELLATION_CODES | _CONCLUSION_CODES | _CONFIRMATION_CODES | _DISPATCH_CODES | _HANDSHAKE_CODES:
            if code in _HANDSHAKE_CODES:
                outcome = _process_handshake(event, settlement=code in {"HSS", "HANDSHAKE_SETTLEMENT"})
            elif code in _CANCELLATION_CODES:
                outcome = _process_cancellation(event_id, order_id)
            elif code in _CONCLUSION_CODES:
                outcome = _process_conclusion(event_id, order_id)
            else:
                outcome = _process_remote_progress(event_id, order_id, dispatch=code in _DISPATCH_CODES)
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


def _process_remote_progress(event_id: str, order_id: str, *, dispatch: bool) -> str:
    """Apply CFM/DSP only along a legal canonical transition.

    CFM authorizes acceptance; DSP records a handoff only after local readiness.
    Neither event manufactures intermediate preparation stages. Persist remote
    evidence before the transition so its callback cannot echo the same fact.
    """
    if not order_id:
        return "failed"
    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE, f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"

    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import get_fulfillment_type

    code = "DSP" if dispatch else "CFM"
    target = Order.Status.DISPATCHED if dispatch else Order.Status.ACCEPTED
    marker = "remote_dispatched" if dispatch else "remote_confirmed"
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, external_ref=order_id,
            ).first()
            if order is None:
                webhook_idempotency.mark_failed(claim)
                return "failed"
            if dispatch and get_fulfillment_type(order) != "delivery":
                # Fato sem transição possível: pedido de retirada não "sai". Gravar
                # e dar ACK — deixar sem ACK só faz o iFood reentregar para sempre.
                logger.warning("ifood_events: DSP for non-delivery order %s; recorded, nothing to apply", order_id)
                _record_remote(order, marker, event_id)
                webhook_idempotency.mark_done(claim, response_body={"status": "recorded", "order_ref": order.ref})
                return "deduped"

            terminal = order.status in Order.TERMINAL_STATUSES
            already_applied = terminal or order.status in (
                {Order.Status.DISPATCHED, Order.Status.DELIVERED}
                if dispatch else {Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY,
                                  Order.Status.DISPATCHED, Order.Status.DELIVERED}
            )
            expected = Order.Status.READY if dispatch else Order.Status.NEW
            # O fato é gravado ANTES de qualquer transição, para o aviso dela não
            # ecoar ao iFood o que veio dele.
            _record_remote(order, marker, event_id)
            if not already_applied and order.status != expected:
                # ACK é "armazenei", não "apliquei" (doc do polling). O fato fica no
                # pedido e a reconciliação o aplica quando o estado local chegar lá
                # — antes, o evento ficava sem ACK e o iFood usava a fila de
                # reentrega como fila de espera nossa, o que o Firefly pune.
                logger.info(
                    "ifood_events: %s recorded for order %s (status %s); applies when the local order catches up",
                    code, order_id, order.status,
                )
                webhook_idempotency.mark_done(
                    claim, response_body={"status": "recorded_pending", "order_ref": order.ref},
                )
                return "ingested"
            if not already_applied:
                _reconcile_locked(order)
                order.refresh_from_db()
                if order.status == expected:
                    raise ValueError(f"iFood {code} did not reach its local target status")
            webhook_idempotency.mark_done(
                claim, response_body={"status": "already_processed" if already_applied else target, "order_ref": order.ref},
            )
    except Exception:
        logger.exception("ifood_events: failed to reconcile %s for order %s (event %s)", code, order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "deduped" if already_applied else "ingested"


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
        if not cancelled and order.status not in Order.TERMINAL_STATUSES:
            logger.warning(
                "ifood_events: CAN cannot reconcile active order %s (status %s); "
                "leaving unacknowledged for operational review", order_id, order.status,
            )
            webhook_idempotency.mark_failed(claim)
            return "failed"
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

            _record_remote(order, "remote_concluded", event_id)
            if not _conclusion_allowed(order):
                # O iFood já encerrou, mas aqui o pedido ainda não chegou à entrega
                # (entrega própria parada em preparo, retirada ainda não pronta).
                # A regra de NÃO pular a custódia do entregador continua de pé; o
                # que muda é o ACK: o fato fica gravado, o card avisa que o iFood
                # concluiu, e a reconciliação fecha quando o pedido chegar lá.
                logger.info(
                    "ifood_events: CON recorded for order %s (status %s); concludes when the local handoff happens",
                    order_id, order.status,
                )
                webhook_idempotency.mark_done(
                    claim, response_body={"status": "recorded_pending", "order_ref": order.ref},
                )
                return "ingested"
            _reconcile_locked(order)
            order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                raise ValueError("iFood conclusion did not complete the local order")
            webhook_idempotency.mark_done(claim, response_body={"status": "concluded", "order_ref": order.ref})
    except Exception:
        logger.exception("ifood_events: failed to conclude order %s (event %s)", order_id, event_id)
        webhook_idempotency.mark_failed(claim)
        return "failed"
    return "ingested"


# ── Fatos do iFood × estado local ──────────────────────────────────────────────
# Um evento de status do iFood (CFM, DSP, CON) é FATO sobre o pedido lá. Ele é
# gravado em ``order.data["ifood"]`` e recebe ACK na mesma transação — a doc do
# polling pede ACK "após armazenar", não após aplicar. A aplicação local segue as
# regras de sempre (nunca inventa preparo nem saída, nunca pula a custódia do
# entregador) e acontece em dois momentos: quando o fato chega, se o pedido já
# está no ponto certo, e depois de cada transição local, pelo ``order_changed``.
_RECONCILING = threading.local()


def _record_remote(order, marker: str, event_id: str) -> None:
    """Grava o fato do iFood no pedido, uma vez só (o primeiro evento é a prova)."""
    from django.utils import timezone

    data = dict(order.data or {})
    facts = dict(data.get("ifood") or {})
    if facts.get(marker):
        return
    facts[marker] = {"event_id": event_id, "observed_at": timezone.now().isoformat()}
    data["ifood"] = facts
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _conclusion_allowed(order) -> bool:
    """Onde o CON pode fechar o pedido: depois da entrega, ou na retirada pronta."""
    from shopman.orderman.models import Order

    from shopman.shop.services.order_helpers import get_fulfillment_type

    fulfillment_type = get_fulfillment_type(order)
    if fulfillment_type == "delivery":
        return order.status in (Order.Status.DISPATCHED, Order.Status.DELIVERED)
    return fulfillment_type == "pickup" and order.status == Order.Status.READY


def _reconcile_locked(order) -> None:
    """Aplica, pelo caminho legal, o que os fatos do iFood já autorizam.

    Chamada com o pedido travado (``select_for_update``). Cada passo é uma das
    transições que o processamento dos eventos sempre fez; o laço só encadeia
    quando um fato destrava o seguinte (DSP leva a "saiu", e aí o CON conclui).
    """
    from django.utils import timezone
    from shopman.orderman.models import Order

    from shopman.shop.services import ifood_cancellation, operator_orders
    from shopman.shop.services.order_helpers import get_fulfillment_type

    for _ in range(4):
        if order.status in Order.TERMINAL_STATUSES:
            return
        facts = (order.data or {}).get("ifood") or {}
        if facts.get("remote_concluded") and _conclusion_allowed(order):
            if ifood_cancellation.is_pending(order):
                # CON confirma a entrega, não o cancelamento. Guarda o pedido
                # original para auditoria e aposenta a trava operacional dele na
                # mesma transação da conclusão.
                data = dict(order.data or {})
                request = dict(data[ifood_cancellation.KEY])
                request.update(
                    state="superseded", resolution="order_concluded",
                    resolved_at=timezone.now().isoformat(), retryable=False,
                )
                data[ifood_cancellation.KEY] = request
                order.data = data
                order.save(update_fields=["data", "updated_at"])
            if get_fulfillment_type(order) == "delivery" and order.status == Order.Status.DISPATCHED:
                operator_orders.confirm_received(order, actor="system:ifood")
                order.refresh_from_db()
            if order.status != Order.Status.COMPLETED:
                operator_orders.advance_order(order, actor="system:ifood")
                order.refresh_from_db()
            return
        if (facts.get("remote_dispatched") and order.status == Order.Status.READY
                and get_fulfillment_type(order) == "delivery"):
            operator_orders.advance_order(order, actor="system:ifood:DSP")
            order.refresh_from_db()
            continue
        if facts.get("remote_confirmed") and order.status == Order.Status.NEW:
            operator_orders.confirm_order(order, actor="system:ifood:CFM")
            order.refresh_from_db()
            continue
        return


def reconcile_remote(order) -> None:
    """Depois de uma transição local, aplica o que o iFood já tinha dito.

    Ex.: o entregador do iFood retirou antes de a cozinha marcar "Pronto" (DSP
    gravado com o pedido em preparo); quando a cozinha marca, o pedido sai e, se
    o CON também já chegou, conclui — sem nenhum aviso ecoar ao iFood.
    """
    if getattr(order, "channel_ref", "") != ifood_ingest.IFOOD_CHANNEL_REF:
        return
    facts = (order.data or {}).get("ifood") or {}
    if not any(facts.get(m) for m in ("remote_confirmed", "remote_dispatched", "remote_concluded")):
        return
    if getattr(_RECONCILING, "active", False):
        return  # as transições da própria reconciliação disparam order_changed

    from django.db import transaction
    from shopman.orderman.models import Order

    _RECONCILING.active = True
    try:
        with transaction.atomic():
            locked = Order.objects.select_for_update().filter(pk=order.pk).first()
            if locked is not None:
                _reconcile_locked(locked)
    except Exception:
        # A transição do operador já aconteceu e não pode ser desfeita por isto;
        # o fato continua gravado e a próxima transição tenta de novo.
        logger.exception("ifood_events: reconcile failed for order %s", getattr(order, "ref", "?"))
    finally:
        _RECONCILING.active = False


def run_once() -> dict:
    """Poll once and process. Used by the management command / cron tick."""
    return process_events(poll())


__all__ = ["poll", "acknowledge", "process_events", "run_once"]


def _process_handshake(event: dict, *, settlement: bool) -> str:
    from django.db import transaction
    from shopman.orderman.models import Order

    from shopman.shop.services import ifood_handshake

    if not event.get("orderId"):
        return "failed"
    claim = webhook_idempotency.claim(
        _IDEMPOTENCY_SCOPE, f"event:{webhook_idempotency.stable_webhook_key(event['id'])}",
    )
    if claim.replayed:
        return "deduped"
    if claim.in_progress:
        return "failed"
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(channel_ref="ifood", external_ref=event["orderId"])
            changed = ifood_handshake.persist_event(order, event, settlement=settlement)
            webhook_idempotency.mark_done(claim, response_body={"status": "persisted", "order_ref": order.ref})
        return "ingested" if changed else "deduped"
    except Exception:
        logger.exception("ifood_events: handshake persistence failed for event %s", event["id"])
        webhook_idempotency.mark_failed(claim)
        return "failed"
