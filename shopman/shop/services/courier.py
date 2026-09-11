"""Courier — despacho de entregadores via logística externa (Machine).

Funil único da corrida: o despacho (Directive ``courier.dispatch``) e as duas
vias de status (webhook push + polling ``courier.sync``) convergem em
:func:`apply_status`, que grava ``Order.data["courier"]`` (schema em
docs/reference/data-schemas.md), espelha na timeline do pedido e emite SSE.

Transições de pedido derivadas do status da corrida:
  E (coletou)   → advance_order  → DISPATCHED → notificação "saiu para entrega"
  F (finalizou) → confirm_received → DELIVERED → notificação "entregue"
  N/C (falhou)  → OperatorAlert + re-despacho manual habilitado no gestor

O ``DELIVERY_AUTO_COMPLETE`` (ETA + folga) segue como rede de segurança: quando
o ``F`` da Machine chega antes, o handler revalida o status e vira no-op.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters import get_adapter
from shopman.shop.adapters.courier_machine import (
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    CourierError,
)
from shopman.shop.services.order_helpers import get_fulfillment_type, merge_order_data

logger = logging.getLogger(__name__)

#: Segundos até o primeiro poll de status após abrir a corrida.
FIRST_SYNC_SECONDS = 45

#: TTL do cache de cotação (a origem é fixa — a loja; o destino define a chave).
ESTIMATE_CACHE_SECONDS = 600

#: Intervalo default de polling quando Shop.defaults não configura.
DEFAULT_POLL_SECONDS = 60


# ── Bloco Order.data["courier"] ─────────────────────────────────────


def get_block(order) -> dict:
    data = order.data if isinstance(order.data, dict) else {}
    block = data.get("courier")
    return block if isinstance(block, dict) else {}


def _save_block(order, block: dict, *, emit: dict | None = None) -> None:
    merge_order_data(order, {"courier": block})
    _emit_sse(order, emit or {"status": block.get("status", "")})


def _emit_sse(order, payload: dict) -> None:
    try:
        from shopman.shop.handlers._sse_emitters import emit_courier_update

        emit_courier_update(order, payload)
    except Exception:
        logger.warning("courier.sse_emit_failed order=%s", order.ref, exc_info=True)


def has_active_ride(order) -> bool:
    """Corrida ativa = id_mch presente e status não-terminal."""
    block = get_block(order)
    return bool(block.get("id_mch")) and block.get("status") not in TERMINAL_STATUSES


def is_enabled_for(order) -> bool:
    """Adapter configurado + pedido é entrega. (O "auto" por canal é gate do lifecycle.)"""
    return get_adapter("courier") is not None and get_fulfillment_type(order) == "delivery"


# ── Payload Machine ─────────────────────────────────────────────────


def build_machine_payload(order) -> dict:
    """Corpo do POST /abrirSolicitacao a partir do pedido + Shop (partida)."""
    from django.conf import settings

    from shopman.shop.models import Shop
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    handoff = build_dispatch_payload(order)  # NotDeliverableError p/ não-delivery
    shop = Shop.load()
    if shop is None:
        raise ValueError("Loja não configurada — impossível montar a partida da corrida.")
    cfg = getattr(settings, "SHOPMAN_MACHINE", {}) or {}

    pickup_street = " ".join(
        p for p in (shop.route, shop.street_number) if p
    ).strip() or shop.formatted_address
    dropoff_street = " ".join(
        p for p in (handoff["route"], handoff["street_number"]) if p
    ).strip() or handoff["formatted_address"]

    parada = {
        "endereco_parada": dropoff_street,
        "bairro_parada": handoff["neighborhood"],
        "complemento_parada": handoff["complement"],
        "cidade_parada": handoff["city"],
        "estado_parada": handoff["state_code"],
        "referencia_parada": handoff["delivery_instructions"],
        "id_externo": order.ref,
        "observacao_parada": f"Pedido {order.ref}",
        "nome_cliente_parada": handoff["customer_name"],
        "telefone_cliente_parada": handoff["customer_phone"],
    }
    if handoff["latitude"] is not None and handoff["longitude"] is not None:
        parada["lat_parada"] = str(handoff["latitude"])
        parada["lng_parada"] = str(handoff["longitude"])

    partida = {
        "endereco": pickup_street,
        "bairro": shop.neighborhood,
        "cidade": shop.city,
        "estado": shop.state_code,
    }
    if shop.latitude is not None and shop.longitude is not None:
        partida["lat"] = str(shop.latitude)
        partida["lng"] = str(shop.longitude)

    return {
        "forma_pagamento": str(cfg.get("forma_pagamento") or "F"),
        "partida": partida,
        "paradas": [parada],
        "retorno": bool(cfg.get("retorno")),
    }


# ── Cotação ─────────────────────────────────────────────────────────


def estimate_for_order(order, *, store: bool = False) -> dict | None:
    """Cotação da corrida (custo interno — o preço ao cliente segue nas faixas/zonas).

    Best-effort: sem adapter, sem coordenadas ou com a Machine fora → None.
    Cache de 10 min por destino (a origem é sempre a loja). ``store=True``
    grava o resultado em ``Order.data["courier"]["estimate"]``.
    """
    adapter = get_adapter("courier")
    if adapter is None or get_fulfillment_type(order) != "delivery":
        return None

    from shopman.shop.models import Shop

    shop = Shop.load()
    structured = (order.data or {}).get("delivery_address_structured") or {}
    lat, lng = structured.get("latitude"), structured.get("longitude")
    if shop is None or None in (shop.latitude, shop.longitude, lat, lng):
        return None

    cache_key = f"courier:est:{float(lat):.4f}:{float(lng):.4f}"
    estimate = cache.get(cache_key)
    if estimate is None:
        try:
            result = adapter.estimate(
                pickup={"lat": str(shop.latitude), "lng": str(shop.longitude)},
                dropoff={"lat": str(lat), "lng": str(lng)},
            )
        except CourierError as exc:
            logger.warning("courier.estimate_failed order=%s: %s", order.ref, exc)
            return None
        if result is None:
            return None
        estimate = {"value_q": result.value_q, "minutes": result.minutes, "km": result.km}
        cache.set(cache_key, estimate, ESTIMATE_CACHE_SECONDS)

    if store:
        with transaction.atomic():
            Order.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()
            block = dict(get_block(order))
            block["estimate"] = estimate
            _save_block(order, block, emit={"kind": "estimate"})
    return estimate


# ── Despacho ────────────────────────────────────────────────────────


def unresolved_dispatch(order, *, exclude_pk=None):
    """Pure receipt read. Unknown/start never authorizes another provider POST."""
    from shopman.shop.directives import COURIER_DISPATCH

    tasks = Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref,
        payload__dispatch_attempt__state__in=["started", "unknown", "accepted"])
    if exclude_pk is not None:
        tasks = tasks.exclude(pk=exclude_pk)
    block = get_block(order)
    known = {block.get("id_mch"), *[attempt.get("id_mch") for attempt in block.get("attempts", [])]}
    for task in tasks.order_by("-pk"):
        receipt = (task.payload or {}).get("dispatch_attempt", {})
        if receipt.get("state") == "accepted" and receipt.get("courier_ref") in known:
            continue
        return task
    return None


def ensure_dispatch_resolved(order) -> None:
    if unresolved_dispatch(order) is not None:
        raise ValueError("Há um despacho sem resultado confirmado. Confira a solicitação na central antes de abrir outra corrida.")


def request_dispatch(order, *, actor: str) -> Directive | None:
    """Enfileira o despacho da corrida (Directive ``courier.dispatch``).

    No-op quando: adapter ausente, pedido não é entrega, corrida ativa em
    andamento, ou já existe directive de despacho na fila (idempotente).
    """
    from shopman.shop.directives import COURIER_DISPATCH

    ensure_dispatch_resolved(order)
    if not is_enabled_for(order):
        return None
    if order.status not in (Order.Status.READY, Order.Status.DISPATCHED):
        return None
    if has_active_ride(order):
        return None

    existing = Directive.objects.filter(
        topic=COURIER_DISPATCH,
        payload__order_ref=order.ref,
        status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
    ).first()
    if existing:
        return existing

    from shopman.shop.directives import create_deduped

    attempt_n = len(get_block(order).get("attempts") or []) + 1
    directive = create_deduped(
        COURIER_DISPATCH,
        payload={"order_ref": order.ref, "channel_ref": order.channel_ref or "", "actor": actor},
        dedupe_key=f"courier.dispatch:{order.ref}:{attempt_n}",
    )
    if directive is None:
        return None
    order.emit_event(event_type="courier_dispatch_requested", actor=actor)
    logger.info("courier.dispatch_requested order=%s actor=%s", order.ref, actor)
    return directive


def dispatch_revision(order) -> str:
    """Observed destination, ride and order facts for the local dispatch command."""
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    return mutation_fingerprint({"version": 1, "order": order.ref, "status": order.status,
        "channel": order.channel_ref, "total_q": order.total_q, "snapshot": order.snapshot,
        "data": {key: (order.data or {}).get(key) for key in (
            "fulfillment_type", "delivery_method", "delivery_address_structured",
            "delivery_address", "recipient", "customer", "customer_phone", "payment", "courier",
        )}})


@transaction.atomic
def redispatch(order, *, actor: str, expected_revision: str | None = None) -> Directive:
    """Re-despacho manual pelo operador após corrida N/C ou erro terminal."""
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if expected_revision is not None and dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou a corrida mudou. Confira o contexto antes de despachar.")
    ensure_dispatch_resolved(order)
    if get_adapter("courier") is None:
        raise ValueError("Nenhum adapter de courier configurado.")
    if get_fulfillment_type(order) != "delivery":
        raise ValueError("Re-despacho só se aplica a pedidos de entrega.")
    if order.status not in (Order.Status.READY, Order.Status.DISPATCHED):
        raise ValueError("Re-despacho só é possível com o pedido pronto ou em entrega.")
    if has_active_ride(order):
        raise ValueError("Já existe uma corrida ativa para este pedido.")

    block = get_block(order)
    if block.get("id_mch"):
        _archive_current_ride(block)
    block.pop("error", None)
    _save_block(order, block, emit={"kind": "redispatch"})

    directive = request_dispatch(order, actor=actor)
    if directive is None:
        raise ValueError("Não foi possível enfileirar o re-despacho.")
    return directive


def cancel_ride(order, *, actor: str, reason_id: int | None = None) -> None:
    """Cancela a corrida ativa na Machine (ação do operador no gestor)."""
    adapter = get_adapter("courier")
    if adapter is None:
        raise ValueError("Nenhum adapter de courier configurado.")
    block = get_block(order)
    if not has_active_ride(order):
        raise ValueError("Não há corrida ativa para cancelar.")
    if block.get("status") not in CANCELLABLE_STATUSES:
        raise ValueError(
            "A corrida já está com o entregador em rota — combine o retorno "
            "por telefone com a central."
        )

    try:
        adapter.cancel(block["id_mch"], reason_id=reason_id)
    except CourierError as exc:
        raise ValueError(f"A central recusou o cancelamento: {exc}") from exc

    apply_status(order, "C", source=f"operator:{actor}")


def _archive_current_ride(block: dict) -> None:
    """Move a corrida corrente para o histórico ``attempts``."""
    attempts = list(block.get("attempts") or [])
    attempts.append(
        {
            "id_mch": block.get("id_mch", ""),
            "status": block.get("status", ""),
            "requested_at": block.get("requested_at", ""),
            "ended_at": timezone.now().isoformat(),
        }
    )
    block["attempts"] = attempts
    for key in ("id_mch", "status", "dispatched_at", "finished_at", "driver",
                "tracking_url", "confirmation_code", "final_value_q"):
        block.pop(key, None)


# ── Status (funil único: webhook + polling) ─────────────────────────

_STATUS_EVENT = "courier_status"


def apply_status(order, machine_status: str, *, source: str, details: dict | None = None) -> None:
    """Persist the external fact once; every replay retries its local derivation.

    Enrichment uses the observed ride outside the lock. A replacement ride cannot
    adopt its response. A local custody refusal never rolls back the external fact.
    """
    status = (machine_status or "").strip().upper()
    observed = dict(get_block(order))
    ride_id = observed.get("id_mch")
    if not status or not ride_id:
        return
    enrichment = dict(observed)
    if status == "A" and observed.get("status") != status and not observed.get("driver"):
        _enrich_accepted(enrichment, details)
    if status == "F" and observed.get("status") != status:
        _enrich_finished(enrichment, details)

    failed_ride = False
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("id_mch") != ride_id:
            return
        previous = block.get("status")
        if previous in TERMINAL_STATUSES and previous != status:
            return
        if previous != status:
            now_iso = timezone.now().isoformat()
            for key in ("driver", "tracking_url", "confirmation_code", "final_value_q"):
                if key in enrichment:
                    block[key] = enrichment[key]
            block.update(status=status, last_event_at=now_iso, last_source=source)
            if status == "E":
                block.setdefault("dispatched_at", now_iso)
            if status == "F":
                block["finished_at"] = now_iso
            order.emit_event(event_type=_STATUS_EVENT, actor=source,
                             payload={"status": status, "id_mch": ride_id})
            failed_ride = status in ("N", "C")
            if failed_ride:
                _archive_current_ride(block)
            _save_block(order, block, emit={"kind": "ride_ended" if failed_ride else "status", "status": status})
    if failed_ride and not source.startswith("operator:"):
        _alert_ride_failed(order, status)
    if not failed_ride:
        recover_local_status(order, ride_id=ride_id)


def recover_local_status(order, *, ride_id: str) -> None:
    """Reconcile only the known ride's due local transitions, without provider I/O."""
    from shopman.shop.services import operator_orders

    order.refresh_from_db()
    block = get_block(order)
    if block.get("id_mch") != ride_id:
        return
    status = block.get("status")
    if status in ("E", "F") and order.status == Order.Status.READY:
        operator_orders.advance_order(
            order, actor="courier:machine", target_status=Order.Status.DISPATCHED,
            expected_courier_id=ride_id,
        )
    if status == "F":
        operator_orders.confirm_received(order, actor="courier:machine", expected_courier_id=ride_id)


