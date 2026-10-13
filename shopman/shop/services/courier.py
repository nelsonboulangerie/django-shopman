"""Courier — despacho de entregadores via logística externa (Machine).

Funil único da corrida: o despacho (Directive ``courier.dispatch``) e as duas
vias de status (webhook push + polling ``courier.sync``) convergem em
:func:`apply_status`, que grava ``Order.data["courier"]`` (schema em
docs/reference/data-schemas.md), espelha na timeline do pedido e emite SSE.

Transições de pedido derivadas do status da corrida:
  E (coletou)   → advance_order  → DISPATCHED → notificação "saiu para entrega"
                  (também com cobrança na porta, que foi na observação da corrida)
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


def house_dispatches(order) -> bool:
    """A casa pode chamar entregador para este pedido? Falha fechado.

    Só quando a entrega é compromisso da casa
    (:func:`order_helpers.delivery_ownership` == ``"house"``). Entrega do
    marketplace (iFood com ``delivered_by=IFOOD``) já tem entregador vindo pelo
    app dele; responsável não informado é falta de prova, e falta de prova não
    abre corrida paga. Pedido do canal iFood sem o bloco ``data["ifood"]``
    também fica de fora: o canal é de marketplace, e só o ``MERCHANT`` explícito
    diz que quem leva é a casa.
    """
    from shopman.shop.services.order_helpers import delivery_ownership

    if delivery_ownership(order) != "house":
        return False
    if (order.channel_ref or "") == "ifood":
        facts = (order.data or {}).get("ifood")
        return isinstance(facts, dict) and str(facts.get("delivered_by") or "").strip().upper() == "MERCHANT"
    return True


def not_house_dispatch_message(order) -> str:
    """Por que este pedido não aceita entregador da casa, em palavras do operador."""
    from shopman.shop.services.order_helpers import delivery_ownership

    if delivery_ownership(order) == "marketplace":
        return "Quem entrega este pedido é o iFood. O entregador vem pelo app do iFood."
    return "O iFood não informou quem entrega este pedido. Chamar entregador vale só para entrega da casa."


def is_enabled_for(order) -> bool:
    """Adapter configurado + entrega da casa. (O "auto" por canal é gate do lifecycle.)"""
    return (
        get_adapter("courier") is not None
        and get_fulfillment_type(order) == "delivery"
        and house_dispatches(order)
    )


# ── Cobrança na porta ───────────────────────────────────────────────


def door_charge(order) -> dict:
    """O que o entregador da TaOn cobra na porta, em centavos.

    ``{"cash_q", "change_for_q", "card_q"}``: a parcela em dinheiro, com quanto o
    cliente disse que paga (zero quando não pediu troco ou pediu abaixo da
    parcela) e a parcela no cartão. Tudo zero quando o pagamento já entrou.
    A casa não tem entregador próprio (decisão do dono, 13/10/2026): toda
    cobrança na porta sai com a corrida, e é esta a régua que vai na observação.
    """
    from shopman.shop.services import operator_orders

    payment = (order.data or {}).get("payment") or {}
    if payment.get("cod_settled_at"):
        return {"cash_q": 0, "change_for_q": 0, "card_q": 0}
    cash_q = operator_orders.cash_due_on_delivery_q(order)
    change_for_q = operator_orders._change_for_q(order) if cash_q > 0 else 0
    return {
        "cash_q": cash_q,
        "change_for_q": change_for_q if change_for_q > cash_q else 0,
        "card_q": operator_orders.card_due_on_delivery_q(order),
    }


def door_charge_note(order) -> str:
    """A observação da corrida: o pedido e a cobrança na porta, numa linha.

    ``Pedido A47 · Cobrar R$ 58,00 em dinheiro · troco para R$ 100,00``,
    ``Pedido A47 · Cobrar R$ 58,00 no cartão (maquininha)`` ou
    ``Pedido A47 · Pago, não cobrar``. O entregador lê no celular, na porta.
    """
    from shopman.utils.monetary import format_money

    from shopman.shop.services.operator_orders import short_ref

    charge = door_charge(order)
    parts = [f"Pedido {short_ref(order.ref)}"]
    if charge["cash_q"] > 0:
        parts.append(f"Cobrar R$ {format_money(charge['cash_q'])} em dinheiro")
        parts.append(
            f"troco para R$ {format_money(charge['change_for_q'])}" if charge["change_for_q"] else "sem troco"
        )
    if charge["card_q"] > 0:
        parts.append(f"Cobrar R$ {format_money(charge['card_q'])} no cartão (maquininha)")
    if len(parts) == 1:
        parts.append("Pago, não cobrar")
    return " · ".join(parts)


# ── Payload Machine ─────────────────────────────────────────────────


def build_machine_payload(order) -> dict:
    """Corpo do POST /abrirSolicitacao a partir do pedido + Shop (partida)."""
    from django.conf import settings

    from shopman.shop.models import Shop
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    handoff = build_dispatch_payload(order)  # NotDeliverableError p/ não-delivery
    shop = Shop.load()
    if shop is None:
        raise ValueError("Loja não configurada: impossível montar a partida da corrida.")
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
        "observacao_parada": door_charge_note(order),
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
    base_revision = dispatch_revision(order) if store else None
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
        from shopman.shop.services.dispatch_handoff import build_dispatch_payload

        handoff = build_dispatch_payload(order)
        pickup = {
            "lat": str(shop.latitude),
            "lng": str(shop.longitude),
            "street": " ".join(p for p in (shop.route, shop.street_number) if p).strip()
            or shop.formatted_address,
            "neighborhood": shop.neighborhood,
            "city": shop.city,
            "state": shop.state_code,
        }
        dropoff = {
            "lat": str(lat),
            "lng": str(lng),
            "street": " ".join(p for p in (handoff["route"], handoff["street_number"]) if p).strip()
            or handoff["formatted_address"],
            "neighborhood": handoff["neighborhood"],
            "city": handoff["city"],
            "state": handoff["state_code"],
        }
        try:
            result = adapter.estimate(pickup=pickup, dropoff=dropoff)
        except CourierError as exc:
            logger.warning("courier.estimate_failed order=%s: %s", order.ref, exc)
            return None
        if result is None:
            return None
        estimate = {"value_q": result.value_q, "minutes": result.minutes, "km": result.km}
        cache.set(cache_key, estimate, ESTIMATE_CACHE_SECONDS)

    if store:
        store_estimate(order, estimate, expected_revision=base_revision)
    return estimate


def can_quote(order) -> bool:
    return is_enabled_for(order) and not has_active_ride(order) and order.status not in {Order.Status.CANCELLED, Order.Status.COMPLETED}


@transaction.atomic
def store_estimate(order, estimate, *, expected_revision, require_quotable=False):
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou o destino mudou durante a cotação. Confira antes de cotar novamente.")
    if require_quotable and not can_quote(order):
        raise OrderStateConflict("Confira o estado do pedido e da corrida antes de cotar.")
    block = dict(get_block(order))
    block["estimate"] = {key: estimate[key] for key in ("value_q", "minutes", "km")}
    _save_block(order, block, emit={"kind": "estimate"})


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
    if not house_dispatches(order):
        raise ValueError(not_house_dispatch_message(order))
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


@transaction.atomic
def release_unresolved_dispatch(order, *, actor: str, expected_revision: str | None = None) -> Directive:
    """"Chamar de novo": a última chamada ficou sem resposta da TaOn.

    O despacho sem resultado confirmado trava qualquer outra chamada (não se
    sabe se a corrida abriu lá). Quem conferiu na central e não achou a corrida
    libera aqui: a tentativa pendente vira ``released`` (com quem e quando, na
    própria Directive e na timeline do pedido) e uma chamada nova é enfileirada
    no mesmo gesto. A tentativa liberada nunca mais chama a TaOn.
    """
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if expected_revision is not None and dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou a corrida mudou. Confira o contexto antes de chamar de novo.")
    pending = unresolved_dispatch(order)
    if pending is None:
        raise ValueError("Não há chamada sem resposta para liberar. Atualize o pedido.")
    task = Directive.objects.select_for_update().get(pk=pending.pk)
    payload = dict(task.payload or {})
    receipt = dict(payload.get("dispatch_attempt") or {})
    previous = receipt.get("state", "")
    now_iso = timezone.now().isoformat()
    receipt.update(state="released", released_from=previous, released_by=actor, released_at=now_iso, updated_at=now_iso)
    payload["dispatch_attempt"] = receipt
    task.payload = payload
    task.save(update_fields=["payload", "updated_at"])
    order.emit_event(event_type="courier_dispatch_released", actor=actor,
                     payload={"directive_id": task.pk, "previous_state": previous})
    logger.info("courier.dispatch_released order=%s directive=%s actor=%s", order.ref, task.pk, actor)
    return redispatch(order, actor=actor)


def latest_cancellation(order, *, pending_only=False):
    """The existing Directive owns queued and unresolved cancellation attempts."""
    from django.db.models import Q

    from shopman.shop.directives import COURIER_CANCEL

    ride = get_block(order).get("id_mch")
    if not ride:
        return None
    tasks = Directive.objects.filter(topic=COURIER_CANCEL, payload__order_ref=order.ref, payload__courier_ref=ride)
    if pending_only:
        tasks = tasks.filter(Q(status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING)) |
            Q(payload__cancel_attempt__state__in=("started", "unknown", "accepted")))
    return tasks.order_by("-pk").first()


@transaction.atomic
def cancel_ride(order, *, actor: str, reason_id: int | None = None, expected_revision: str | None = None) -> Directive:
    """Record a request for the observed ride; the worker owns remote I/O."""
    from shopman.shop.directives import COURIER_CANCEL, create_deduped
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if expected_revision is not None and dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou a corrida mudou. Confira antes de solicitar cancelamento.")
    if get_adapter("courier") is None:
        raise ValueError("Nenhum adapter de courier configurado.")
    block = get_block(order)
    if not has_active_ride(order):
        raise ValueError("Não há corrida ativa para cancelar.")
    if block.get("status") not in CANCELLABLE_STATUSES:
        raise ValueError("A corrida já está com o entregador em rota. Combine o retorno por telefone com a central.")
    existing = latest_cancellation(order, pending_only=True)
    if existing is not None:
        state = (existing.payload or {}).get("cancel_attempt", {}).get("state")
        if state in {"started", "unknown", "accepted"}:
            raise OrderStateConflict("Cancelamento já iniciado. Confira o resultado na central antes de outra solicitação.")
        return existing
    task = create_deduped(COURIER_CANCEL,
        payload={"order_ref": order.ref, "channel_ref": order.channel_ref or "", "actor": actor,
            "courier_ref": block["id_mch"], "reason_id": reason_id},
        dedupe_key=f"courier.cancel:{order.ref}:{block['id_mch']}")
    if task is None:
        raise OrderStateConflict("Já existe uma solicitação de cancelamento para esta corrida. Atualize o pedido.")
    order.emit_event(event_type="courier_cancel_requested", actor=actor, payload={"directive_id": task.pk, "id_mch": block["id_mch"]})
    _emit_sse(order, {"kind": "cancel_queued"})
    return task


#: O aviso que o cancelamento do pedido deixa quando a corrida não volta sozinha.
#: Tipo existente (sem migração) e fora da resolução automática por status do
#: pedido: só sai quando o operador resolve com a central.
_CANCELLED_ORDER_ALERT_TYPE = "integration_failed"


def on_order_cancelled(order) -> None:
    """Pedido cancelado: a corrida dele não pode seguir aberta na central.

    - Antes da coleta (``CANCELLABLE_STATUSES``): enfileira o cancelamento da
      corrida pelo caminho de sempre (:func:`cancel_ride`, Directive
      ``courier.cancel``, dedupe por corrida). Cancelamento já pedido é no-op.
    - Depois da coleta (``E``): a central não cancela mais. Aviso crítico ao
      operador, uma vez por pedido.
    - Despacho sem resultado confirmado: pode haver corrida na central que o
      pedido não conhece. Mesmo aviso, porque a conferência é a mesma.

    Nunca levanta: o cancelamento do pedido não depende da central.
    """
    from shopman.shop.services.operator_orders import OrderStateConflict, short_ref

    code = short_ref(order.ref)
    try:
        block = get_block(order)
        status = str(block.get("status") or "")
        if not has_active_ride(order):
            if unresolved_dispatch(order) is not None:
                _alert_cancelled_order(order, f"O pedido {code} foi cancelado com um pedido de entregador sem "
                    "resultado confirmado: confira na central e cancele a corrida, se ela existir.")
            return
        if status == "E":
            _alert_cancelled_order(order, f"O entregador já coletou o pedido {code}, que foi cancelado: fale com a central.")
            return
        if status in CANCELLABLE_STATUSES:
            try:
                cancel_ride(order, actor="lifecycle.on_cancelled")
            except OrderStateConflict:  # silêncio-deliberado: cancelamento desta corrida já pedido, o worker cuida dele
                pass
            except ValueError:
                _alert_cancelled_order(order, f"O pedido {code} foi cancelado e a corrida segue aberta na central: "
                    "cancele a corrida por lá.")
            return
        _alert_cancelled_order(order, f"O pedido {code} foi cancelado e a corrida segue aberta na central: "
            "cancele a corrida por lá.")
    except Exception:
        logger.exception("courier.on_order_cancelled_failed order=%s", order.ref)


def _alert_cancelled_order(order, message: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    if alert_adapter.recent_exists(_CANCELLED_ORDER_ALERT_TYPE, None, order_ref=order.ref, message_contains="foi cancelado"):
        return
    alert_adapter.create(_CANCELLED_ORDER_ALERT_TYPE, "critical", message, order_ref=order.ref)


def _archive_current_ride(block: dict) -> None:
    """Move a corrida corrente para o histórico ``attempts``."""
    attempts = list(block.get("attempts") or [])
    attempts.append(
        {
            "id_mch": block.get("id_mch", ""),
            "status": block.get("status", ""),
            "requested_at": block.get("requested_at", ""),
            "status_at": dict(block.get("status_at") or {}),
            "ended_at": timezone.now().isoformat(),
        }
    )
    block["attempts"] = attempts
    for key in ("id_mch", "status", "status_at", "dispatched_at", "finished_at", "driver",
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
            # Cada letra com a hora em que chegou pela primeira vez (A aceita, S em
            # espera, E coletou, F finalizou): o B.I. mede daqui o tempo de chegada do
            # entregador. ``last_event_at`` só guarda a última.
            status_at = dict(block.get("status_at") or {})
            status_at.setdefault(status, now_iso)
            block["status_at"] = status_at
            if status == "E":
                block.setdefault("dispatched_at", now_iso)
                # A cobrança que saiu com o entregador da TaOn, registrada na coleta.
                block.setdefault("door_charge", door_charge(order))
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
        # Uma corrida viva (a de agora, ou a nova depois da que falhou): os
        # avisos de corrida que não abriu, não foi aceita ou foi cancelada
        # deixam de ser verdade.
        from shopman.shop.handlers.alert_resolution import COURIER_TYPES, resolve_on_commit

        resolve_on_commit(order.ref, COURIER_TYPES, actor=f"courier:{status}")
        recover_local_status(order, ride_id=ride_id)
        if status == "E" and order.status == Order.Status.CANCELLED:
            # Coleta que chegou depois do cancelamento (a corrida não cancelou
            # a tempo): o mesmo aviso de "já coletou", uma vez por pedido.
            on_order_cancelled(order)


def recover_local_status(order, *, ride_id: str) -> None:
    """Reconcile only the known ride's due local transitions, without provider I/O."""
    from shopman.shop.services import operator_orders

    order.refresh_from_db()
    block = get_block(order)
    if block.get("id_mch") != ride_id:
        return
    status = block.get("status")
    if status in ("E", "F") and order.status == Order.Status.READY:
        # A coleta despacha também com cobrança na porta (decisão do dono,
        # 13/10/2026): a cobrança foi na observação e fica em ``door_charge``.
        # Se a casa despachou antes no Gestor, com troco ou maquininha, o
        # pedido já não está pronto e nada aqui roda.
        operator_orders.advance_order(
            order, actor="courier:machine", target_status=Order.Status.DISPATCHED,
            expected_courier_id=ride_id, partner_collects=True,
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
            f"Nenhum entregador da TaOn aceitou a corrida do pedido {order.ref}. "
            "Abra o pedido e chame o entregador de novo.",
        )
    else:
        alert_type, message = (
            "courier_ride_cancelled",
            f"A TaOn cancelou a corrida do pedido {order.ref}. "
            "Abra o pedido e chame o entregador de novo.",
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