def _enrich_accepted(block: dict, details: dict | None) -> None:
    """Corrida aceita: busca entregador + link de rastreio (best-effort)."""
    adapter = get_adapter("courier")
    if adapter is None:
        return
    try:
        info = details or adapter.get_details(block["id_mch"])
        driver = info.get("driver") or {}
        if driver:
            block["driver"] = {
                "name": str(driver.get("name") or ""),
                "phone": str(driver.get("phone") or ""),
                "vehicle_plate": str(driver.get("vehicle_plate") or ""),
                "vehicle_model": str(driver.get("vehicle_model") or ""),
            }
    except CourierError as exc:
        logger.warning("courier.details_failed id_mch=%s: %s", block.get("id_mch"), exc)
    try:
        links = adapter.tracking_links(block["id_mch"])
        if links:
            block["tracking_url"] = str(links[0].get("link_rastreio") or "")
            code = links[0].get("codigo_confirmacao")
            block["confirmation_code"] = str(code) if code is not None else ""
    except CourierError as exc:
        logger.warning("courier.tracking_failed id_mch=%s: %s", block.get("id_mch"), exc)


def _enrich_finished(block: dict, details: dict | None) -> None:
    """Corrida finalizada: valor final cobrado pela central (best-effort)."""
    adapter = get_adapter("courier")
    if adapter is None:
        return
    try:
        info = details or adapter.get_details(block["id_mch"])
        finished = info.get("finished") or {}
        final_value = finished.get("final_value")
        if final_value is not None:
            from shopman.shop.adapters.courier_machine import _to_q

            block["final_value_q"] = _to_q(final_value)
    except CourierError as exc:
        logger.warning("courier.finished_details_failed id_mch=%s: %s", block.get("id_mch"), exc)


def _alert_ride_failed(order, status: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    if status == "N":
        alert_type, message = (
            "courier_not_attended",
            f"Nenhum entregador aceitou a corrida do pedido {order.ref}. "
            "Re-despache ou combine entrega própria.",
        )
    else:
        alert_type, message = (
            "courier_ride_cancelled",
            f"A central cancelou a corrida do pedido {order.ref}. "
            "Re-despache ou combine entrega própria.",
        )
    try:
        alert_adapter.create(alert_type, "warning", message, order_ref=order.ref)
    except Exception:
        logger.warning("courier.alert_failed order=%s", order.ref, exc_info=True)


# ── Polling (fallback do webhook) ───────────────────────────────────


def poll_seconds() -> int:
    """Intervalo de polling do status (Shop.defaults.delivery.courier_poll_seconds).

    0 desliga o polling (quando o webhook estiver homologado).
    """
    from shopman.shop.models import Shop

    shop = Shop.load()
    delivery_cfg = ((shop.defaults if shop else {}) or {}).get("delivery") or {}
    try:
        return int(delivery_cfg.get("courier_poll_seconds", DEFAULT_POLL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_POLL_SECONDS


def schedule_sync(order, *, delay_seconds: int) -> None:
    """Agenda (ou reagenda) o próximo poll de status. Idempotente."""
    from shopman.shop.directives import COURIER_SYNC

    available_at = timezone.now() + timedelta(seconds=delay_seconds)
    existing = (
        Directive.objects.filter(
            topic=COURIER_SYNC,
            payload__order_ref=order.ref,
            status=Directive.Status.QUEUED,
        )
        .order_by("available_at", "id")
        .first()
    )
    if existing:
        existing.available_at = available_at
        existing.save(update_fields=["available_at", "updated_at"])
        return
    Directive.objects.create(
        topic=COURIER_SYNC,
        payload={"order_ref": order.ref},
        available_at=available_at,
    )
