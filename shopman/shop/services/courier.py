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

from shopman.shop.adapters.courier_machine import (
    BEFORE_ACCEPT_STATUSES,
    CANCEL_INTENT_OPERATOR,
    CANCEL_INTENT_ORDER_CANCELLED,
    CANCEL_REASONS_AFTER_ACCEPT,
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    CourierError,
)
from shopman.shop.services import delivery_services
from shopman.shop.services.order_helpers import get_commitment_date, get_fulfillment_type, merge_order_data

logger = logging.getLogger(__name__)

#: Segundos até o primeiro poll de status após abrir a corrida.
FIRST_SYNC_SECONDS = 45

#: TTL do cache de cotação (a origem é fixa — a loja; o destino define a chave).
ESTIMATE_CACHE_SECONDS = 600

#: Intervalo default de polling quando Shop.defaults não configura.
DEFAULT_POLL_SECONDS = 60

#: Em que estados do pedido a casa pode chamar o entregador: desde o aceite.
#: Quem chama é o operador, conscientemente, e só ele sabe se a sacola já está
#: pronta (decisão do dono, 13/10/2026): a entrega da casa se despacha na hora,
#: sem esperar o "pronto" do sistema. O lembrete do Gestor (``courier_reminder``)
#: cobra a chamada durante o preparo (WP-ENTREGADOR-CHAMADA-ANTECIPADA).
RIDE_ORDER_STATUSES = frozenset({
    Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY, Order.Status.DISPATCHED,
})

#: Chamada antes do pronto: a coleta (``E``) leva o pedido pelos degraus que
#: faltam até a saída, porque a sacola foi com o entregador.
_BEFORE_READY_STATUSES = frozenset({Order.Status.ACCEPTED, Order.Status.PREPARING})


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
    """Corrida ativa = ride_ref presente e status não-terminal."""
    block = get_block(order)
    return bool(block.get("ride_ref")) and block.get("status") not in TERMINAL_STATUSES


def ride_cancellable(block: dict) -> bool:
    """A corrida deste bloco ainda pode ser cancelada pela casa? Régua única.

    Antes da coleta: corrida aberta na central (``ride_ref``), numa letra que a
    central cancela (``CANCELLABLE_STATUSES``) e SEM a marca da coleta
    (``dispatched_at``). A marca é o fato: se uma letra atrasada devolver o
    status a "aceita" com a sacola já na moto, o cancelar não reaparece. É a
    mesma pergunta nas quatro portas (a projeção do pedido, a das Entregas, o
    pedido de cancelamento e o worker que chama a central).
    """
    return (
        bool(block.get("ride_ref"))
        and block.get("status") in CANCELLABLE_STATUSES
        and not block.get("dispatched_at")
    )


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
        delivery_services.courier_backend() is not None
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
    change_for_q = operator_orders.change_for_q(order) if cash_q > 0 else 0
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


def needs_return(order) -> bool:
    """A corrida volta à loja: o entregador traz o que cobrou ou levou.

    Cobrança na porta (dinheiro, com troco ou sem, e cartão na maquininha) ou
    maquininha que saiu com ele: o entregador nunca fica com dinheiro nem com a
    maquininha da casa, então a corrida pede ``retorno`` à TaOn. Pedido pago e
    sem nada da casa vai só de ida. O retorno é custo da casa e não muda o que
    o cliente paga (o frete segue nas faixas e zonas).
    """
    charge = door_charge(order)
    if charge["cash_q"] > 0 or charge["card_q"] > 0:
        return True
    dispatch = (order.data or {}).get("dispatch") or {}
    return bool(dispatch.get("equipment"))


def ride_note(body: dict, order_ref: str | None = None) -> str:
    """A observação que um corpo de ``/abrirSolicitacao`` leva ao entregador.

    ``order_ref``: a da parada daquele pedido (corrida com várias paradas);
    sem ele, a da primeira parada.
    """
    stops = body.get("paradas") if isinstance(body, dict) else None
    stops = [stop for stop in stops if isinstance(stop, dict)] if isinstance(stops, list) else []
    if order_ref is not None:
        stops = [stop for stop in stops if stop.get("id_externo") == order_ref]
    stop = stops[0] if stops else {}
    return str(stop.get("observacao_parada") or "")


def _charge_part(note: str) -> str:
    """A observação sem o "Pedido A47 · " do começo: só a cobrança."""
    head, sep, rest = note.partition(" · ")
    return rest if sep and head.startswith("Pedido ") else note


def charge_outdated(order) -> dict | None:
    """A corrida aberta leva uma cobrança que o pedido já não diz.

    A TaOn não altera a observação de uma corrida aberta (a API só abre,
    consulta e cancela). Editar o pedido depois da chamada (itens, troco, forma
    de pagar, pagamento que entrou) muda o que o entregador deve cobrar, e a
    observação que ele lê no celular fica para trás. Compara a observação que
    foi (``courier.door_charge_note``, gravada na abertura) com a de agora.

    ``{"sent", "current", "collected"}`` (só a cobrança, sem o número do
    pedido), ou ``None`` quando bate, quando não há corrida ativa, ou quando a
    corrida não guardou o que levou.
    """
    if not has_active_ride(order):
        return None
    block = get_block(order)
    sent = str(block.get("door_charge_note") or "")
    if not sent:
        return None
    current = door_charge_note(order)
    if sent == current:
        return None
    return {
        "sent": _charge_part(sent),
        "current": _charge_part(current),
        "collected": not ride_cancellable(block),
    }


# ── Payload Machine ─────────────────────────────────────────────────


def _stop(order, handoff: dict) -> dict:
    """A parada de um pedido: endereço, cliente e a cobrança na porta."""
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
    return parada


def _route(origin: tuple[float, float] | None, stops: list[tuple[dict, dict]]) -> list[tuple[dict, dict]]:
    """As paradas na ordem do percurso: a mais perto de onde o entregador está, depois a seguinte.

    A API da TaOn não ordena as paradas; o entregador segue a ordem enviada.
    Vizinho mais próximo (distância plana em graus, que na escala de uma cidade
    ordena igual à de verdade), a partir da loja. Parada sem coordenada vai ao
    fim, na ordem em que chegou.
    """
    located = [stop for stop in stops if stop[1]["latitude"] is not None and stop[1]["longitude"] is not None]
    rest = [stop for stop in stops if stop not in located]
    if origin is None:
        return stops
    route, here = [], origin
    while located:
        nearest = min(located, key=lambda stop: (float(stop[1]["latitude"]) - here[0]) ** 2
                      + (float(stop[1]["longitude"]) - here[1]) ** 2)
        located.remove(nearest)
        route.append(nearest)
        here = (float(nearest[1]["latitude"]), float(nearest[1]["longitude"]))
    return route + rest


def build_machine_payload(*orders) -> dict:
    """Corpo do POST /abrirSolicitacao: a loja na partida e uma parada por pedido.

    Um pedido é uma corrida de uma parada. Vários pedidos (:func:`request_group_dispatch`)
    viram UMA corrida, com as paradas na ordem do percurso (:func:`_route`) e
    ``retorno`` se qualquer parada traz algo de volta (:func:`needs_return`).
    """
    from django.conf import settings

    from shopman.shop.models import Shop
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    if not orders:
        raise ValueError("Nenhum pedido para a corrida.")
    # NotDeliverableError p/ não-delivery
    handoffs = [(order, build_dispatch_payload(order)) for order in orders]
    shop = Shop.load()
    if shop is None:
        raise ValueError("Loja não configurada: impossível montar a partida da corrida.")
    cfg = getattr(settings, "SHOPMAN_MACHINE", {}) or {}

    pickup_street = " ".join(
        p for p in (shop.route, shop.street_number) if p
    ).strip() or shop.formatted_address

    partida = {
        "endereco": pickup_street,
        "bairro": shop.neighborhood,
        "cidade": shop.city,
        "estado": shop.state_code,
    }
    origin = None
    if shop.latitude is not None and shop.longitude is not None:
        partida["lat"] = str(shop.latitude)
        partida["lng"] = str(shop.longitude)
        origin = (float(shop.latitude), float(shop.longitude))

    route = _route(origin, handoffs) if len(handoffs) > 1 else handoffs
    return {
        "forma_pagamento": str(cfg.get("forma_pagamento") or "F"),
        "partida": partida,
        "paradas": [_stop(order, handoff) for order, handoff in route],
        "retorno": any(needs_return(order) for order in orders),
    }


# ── Cotação ─────────────────────────────────────────────────────────


def _shop_point(shop) -> dict:
    """A loja como ponto da cotação: coordenada e o endereço que a API exige."""
    return {
        "lat": str(shop.latitude),
        "lng": str(shop.longitude),
        "street": " ".join(p for p in (shop.route, shop.street_number) if p).strip() or shop.formatted_address,
        "neighborhood": shop.neighborhood,
        "city": shop.city,
        "state": shop.state_code,
    }


def _handoff_point(handoff: dict) -> dict:
    """Um endereço de entrega como ponto da cotação."""
    return {
        "lat": str(handoff["latitude"]),
        "lng": str(handoff["longitude"]),
        "street": " ".join(p for p in (handoff["route"], handoff["street_number"]) if p).strip()
        or handoff["formatted_address"],
        "neighborhood": handoff["neighborhood"],
        "city": handoff["city"],
        "state": handoff["state_code"],
    }


def estimate_for_ride(orders) -> dict | None:
    """Cotação de UMA corrida com várias paradas, antes de chamar.

    A mesma corrida que :func:`build_machine_payload` vai abrir: as paradas na
    ordem do percurso (:func:`_route`), a última como destino e as outras em
    ``stops``, e o retorno se qualquer pedido traz algo de volta. Custo interno
    (o frete dos clientes não muda). Best-effort: sem adapter, loja ou pedido
    sem coordenada, ou a TaOn fora → None. Cache de 10 min pelo percurso.
    ``stops`` no resultado é a ordem das paradas (refs), para a tela dizer.
    """
    from shopman.shop.models import Shop
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    adapter = delivery_services.courier_backend()
    shop = Shop.load()
    if adapter is None or shop is None or None in (shop.latitude, shop.longitude) or len(orders) < 2:
        return None
    if any(get_fulfillment_type(order) != "delivery" for order in orders):
        return None
    handoffs = [(order, build_dispatch_payload(order)) for order in orders]
    if any(handoff["latitude"] is None or handoff["longitude"] is None for _, handoff in handoffs):
        return None
    route = _route((float(shop.latitude), float(shop.longitude)), handoffs)
    with_return = any(needs_return(order) for order in orders)
    path = ":".join(f"{float(h['latitude']):.4f},{float(h['longitude']):.4f}" for _, h in route)
    cache_key = f"courier:est-ride:{path}:{'r' if with_return else 'i'}"
    estimate = cache.get(cache_key)
    if estimate is None:
        points = [_handoff_point(handoff) for _, handoff in route]
        try:
            result = adapter.estimate(pickup=_shop_point(shop), dropoff=points[-1], with_return=with_return,
                                      stops=points[:-1])
        except CourierError as exc:
            logger.warning("courier.estimate_ride_failed orders=%s: %s", ",".join(o.ref for o in orders), exc)
            return None
        if result is None:
            return None
        estimate = {"value_q": result.value_q, "minutes": result.minutes, "km": result.km,
                    "with_return": with_return}
        cache.set(cache_key, estimate, ESTIMATE_CACHE_SECONDS)
    return {**estimate, "stops": [order.ref for order, _ in route]}


def estimate_for_order(order) -> dict | None:
    """Cotação da corrida (custo interno; o preço ao cliente segue nas faixas/zonas). Só lê.

    Best-effort: sem adapter, sem coordenadas ou com a Machine fora → None.
    Cota com o mesmo retorno que a abertura vai pedir (:func:`needs_return`).
    Cache de 10 min por destino e retorno (a origem é sempre a loja). Quem grava
    (o despacho) toma a revisão ANTES de cotar e chama :func:`store_estimate`:
    um GET que cota nunca escreve no pedido.
    """
    adapter = delivery_services.courier_backend()
    if adapter is None or get_fulfillment_type(order) != "delivery":
        return None

    from shopman.shop.models import Shop

    shop = Shop.load()
    structured = (order.data or {}).get("delivery_address_structured") or {}
    lat, lng = structured.get("latitude"), structured.get("longitude")
    if shop is None or None in (shop.latitude, shop.longitude, lat, lng):
        return None

    with_return = needs_return(order)
    cache_key = f"courier:est:{float(lat):.4f}:{float(lng):.4f}:{'r' if with_return else 'i'}"
    estimate = cache.get(cache_key)
    if estimate is None:
        from shopman.shop.services.dispatch_handoff import build_dispatch_payload

        handoff = build_dispatch_payload(order)
        try:
            result = adapter.estimate(pickup=_shop_point(shop), dropoff=_handoff_point(handoff), with_return=with_return)
        except CourierError as exc:
            logger.warning("courier.estimate_failed order=%s: %s", order.ref, exc)
            return None
        if result is None:
            return None
        estimate = {"value_q": result.value_q, "minutes": result.minutes, "km": result.km,
                    "with_return": with_return}
        cache.set(cache_key, estimate, ESTIMATE_CACHE_SECONDS)
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
    block["estimate"] = {key: estimate[key] for key in ("value_q", "minutes", "km", "with_return", "stops")
                         if key in estimate}
    _save_block(order, block, emit={"kind": "estimate"})


# ── Despacho ────────────────────────────────────────────────────────


def dispatch_task_filter(order_ref: str):
    """As tarefas de despacho deste pedido: a dele e as das corridas em que ele é parada.

    A corrida com várias paradas é UMA tarefa (``payload.order_ref`` é o primeiro
    pedido); os outros moram em ``payload.ride_members`` (``{ref: true}``, chave
    consultável em qualquer banco).
    """
    from django.db.models import Q

    return Q(payload__order_ref=order_ref) | Q(payload__ride_members__has_key=order_ref)


def ride_orders(order) -> list[str]:
    """Os pedidos da corrida ativa deste pedido, na ordem das paradas (ele mesmo, se é corrida de um só)."""
    refs = get_block(order).get("ride_orders")
    return [str(ref) for ref in refs] if isinstance(refs, list) and refs else [order.ref]


def ride_companions(order, *, alive: bool = False) -> list:
    """Os OUTROS pedidos que estão na mesma corrida (mesmo ``ride_ref``).

    ``alive=True`` conta só quem ainda espera a entrega: pedido cancelado segue
    com o ``ride_ref`` no bloco (a corrida é dos outros), mas não é mais motivo
    para a corrida seguir aberta.
    """
    ride_id = get_block(order).get("ride_ref")
    others = [ref for ref in ride_orders(order) if ref != order.ref]
    if not ride_id or not others:
        return []
    return [other for other in Order.objects.filter(ref__in=others).order_by("pk")
            if get_block(other).get("ride_ref") == ride_id
            and not (alive and other.status == Order.Status.CANCELLED)]


def stranded_companions(order) -> tuple[str, list]:
    """Quem ficou preso na corrida que este pedido já encerrou.

    A corrida com várias paradas tem uma batida só, no primeiro pedido. Se só
    ele recebeu o fim (``N``/``C``), a corrida foi para o histórico dele
    (``attempts[-1]``) e os outros seguem "com corrida" para sempre, segurando
    letra, cor, troco e maquininha. Devolve a letra final e os pedidos que
    ainda carregam aquele ``ride_ref`` vivo; ``("", [])`` quando ninguém ficou.
    """
    attempts = get_block(order).get("attempts") or []
    last = attempts[-1] if attempts and isinstance(attempts[-1], dict) else {}
    ride_id, status = last.get("ride_ref"), str(last.get("status") or "")
    refs = [str(ref) for ref in last.get("ride_orders") or [] if ref != order.ref]
    if not ride_id or not refs or get_block(order).get("ride_ref") == ride_id:
        return "", []
    stuck = [other for other in Order.objects.filter(ref__in=refs).order_by("pk")
             if get_block(other).get("ride_ref") == ride_id
             and get_block(other).get("status") not in TERMINAL_STATUSES]
    return status, stuck


#: Recibos de despacho que ainda podem estar abertos lá (:func:`unresolved_dispatch`).
_RECEIPT_STATES = ("started", "unknown", "accepted")

#: A tarefa de despacho que ainda vai (ou está indo) à central.
_LIVE_TASK_STATUSES = (Directive.Status.QUEUED, Directive.Status.RUNNING)


def dispatch_tasks_for(orders) -> dict[str, list[Directive]]:
    """As tarefas de despacho de vários pedidos numa consulta só, por pedido.

    Só as que alguma leitura pergunta: as vivas (:func:`ride_is_live`) e as que têm
    recibo (:func:`unresolved_dispatch`). A tarefa da corrida de várias paradas
    entra em cada pedido dela (``payload.order_ref`` e ``payload.ride_members``).
    Quem lê uma lista de pedidos passa o resultado para essas duas funções, e a
    leitura deixa de fazer uma consulta por pedido.
    """
    from django.db.models import Q

    from shopman.shop.directives import COURIER_DISPATCH

    refs = [order.ref for order in orders]
    found: dict[str, list[Directive]] = {ref: [] for ref in refs}
    if not refs:
        return found
    tasks = Directive.objects.filter(
        Q(payload__order_ref__in=refs) | Q(payload__ride_members__has_any_keys=refs),
        Q(status__in=_LIVE_TASK_STATUSES) | Q(payload__dispatch_attempt__state__in=_RECEIPT_STATES),
        topic=COURIER_DISPATCH,
    ).order_by("-pk")
    for task in tasks:
        payload = task.payload or {}
        members = payload.get("ride_members") if isinstance(payload.get("ride_members"), dict) else {}
        for ref in {str(payload.get("order_ref") or ""), *members}:
            if ref in found:
                found[ref].append(task)
    return found


def unresolved_dispatch(order, *, exclude_pk=None, tasks: dict[str, list[Directive]] | None = None):
    """Pure receipt read. Unknown/start never authorizes another provider POST.

    ``tasks``: as tarefas já lidas em lote (:func:`dispatch_tasks_for`).
    """
    from shopman.shop.directives import COURIER_DISPATCH

    if tasks is None:
        candidates = Directive.objects.filter(dispatch_task_filter(order.ref), topic=COURIER_DISPATCH,
            payload__dispatch_attempt__state__in=list(_RECEIPT_STATES))
        if exclude_pk is not None:
            candidates = candidates.exclude(pk=exclude_pk)
        candidates = candidates.order_by("-pk")
    else:
        candidates = [
            task for task in tasks.get(order.ref, [])
            if ((task.payload or {}).get("dispatch_attempt") or {}).get("state") in _RECEIPT_STATES
            and task.pk != exclude_pk
        ]
    block = get_block(order)
    known = {block.get("ride_ref"), *[attempt.get("ride_ref") for attempt in block.get("attempts", [])]}
    for task in candidates:
        receipt = (task.payload or {}).get("dispatch_attempt", {})
        if receipt.get("state") == "accepted" and receipt.get("courier_ref") in known:
            continue
        return task
    return None


def ensure_dispatch_resolved(order) -> None:
    if unresolved_dispatch(order) is not None:
        raise ValueError("Há um despacho sem resultado confirmado. Confira a solicitação na central antes de abrir outra corrida.")


def request_dispatch(order, *, actor: str, ride_number: int | None = None) -> Directive | None:
    """Enfileira o despacho da corrida (Directive ``courier.dispatch``).

    No-op quando: adapter ausente, pedido não é entrega, corrida ativa em
    andamento, ou já existe directive de despacho na fila (idempotente).
    ``ride_number``: o número que a tela mostrava para esta corrida; vale se
    ainda estiver livre (:func:`next_ride_number`).
    """
    from shopman.shop.directives import COURIER_DISPATCH

    ensure_dispatch_resolved(order)
    if not is_enabled_for(order):
        return None
    if order.status not in RIDE_ORDER_STATUSES:
        return None
    if not_today_refusal(order):
        # A encomenda de outro dia que ficou pronta antes: o lifecycle não chama;
        # a chamada manual recusa com a frase (``redispatch``).
        return None
    if has_active_ride(order):
        return None

    existing = Directive.objects.filter(
        dispatch_task_filter(order.ref),
        topic=COURIER_DISPATCH,
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
    with transaction.atomic():
        # O pedido antes da trava dos números, na mesma ordem da corrida em
        # grupo: quem segura a trava nunca espera por linha de pedido.
        Order.objects.select_for_update().get(pk=order.pk)
        fields = {"ride_number": next_ride_number(exclude_refs=[order.ref], prefer=ride_number)}
        if not get_block(order).get("called_at"):
            # A primeira chamada do pedido, com quem chamou: encerra o lembrete do
            # Gestor (``backstage.services.courier_reminder``) e é o marco "chamada
            # pedida" que a chamada antecipada vai aprender.
            fields.update(called_at=timezone.now().isoformat(), called_by=actor)
        merge_order_data(order, fields, block="courier")
    order.emit_event(event_type="courier_dispatch_requested", actor=actor)
    logger.info("courier.dispatch_requested order=%s actor=%s", order.ref, actor)
    return directive


# ── Número da corrida: a letra e a cor dela na tela ─────────────────

#: Quantas cores a tela tem para as corridas vivas (``ridePalette.ts`` do Gestor).
#: A cor repete a cada seis corridas; a letra desfaz a dúvida.
RIDE_NUMBERS = 6

#: Quantas corridas vivas têm nome próprio: uma letra cada, de A a Z.
RIDE_LETTERS = 26

#: Chave do advisory lock que serializa a escolha do número da corrida.
_RIDE_NUMBER_LOCK = 0x52494445  # "RIDE"


def ride_is_live(order, *, tasks: dict[str, list[Directive]] | None = None) -> bool:
    """A corrida deste pedido ainda ocupa uma letra (e uma cor) na tela.

    Viva: chamada à espera da TaOn, corrida aberta ainda não terminada, ou
    terminada com o entregador ainda devendo voltar (troco, dinheiro, maquininha).
    ``tasks``: as tarefas de despacho já lidas em lote (:func:`dispatch_tasks_for`).
    """
    block = get_block(order)
    if not block.get("ride_number"):
        return False
    status = str(block.get("status") or "")
    if block.get("ride_ref"):
        if status not in TERMINAL_STATUSES:
            return True
        if status != "F":
            return False
        from shopman.shop.services import operator_orders

        return bool(operator_orders.courier_return_members(order))
    if tasks is not None:
        return any(task.status in _LIVE_TASK_STATUSES for task in tasks.get(order.ref, []))
    from shopman.shop.directives import COURIER_DISPATCH

    return Directive.objects.filter(
        dispatch_task_filter(order.ref), topic=COURIER_DISPATCH, status__in=_LIVE_TASK_STATUSES,
    ).exists()


def ride_letter(number) -> str:
    """A letra da corrida, como o operador a chama: 1 é A, 2 é B, 26 é Z.

    Corrida se nomeia por LETRA em toda tela e em toda mensagem (decisão do dono,
    16/11/2026); o número segue sendo o que se grava (``courier.ride_number``) e
    o que escolhe a cor. Sem número válido devolve vazio, e quem escreve a frase
    decide o que dizer sem a letra.
    """
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        return ""
    return chr(ord("A") + (number - 1) % 26)


def _live_ride_numbers(exclude_refs=()) -> dict[int, str]:
    """Os números ocupados por corridas vivas, cada um com a chamada mais antiga."""
    live: dict[int, str] = {}
    statuses = (*RIDE_ORDER_STATUSES, Order.Status.DISPATCHED, Order.Status.DELIVERED)
    orders = list(Order.objects.filter(status__in=statuses, data__courier__has_key="ride_number").exclude(ref__in=list(exclude_refs)))
    tasks = dispatch_tasks_for([order for order in orders if not get_block(order).get("ride_ref")])
    for order in orders:
        number = get_block(order).get("ride_number")
        if isinstance(number, int) and not isinstance(number, bool) and 1 <= number <= RIDE_LETTERS and ride_is_live(order, tasks=tasks):
            called = str(get_block(order).get("called_at") or "")
            live[number] = min(live.get(number, called), called)
    return live


def free_ride_numbers(*, exclude_refs=()) -> list[int]:
    """Os números livres agora, do menor ao maior (leitura, sem trava).

    É o que a tela usa para dar letra e cor à corrida que o operador ainda está
    juntando; quem grava é a chamada, por :func:`next_ride_number`.
    """
    live = _live_ride_numbers(exclude_refs)
    return [number for number in range(1, RIDE_LETTERS + 1) if number not in live]


def _lock_ride_numbers() -> None:
    """Uma escolha de número por vez, até o fim da transação de quem chama.

    Sem a trava, duas chamadas simultâneas (dois dispositivos, ou o operador e a
    chamada automática) liam o mesmo "menor livre" e duas corridas saíam com a
    mesma letra e a mesma cor. Advisory lock de transação: solta sozinho no
    commit ou no rollback. Fora do Postgres (banco de desenvolvimento em
    arquivo) a escrita já é uma por vez.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_RIDE_NUMBER_LOCK])


def next_ride_number(*, exclude_refs=(), prefer: int | None = None) -> int:
    """O número da corrida que está sendo chamada (1 a :data:`RIDE_LETTERS`).

    O número é a letra e a cor da corrida na tela e não muda enquanto ela vive:
    fica gravado no pedido (``Order.data["courier"]["ride_number"]``) na chamada.
    ``prefer`` é o número que a tela mostrava enquanto o operador juntava a
    corrida: vale se continuar livre; senão, o menor livre. Com as 26 letras
    ocupadas, repete a da corrida mais antiga.

    Chame dentro da transação que grava o número: a trava
    (:func:`_lock_ride_numbers`) só protege até o commit.
    """
    _lock_ride_numbers()
    live = _live_ride_numbers(exclude_refs)
    if isinstance(prefer, int) and not isinstance(prefer, bool) and 1 <= prefer <= RIDE_LETTERS and prefer not in live:
        return prefer
    for number in range(1, RIDE_LETTERS + 1):
        if number not in live:
            return number
    return min(live, key=lambda n: live[n])


#: Quantos pedidos cabem numa corrida. A API não publica teto; quatro é o que
#: um entregador de moto leva sem a última entrega esfriar.
MAX_RIDE_STOPS = 4


def not_today_refusal(order) -> str:
    """A encomenda é para outro dia: o entregador se chama no dia ("" quando é hoje).

    A régua única de "chamável hoje" (ENT-LIM-15): a lista Aguardando já não
    mostra a encomenda futura, e a chamada por API, a chamada em grupo e o
    lifecycle também não a chamam. Sem data combinada, é para hoje.
    """
    from shopman.shop.services.operator_orders import short_ref

    commitment = get_commitment_date(order)
    today = timezone.localdate()
    if commitment is None or commitment <= today:
        return ""
    day = f"amanhã, {commitment:%d/%m}" if commitment == today + timedelta(days=1) else f"{commitment:%d/%m}"
    return f"A encomenda {short_ref(order.ref)} é para {day}. O entregador se chama no dia."


def group_refusal(order, *, tasks: dict[str, list[Directive]] | None = None) -> str:
    """Por que este pedido não entra numa corrida com outros ("" quando entra).

    ``tasks``: as tarefas de despacho já lidas em lote (:func:`dispatch_tasks_for`).
    """
    from shopman.shop.services.operator_orders import short_ref

    code = short_ref(order.ref)
    if delivery_services.courier_backend() is None:
        return "Nenhuma central de entregas configurada."
    if get_fulfillment_type(order) != "delivery":
        return f"O pedido {code} não é entrega."
    if refusal := not_today_refusal(order):
        return refusal
    if not house_dispatches(order):
        return f"O pedido {code}: {not_house_dispatch_message(order)}"
    if order.status not in RIDE_ORDER_STATUSES or order.status == Order.Status.DISPATCHED:
        return f"O pedido {code} não está esperando entregador."
    if has_active_ride(order):
        return f"O pedido {code} já tem corrida."
    if unresolved_dispatch(order, tasks=tasks) is not None:
        return f"O pedido {code} tem uma chamada sem resposta da TaOn. Confira na central antes."
    return ""


class RideRevisionChanged(ValueError):
    """Um pedido da corrida mudou depois que a tela foi lida (``refs``: quais)."""

    def __init__(self, refs: list[str]):
        from shopman.shop.services.operator_orders import short_ref

        self.refs = list(refs)
        codes = [short_ref(ref) for ref in self.refs]
        if len(codes) == 1:
            message = f"O pedido {codes[0]} mudou depois que você abriu esta tela. Confira e chame de novo."
        else:
            message = f"Os pedidos {', '.join(codes[:-1])} e {codes[-1]} mudaram depois que você abriu esta tela. Confira e chame de novo."
        super().__init__(message)


class RideAlreadyCalled(ValueError):
    """Estes mesmos pedidos já estão na mesma corrida, chamada ou aberta.

    Não é recusa: quem pediu de novo (outro dispositivo, ou a tela que perdeu a
    resposta) queria esta corrida, e ela existe. ``ride_number`` é o dela.
    """

    def __init__(self, *, ride_number: int | None, directive_id: int | None = None):
        self.ride_number = ride_number
        self.directive_id = directive_id
        letter = ride_letter(ride_number)
        super().__init__(f"A corrida {letter} já tinha sido chamada." if letter else "Esta corrida já tinha sido chamada.")


def _same_ride_already_called(ordered) -> RideAlreadyCalled | None:
    """A corrida com EXATAMENTE estes pedidos já existe (na fila ou aberta)?"""
    from shopman.shop.directives import COURIER_DISPATCH

    refs = {order.ref for order in ordered}
    lead = ordered[0]
    number = get_block(lead).get("ride_number")
    number = number if isinstance(number, int) and not isinstance(number, bool) else None
    task = Directive.objects.filter(
        dispatch_task_filter(lead.ref), topic=COURIER_DISPATCH,
        status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
    ).order_by("-pk").first()
    if task is not None and set((task.payload or {}).get("order_refs") or []) == refs:
        return RideAlreadyCalled(ride_number=number, directive_id=task.pk)
    ride_id = get_block(lead).get("ride_ref")
    if ride_id and all(has_active_ride(order) and get_block(order).get("ride_ref") == ride_id
                       and set(ride_orders(order)) == refs for order in ordered):
        return RideAlreadyCalled(ride_number=number)
    return None


@transaction.atomic
def request_group_dispatch(orders, *, actor: str, expected_revisions: dict[str, str] | None = None,
                           ride_number: int | None = None) -> Directive:
    """Uma corrida para vários pedidos: uma solicitação na TaOn, uma parada por pedido.

    Junta entregas próximas e dilui o custo da casa (o frete do cliente não
    muda). Cada pedido entra só se pudesse ser chamado sozinho
    (:func:`group_refusal`). A custódia (troco da gaveta por pedido, uma
    maquininha para a corrida) é de quem chama, na mesma transação
    (``backstage.services.orders.courier_group_dispatch``). Uma tarefa
    ``courier.dispatch`` só, com ``ride_members``; a corrida aberta é gravada em
    cada pedido, com ``ride_orders`` na ordem das paradas.

    ``expected_revisions`` (``{ref: dispatch_revision}``) é o que a tela leu de
    cada pedido: conferido com os pedidos travados, ANTES de qualquer gravação.
    Endereço, pagamento ou corrida que mudou por outra porta recusa com
    :class:`RideRevisionChanged`, dizendo qual pedido. A corrida que já existe
    com estes mesmos pedidos levanta :class:`RideAlreadyCalled` (nada a fazer).
    ``ride_number``: o número que a tela mostrava; vale se continuar livre.
    """
    from shopman.shop.directives import COURIER_DISPATCH, create_deduped
    from shopman.shop.services.operator_orders import short_ref

    refs = list(dict.fromkeys(order.ref for order in orders))
    if len(refs) < 2:
        raise ValueError("Escolha pelo menos dois pedidos para juntar numa corrida.")
    if len(refs) > MAX_RIDE_STOPS:
        raise ValueError(f"Uma corrida leva até {MAX_RIDE_STOPS} pedidos.")
    locked = list(Order.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
    if len(locked) != len(refs):
        raise ValueError("Algum pedido não existe mais. Atualize a fila.")
    by_ref = {order.ref: order for order in locked}
    ordered = [by_ref[ref] for ref in refs]
    already = _same_ride_already_called(ordered)
    if already is not None:
        raise already
    if expected_revisions is not None:
        changed = [ref for ref in refs if expected_revisions.get(ref) != dispatch_revision(by_ref[ref])]
        if changed:
            raise RideRevisionChanged(changed)
    refusals = [reason for reason in (group_refusal(order) for order in ordered) if reason]
    if refusals:
        raise ValueError(" ".join(refusals))
    pending = Directive.objects.filter(
        topic=COURIER_DISPATCH, status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
    )
    for order in ordered:
        if pending.filter(dispatch_task_filter(order.ref)).exists():
            raise ValueError(f"O pedido {short_ref(order.ref)} já está sendo chamado. Atualize a fila.")

    lead = ordered[0]
    attempt_n = len(get_block(lead).get("attempts") or []) + 1
    directive = create_deduped(
        COURIER_DISPATCH,
        payload={"order_ref": lead.ref, "order_refs": refs, "ride_members": dict.fromkeys(refs, True),
                 "channel_ref": lead.channel_ref or "", "actor": actor},
        dedupe_key=f"courier.dispatch:{lead.ref}:{attempt_n}:{'+'.join(refs[1:])}",
    )
    if directive is None:
        raise ValueError("Esta corrida já foi pedida. Atualize a fila.")
    now_iso = timezone.now().isoformat()
    number = next_ride_number(exclude_refs=refs, prefer=ride_number)
    for order in ordered:
        block = dict(get_block(order))
        if block.get("ride_ref"):
            _archive_current_ride(block)
        block.pop("error", None)
        block["ride_number"] = number
        block.setdefault("called_at", now_iso)
        block.setdefault("called_by", actor)
        _save_block(order, block, emit={"kind": "redispatch"})
        order.emit_event(event_type="courier_dispatch_requested", actor=actor, payload={"ride_orders": refs})
    logger.info("courier.group_dispatch_requested orders=%s actor=%s", ",".join(refs), actor)
    return directive


def request_auto_dispatch(order) -> Directive | None:
    """A chamada automática do pronto (``fulfillment.courier="auto"``).

    Pedido que leva troco da gaveta ou a maquininha da casa não se chama
    sozinho: a maquininha só sai escolhida pelo operador (``delivery_devices``),
    e o troco sai do turno de quem chama. Sem isso a TaOn coletaria com a
    maquininha fora do registro, e o Gestor não saberia onde ela está. O
    operador recebe o aviso e chama pelo "Chamar entregador" do Gestor, que
    pergunta a custódia antes de abrir a corrida.
    """
    from shopman.shop.services.operator_orders import partner_custody_asks, short_ref

    if not is_enabled_for(order):
        return None
    asks = partner_custody_asks(order)
    if not asks["recorded"] and (asks["needs_machine"] or asks["change_out_suggested_q"] > 0):
        what = "a maquininha" if asks["needs_machine"] else "troco da gaveta"
        logger.info("courier.auto_dispatch_needs_custody order=%s", order.ref)
        from shopman.shop.adapters import alert as alert_adapter

        alert_adapter.create(
            "courier_dispatch_failed", "warning",
            f"O pedido {short_ref(order.ref)} está pronto e o entregador leva {what}: "
            "chame o entregador pelo Gestor para registrar o que sai com ele.",
            order_ref=order.ref,
        )
        return None
    return request_dispatch(order, actor="lifecycle.on_ready")


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
def redispatch(order, *, actor: str, expected_revision: str | None = None, ride_number: int | None = None) -> Directive:
    """Re-despacho manual pelo operador após corrida N/C ou erro terminal."""
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if expected_revision is not None and dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou a corrida mudou. Confira o contexto antes de despachar.")
    ensure_dispatch_resolved(order)
    if delivery_services.courier_backend() is None:
        raise ValueError("Nenhum adapter de courier configurado.")
    if get_fulfillment_type(order) != "delivery":
        raise ValueError("Re-despacho só se aplica a pedidos de entrega.")
    if not house_dispatches(order):
        raise ValueError(not_house_dispatch_message(order))
    if order.status not in RIDE_ORDER_STATUSES:
        raise ValueError("Chamar entregador só é possível depois de aceitar o pedido.")
    if has_active_ride(order):
        raise ValueError("Já existe uma corrida ativa para este pedido.")
    if refusal := not_today_refusal(order):
        raise ValueError(refusal)

    block = get_block(order)
    if block.get("ride_ref"):
        _archive_current_ride(block)
    block.pop("error", None)
    _save_block(order, block, emit={"kind": "redispatch"})

    directive = request_dispatch(order, actor=actor, ride_number=ride_number)
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
    refs = [str(ref) for ref in payload.get("order_refs") or []]
    if len(refs) > 1:
        # A corrida que ficou sem resposta levava vários pedidos: chama a MESMA
        # corrida de novo, com a custódia que já saiu (a mesma saída, a mesma
        # maquininha). Chamar só este pedido deixaria os outros sem entregador.
        by_ref = {other.ref: other for other in Order.objects.filter(ref__in=refs)}
        return request_group_dispatch([by_ref[ref] for ref in refs if ref in by_ref], actor=actor)
    return redispatch(order, actor=actor)


#: As duas saídas do "Encerrar aqui" (#2736): só o operador sabe o que aconteceu.
CLOSE_DELIVERED = "delivered"
CLOSE_RETURNED = "returned"


def close_here_outcomes(order) -> tuple[str, ...]:
    """As saídas que o "Encerrar aqui" oferece a esta corrida. Vazio quando não cabe.

    Só a corrida aberta além da idade em que uma corrida real dura
    (:func:`ride_open_too_long`): a central já não a encerra. "Voltou para a
    loja" só antes da coleta; depois dela o pedido saiu para entrega e não volta
    a pronto (a sacola que volta é outro fluxo, o da devolução).
    """
    from shopman.shop.protocols import RideState

    block = get_block(order)
    if not ride_open_too_long(block):
        return ()
    collected = bool(block.get("dispatched_at")) or delivery_services.ride_state(block) == RideState.ON_ROUTE
    return (CLOSE_DELIVERED,) if collected else (CLOSE_DELIVERED, CLOSE_RETURNED)


def close_here(order, *, outcome: str, actor: str, expected_revision: str | None = None) -> list[str]:
    """"Encerrar aqui": a casa encerra a corrida que a central nunca fechou.

    ``delivered`` ("Foi entregue") termina a corrida como o ``F`` da central: os
    pedidos ficam entregues, e o troco e a maquininha ficam pendentes no
    "Entregador voltou", como num fim normal. ``returned`` ("Voltou para a
    loja") termina como um cancelamento da casa: os pedidos voltam para
    Aguardando, e o troco e a maquininha voltam para a gaveta. Nas duas a letra
    fica livre. Nada vai à central: ela já não responde por esta corrida.

    Devolve os pedidos encerrados. Recusa o que mudou desde a leitura da tela
    (``expected_revision``) e a saída que esta corrida não oferece
    (:func:`close_here_outcomes`).
    """
    from shopman.shop.services.operator_orders import OrderStateConflict

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if expected_revision is not None and dispatch_revision(locked) != expected_revision:
            raise OrderStateConflict("O pedido ou a corrida mudou. Confira o contexto antes de encerrar.")
        if outcome not in close_here_outcomes(locked):
            raise ValueError("Esta corrida não se encerra assim agora. Atualize a tela.")
        ride_id = get_block(locked).get("ride_ref")
        members = [locked, *ride_companions(locked)]
        locked.emit_event(event_type="courier_closed_here", actor=actor,
                          payload={"ride_ref": ride_id, "outcome": outcome, "orders": [m.ref for m in members]})
    status = "F" if outcome == CLOSE_DELIVERED else "C"
    closed = []
    for member in members:
        if apply_status(member, status, source=f"operator:{actor}") in ("applied", "noop"):
            closed.append(member.ref)
    logger.info("courier.closed_here ride_ref=%s outcome=%s orders=%s actor=%s",
                ride_id, outcome, ",".join(closed), actor)
    return closed


def latest_cancellation(order, *, pending_only=False):
    """The existing Directive owns queued and unresolved cancellation attempts.

    O cancelamento é da CORRIDA (``courier_ref``), não do pedido: na corrida com
    várias paradas qualquer pedido dela enxerga a mesma solicitação.
    """
    from django.db.models import Q

    from shopman.shop.directives import COURIER_CANCEL

    ride = get_block(order).get("ride_ref")
    if not ride:
        return None
    tasks = Directive.objects.filter(topic=COURIER_CANCEL, payload__courier_ref=ride)
    if pending_only:
        tasks = tasks.filter(Q(status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING)) |
            Q(payload__cancel_attempt__state__in=("started", "unknown", "accepted")))
    return tasks.order_by("-pk").first()


#: O que a tela diz de um cancelamento pedido, por estado (:func:`cancel_state`).
CANCEL_PENDING_MESSAGE = "Pedido de cancelamento enviado. Esperando a TaOn confirmar."
CANCEL_UNKNOWN_MESSAGE = "Cancelamento sem resultado confirmado. Confira esta corrida na central antes de reenviar."
CANCEL_NOT_SENT_MESSAGE = "O cancelamento não foi enviado à TaOn. Tente de novo."


def ride_name(order) -> str:
    """Como a frase chama a corrida deste pedido: "a corrida B", ou "a corrida do pedido A47"."""
    from shopman.shop.services.operator_orders import short_ref

    letter = ride_letter(get_block(order).get("ride_number"))
    return f"a corrida {letter}" if letter else f"a corrida do pedido {short_ref(order.ref)}"


def cancel_refused_message(order) -> str:
    """A recusa da central, na frase que a tela e o aviso mostram."""
    return f"A TaOn não cancelou {ride_name(order)}. Cancele pela central da TaOn."


def cancel_state(order) -> dict:
    """Em que pé está o cancelamento da corrida viva deste pedido. Fonte única.

    ``{"state", "message", "at"}``, lido da Directive ``courier.cancel`` da
    corrida: o Painel do pedido e a seção Entregas mostram a mesma coisa.

    - ``""``: ninguém pediu cancelamento (ou a corrida já não se cancela);
    - ``pending``: pedido enviado, a central ainda não confirmou. O botão some;
    - ``unknown``: o envio ficou sem resposta. Não se reenvia: confere-se na central;
    - ``failed``: a central recusou (ou nada foi enviado). A corrida segue aberta.
    """
    empty = {"state": "", "message": "", "at": ""}
    if not ride_cancellable(get_block(order)):
        return empty
    task = latest_cancellation(order)
    if task is None:
        return empty
    state = ((task.payload or {}).get("cancel_attempt") or {}).get("state")
    at = task.updated_at.isoformat() if task.updated_at else ""
    # O recibo da tentativa manda: ele é gravado antes de a tarefa mudar de status.
    if state == "refused":
        return {"state": "failed", "message": cancel_refused_message(order), "at": at}
    if state == "not_applied":
        return {"state": "failed", "message": CANCEL_NOT_SENT_MESSAGE, "at": at}
    live = task.status in (Directive.Status.QUEUED, Directive.Status.RUNNING)
    if state == "unknown" or (state == "started" and not live):
        return {"state": "unknown", "message": CANCEL_UNKNOWN_MESSAGE, "at": at}
    if live or state in ("started", "accepted"):
        return {"state": "pending", "message": CANCEL_PENDING_MESSAGE, "at": at}
    return empty


def last_failure(order) -> dict | None:
    """A corrida que acabou sem levar este pedido, enquanto ele espera de novo.

    Ninguém aceitou (``NOT_SERVED``) ou foi cancelada (``CANCELLED``): a corrida
    vai para o histórico (``attempts[-1]``) e o pedido volta para Aguardando. Sem
    isto ele voltava calado, como se nunca tivesse sido chamado.

    ``{"key", "state", "by_house", "at", "refs", "number"}``: ``key`` é a corrida
    (o ``ride_ref`` dela), ``refs`` os pedidos que iam nela (o "Chamar de novo"
    chama a corrida inteira), ``by_house`` diz que o cancelamento saiu daqui e
    ``number`` é o da letra que ela tinha. ``None`` com corrida viva, sem
    histórico, quando o fim não foi falha, ou quando uma chamada mais nova já
    falhou por outro motivo (``block["error"]``, que a tela mostra no lugar).
    """
    from shopman.shop.protocols import RideState

    block = get_block(order)
    if block.get("ride_ref"):
        return None
    attempts = block.get("attempts") or []
    last = attempts[-1] if attempts and isinstance(attempts[-1], dict) else None
    if last is None:
        return None
    state = delivery_services.ride_state({**block, "status": last.get("status")})
    if state not in (RideState.NOT_SERVED, RideState.CANCELLED):
        return None
    at = str(last.get("ended_at") or "")
    error = block.get("error") if isinstance(block.get("error"), dict) else {}
    if str(error.get("at") or "") > at:
        return None
    refs = [str(ref) for ref in last.get("ride_orders") or [] if ref] or [order.ref]
    return {
        "key": str(last.get("ride_ref") or ""),
        "state": state.value,
        "by_house": state == RideState.CANCELLED and str(block.get("last_source") or "").startswith("operator:"),
        "at": at,
        "refs": refs,
        "number": block.get("ride_number"),
    }


def failure_message(failure: dict, *, live_numbers=None) -> str:
    """A frase da corrida que falhou: "Ninguém aceitou a corrida B (14h20)."

    A letra sai quando já é de outra corrida viva (``live_numbers``, os números
    ocupados; lidos aqui quando a tela não os passa): a frase diz só "a
    corrida", e a tela mostra os pedidos dela ao lado.
    """
    from django.utils.dateparse import parse_datetime
    from shopman.utils.formatting import format_clock

    from shopman.shop.protocols import RideState

    number = failure.get("number")
    live = set(_live_ride_numbers()) if live_numbers is None else set(live_numbers)
    letter = "" if number in live else ride_letter(number)
    ride = f"a corrida {letter}" if letter else "a corrida"
    clock = format_clock(parse_datetime(failure.get("at") or ""))
    when = f" ({clock})" if clock else ""
    if failure.get("state") == RideState.NOT_SERVED.value:
        return f"Ninguém aceitou {ride}{when}."
    if failure.get("by_house"):
        return f"A casa cancelou {ride}{when}."
    return f"A TaOn cancelou {ride}{when}."


def ride_health(order, *, tasks: dict[str, list[Directive]] | None = None) -> dict:
    """Como vai a corrida deste pedido. Fonte ÚNICA do Painel do pedido e da página Entregas.

    As duas telas leem daqui, e só daqui, o que mostram da corrida; um campo
    novo entra aqui e chega às duas (o teste de contrato
    ``test_ride_health_contract`` reprova a tela que deixar de ler).

    - ``unresolved``: a chamada ficou sem resposta (:func:`unresolved_dispatch`);
    - ``cancel``: o cancelamento pedido (:func:`cancel_state`);
    - ``progress``: o andamento em instantes ISO (:func:`progress_view`);
    - ``reopened``: a desistência que ainda vale (:func:`reopen_view`);
    - ``tracking``: link e código da parada deste pedido (:func:`proven_tracking`);
    - ``charge_outdated``: a cobrança que ficou para trás (:func:`charge_outdated`);
    - ``last_failure``: a corrida que acabou sem levar o pedido (:func:`last_failure`).

    ``tasks``: as tarefas de despacho já lidas em lote (:func:`dispatch_tasks_for`).
    """
    block = get_block(order)
    return {
        "unresolved": unresolved_dispatch(order, tasks=tasks) is not None,
        "cancel": cancel_state(order),
        "progress": progress_view(block),
        "reopened": reopen_view(block),
        "tracking": proven_tracking(block),
        "charge_outdated": charge_outdated(order),
        "last_failure": last_failure(order),
    }


def cancel_question(order) -> str:
    """A pergunta da confirmação: "Cancelar a corrida B? A05 e C12 voltam para Aguardando."

    Diz o que o toque desfaz: a corrida inteira, com todos os pedidos dela.
    """
    return f"Cancelar {ride_name(order)}? {cancel_consequence(order)}"


def cancel_consequence(order) -> str:
    """O que o cancelamento desfaz: "A05 e C12 voltam para Aguardando."."""
    from shopman.shop.services.operator_orders import short_ref

    codes = [short_ref(ref) for ref in ride_orders(order)]
    names = codes[0] if len(codes) == 1 else f"{', '.join(codes[:-1])} e {codes[-1]}"
    return f"{names} {'volta' if len(codes) == 1 else 'voltam'} para Aguardando."


def cancel_asks_reason(order) -> bool:
    """Depois do aceite a central quer saber por quê: a confirmação já traz os motivos."""
    block = get_block(order)
    return ride_cancellable(block) and block.get("status") not in BEFORE_ACCEPT_STATUSES


@transaction.atomic
def cancel_ride(order, *, actor: str, reason_id: int | None = None, expected_revision: str | None = None,
                intent: str = CANCEL_INTENT_OPERATOR) -> Directive:
    """Record a request for the observed ride; the worker owns remote I/O.

    ``reason_id`` é o motivo que o operador escolheu (só vale depois do aceite;
    antes dele a central só aceita o 10 e a escolha nem é perguntada). Sem ele,
    o worker usa o motivo do ``intent`` (``courier_machine.cancel_reason_for``).
    A solicitação é da corrida: uma por ``ride_ref``, venha de qual pedido vier.
    """
    from shopman.shop.directives import COURIER_CANCEL, create_deduped
    from shopman.shop.services.operator_orders import OrderStateConflict

    order = Order.objects.select_for_update().get(pk=order.pk)
    if expected_revision is not None and dispatch_revision(order) != expected_revision:
        raise OrderStateConflict("O pedido ou a corrida mudou. Confira antes de solicitar cancelamento.")
    if delivery_services.courier_backend() is None:
        raise ValueError("Nenhum adapter de courier configurado.")
    if reason_id is not None and reason_id not in CANCEL_REASONS_AFTER_ACCEPT:
        raise ValueError("Motivo de cancelamento desconhecido. Atualize a tela e escolha de novo.")
    block = get_block(order)
    if not has_active_ride(order):
        raise ValueError("Não há corrida ativa para cancelar.")
    if not ride_cancellable(block):
        raise ValueError("A corrida já está com o entregador em rota. Combine o retorno por telefone com a central.")
    existing = latest_cancellation(order, pending_only=True)
    if existing is not None:
        state = (existing.payload or {}).get("cancel_attempt", {}).get("state")
        if state in {"started", "unknown", "accepted"}:
            raise OrderStateConflict("Cancelamento já iniciado. Confira o resultado na central antes de outra solicitação.")
        return existing
    # A corrida inteira: o pedido pelo qual os gestos dela vão (o primeiro) e
    # todos os que a carregam, lidos AGORA. Depois do C ninguém mais saberia
    # quem estava nela (o fim arquiva ``ride_orders``).
    members = [order, *ride_companions(order)]
    by_ref = {member.ref: member for member in members}
    refs = [ref for ref in ride_orders(order) if ref in by_ref]
    refs += [member.ref for member in members if member.ref not in refs]
    task = create_deduped(COURIER_CANCEL,
        payload={"order_ref": refs[0], "order_refs": refs, "channel_ref": by_ref[refs[0]].channel_ref or "",
            "actor": actor, "courier_ref": block["ride_ref"], "reason_id": reason_id, "intent": intent},
        dedupe_key=f"courier.cancel:{block['ride_ref']}")
    if task is None:
        raise OrderStateConflict("Já existe uma solicitação de cancelamento para esta corrida. Atualize o pedido.")
    for member in members:
        member.emit_event(event_type="courier_cancel_requested", actor=actor,
                          payload={"directive_id": task.pk, "ride_ref": block["ride_ref"]})
        _emit_sse(member, {"kind": "cancel_queued"})
    return task


#: O aviso que o cancelamento do pedido deixa quando a corrida não volta sozinha.
#: Tipo existente (sem migração) e fora da resolução automática por status do
#: pedido: só sai quando o operador resolve com a central.
_CANCELLED_ORDER_ALERT_TYPE = "integration_failed"


def on_order_cancelled(order) -> None:
    """Pedido cancelado: a corrida dele não pode seguir aberta na central.

    - Antes da coleta (:func:`ride_cancellable`): enfileira o cancelamento da
      corrida pelo caminho de sempre (:func:`cancel_ride`, Directive
      ``courier.cancel``, dedupe por corrida), com o motivo da fase.
      Cancelamento já pedido é no-op.
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
        # Só quem ainda espera a entrega segura a corrida: se os outros já
        # foram cancelados, esta é a última parada viva e a corrida vai junto.
        companions = ride_companions(order, alive=True) if has_active_ride(order) else []
        if companions:
            # A corrida leva outros pedidos: cancelar a corrida tiraria o
            # entregador deles também. O operador tira a parada com a central.
            others = ", ".join(short_ref(other.ref) for other in companions)
            if status == "E":
                _alert_cancelled_order(order, f"O pedido {code} foi cancelado e já saiu na corrida de {others}: "
                    "fale com a central. O troco e a maquininha dele voltam com o entregador.")
                return
            # Ainda não coletado: o troco dele volta à gaveta já, e a maquininha
            # compartilhada segue com a corrida dos outros.
            _return_custody(order, actor="lifecycle.on_cancelled", reason="order_cancelled", ride_continues=True)
            _alert_cancelled_order(order, f"O pedido {code} foi cancelado e está na mesma corrida de {others}: "
                "fale com a central para tirar a parada dele, sem cancelar a corrida.")
            return
        if not has_active_ride(order):
            if unresolved_dispatch(order) is not None:
                _alert_cancelled_order(order, f"O pedido {code} foi cancelado com um pedido de entregador sem "
                    "resultado confirmado: confira na central e cancele a corrida, se ela existir.")
            else:
                # Nenhuma corrida viva nem possível: a custódia da chamada volta já.
                _return_custody(order, actor="lifecycle.on_cancelled", reason="order_cancelled")
            return
        if status == "E":
            _alert_cancelled_order(order, f"O entregador já coletou o pedido {code}, que foi cancelado: fale com a central.")
            return
        if ride_cancellable(block):
            try:
                cancel_ride(order, actor="lifecycle.on_cancelled", intent=CANCEL_INTENT_ORDER_CANCELLED)
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


def _return_custody(order, *, actor: str, reason: str, ride_continues: bool = False) -> None:
    """Devolve a custódia da chamada; nunca derruba o funil da corrida, mas grita."""
    from shopman.shop.services import operator_orders

    try:
        operator_orders.return_partner_custody(order, actor=actor, reason=reason, ride_continues=ride_continues)
    except Exception:
        logger.exception("courier.custody_return_failed order=%s reason=%s", order.ref, reason)


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
            "ride_ref": block.get("ride_ref", ""),
            "status": block.get("status", ""),
            "requested_at": block.get("requested_at", ""),
            "status_at": dict(block.get("status_at") or {}),
            "ended_at": timezone.now().isoformat(),
            # O custo fica com a corrida: o B.I. soma o que a casa pagou à TaOn,
            # inclusive a corrida que terminou antes de outra chamada.
            **({"final_value_q": block["final_value_q"]} if block.get("final_value_q") is not None else {}),
            **({"estimate": dict(block["estimate"])} if block.get("status") == "F" and block.get("estimate") else {}),
            **({"ride_orders": list(block["ride_orders"])} if block.get("ride_orders") else {}),
            **({"reopens": list(block["reopens"])} if block.get("reopens") else {}),
        }
    )
    block["attempts"] = attempts
    for key in ("ride_ref", "status", "status_at", "dispatched_at", "finished_at", "driver",
                "tracking_url", "confirmation_code", "tracking_match", "final_value_q", "progress", "sync",
                "door_charge_note",
                "ride_orders", "reopens", "last_provider_at"):
        block.pop(key, None)


# ── Desistência do entregador: a TaOn reabre a MESMA corrida ─────────

#: O que o entregador que saiu deixou no andamento: vai embora com ele.
_DRIVER_PROGRESS_KEYS = ("accepted_at", "pickup_eta_at", "pickup_eta_minutes", "pickup_km",
                         "near_pickup_at", "arrived_pickup_at", "waited_pickup_at",
                         "cancelled_at", "cancelled_reason")

_REOPEN_EVENT = "courier_ride_reopened"


def provider_instant(value):
    """Instante com fuso de um texto ISO, ou ``None`` (ilegível ou sem fuso não ordena nada)."""
    from django.utils.dateparse import parse_datetime

    if not isinstance(value, str) or not value:
        return None
    try:
        moment = parse_datetime(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None


#: Por que a corrida voltou a procurar: o entregador desistiu (``C`` com
#: ``will_reopen``, ou o aceite que regrediu) ou a TaOn trocou o entregador (``T``).
REOPEN_WITHDREW = "withdrew"
REOPEN_TRANSFER = "transfer"


def _reopen(block: dict, *, at: str, source: str, reason: str = REOPEN_WITHDREW) -> str:
    """O entregador saiu da corrida e a TaOn voltou a procurar: devolve o nome dele.

    A corrida é a mesma (``ride_ref``, paradas, custódia, número): só o entregador
    e o que era dele saem. O aceite dele sai de ``status_at`` para o próximo
    aceite registrar a própria hora, e fica guardado em ``reopens``. O link de
    rastreio e o código da parada saem também: o entregador novo pode ter link
    novo, e o próximo aceite busca de novo.
    """
    driver = block.get("driver") if isinstance(block.get("driver"), dict) else {}
    name = str(driver.get("name") or "")
    status_at = dict(block.get("status_at") or {})
    accepted_at = status_at.pop("A", None)
    status_at.pop("S", None)
    entry = {"at": at, "driver": name, "source": source, "reason": reason}
    if accepted_at:
        entry["accepted_at"] = accepted_at
    block["reopens"] = [*list(block.get("reopens") or []), entry]
    block["status_at"] = status_at
    for key in ("driver", "tracking_url", "confirmation_code", "tracking_match"):
        block.pop(key, None)
    progress = {key: value for key, value in (block.get("progress") or {}).items() if key not in _DRIVER_PROGRESS_KEYS}
    if progress:
        block["progress"] = progress
    else:
        block.pop("progress", None)
    return name


def reopen_view(block: dict) -> dict:
    """A desistência que ainda vale na tela: ``{"at", "driver", "reason"}`` (vazios quando não há).

    Vale enquanto a TaOn procura outro entregador (D/G/P depois de uma
    desistência ou de uma troca). Aceita de novo, a corrida volta a ter dono e
    a frase some. ``reason``: :data:`REOPEN_WITHDREW` ou :data:`REOPEN_TRANSFER`.
    """
    reopens = block.get("reopens") if isinstance(block.get("reopens"), list) else []
    last = reopens[-1] if reopens and isinstance(reopens[-1], dict) else None
    if last is None or not block.get("ride_ref") or str(block.get("status") or "") not in ("D", "G", "P"):
        return {"at": "", "driver": "", "reason": ""}
    return {"at": str(last.get("at") or ""), "driver": str(last.get("driver") or ""),
            "reason": str(last.get("reason") or REOPEN_WITHDREW)}


def record_reopen(order, *, at: str | None = None, source: str = "webhook",
                  reason: str = REOPEN_WITHDREW) -> str:
    """O entregador desistiu e a TaOn reabriu a corrida sozinha (``will_reopen``).

    A doc da TaOn diz: com ``will_reopen``, "não abra outra solicitação". A
    corrida continua a mesma e chamada: mantém o ``ride_ref``, volta a procurar
    (``D``), perde o entregador e grava ``reopens``. Não arquiva, não avisa
    "chame de novo" e não devolve a custódia: o troco e a maquininha seguem
    separados para o próximo entregador. Chamar de novo aqui seria uma segunda
    corrida paga.

    Devolve ``"applied"``, ``"noop"`` (a mesma desistência, de novo), ``"stale"``
    (chegou fora de hora) ou vazio (o pedido não tem esta corrida).
    """
    ride_id = get_block(order).get("ride_ref")
    if not ride_id:
        return ""
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") != ride_id:
            return ""
        previous = str(block.get("status") or "")
        reopens = block.get("reopens") if isinstance(block.get("reopens"), list) else []
        if at and reopens and isinstance(reopens[-1], dict) and reopens[-1].get("at") == at:
            return "noop"
        provider_at, last = provider_instant(at), provider_instant(block.get("last_provider_at"))
        if previous in TERMINAL_STATUSES or block.get("dispatched_at") or (provider_at and last and provider_at < last):
            # Depois da coleta ou do fim não há o que reabrir; aviso mais velho
            # que o último aplicado chegou fora de ordem.
            logger.info("courier_status_ignored order=%s ride_ref=%s previous=%s received=C(will_reopen) source=%s",
                        order.ref, ride_id, previous, source)
            return "stale"
        now_iso = timezone.now().isoformat()
        name = _reopen(block, at=at or now_iso, source=source, reason=reason)
        block.update(status="D", last_event_at=now_iso, last_source=source)
        if provider_at:
            block["last_provider_at"] = at
        order.emit_event(event_type=_REOPEN_EVENT, actor=source,
                         payload={"ride_ref": ride_id, "driver": name, "reason": reason})
        _save_block(order, block, emit={"kind": "reopened", "status": "D"})
    _forget_driver_caches(ride_id)
    return "applied"


def _forget_driver_caches(ride_id: str) -> None:
    """A posição, os links e a foto em cache eram do entregador que saiu."""
    cache.delete_many([f"courier:pos:{ride_id}", f"courier:tracking_links:{ride_id}",
                       *_driver_photo_keys(ride_id)])


# ── A foto do entregador: só durante a corrida (decisão do dono, LGPD) ──

#: Teto da vida da foto em cache. O fim da corrida (F, N, C, desistência) apaga
#: antes; o teto só cobre a corrida que some sem fim registrado.
DRIVER_PHOTO_SECONDS = 6 * 3600

#: Maior foto aceita (bytes). A da TaOn é um retrato pequeno.
DRIVER_PHOTO_MAX_BYTES = 512 * 1024


def _driver_photo_keys(ride_id: str) -> tuple[str, str]:
    return f"courier:photo_url:{ride_id}", f"courier:photo:{ride_id}"


def remember_driver_photo(ride_id: str, url: str) -> None:
    """Guarda o endereço da foto do entregador no cache, nunca no pedido.

    O endereço é assinado e é dado pessoal: não vai para ``Order.data`` nem
    para o log. A foto é baixada na primeira vez que uma tela pede
    (:func:`driver_photo`) e some com a corrida (:func:`_forget_driver_caches`).
    """
    if ride_id and url:
        cache.set(_driver_photo_keys(ride_id)[0], url, DRIVER_PHOTO_SECONDS)


def has_driver_photo(ride_id: str) -> bool:
    return bool(ride_id) and any(cache.get(key) for key in _driver_photo_keys(ride_id))


def driver_photo(ride_id: str) -> tuple[bytes, str] | None:
    """A foto do entregador desta corrida viva: ``(bytes, content_type)`` ou ``None``.

    Baixada pelo servidor (a tela nunca vê o endereço da TaOn) e guardada só em
    cache, com o teto de :data:`DRIVER_PHOTO_SECONDS`. Corrida que terminou não
    tem foto, mesmo que o cache ainda tenha: a regra é a corrida, não o relógio.
    """
    if not ride_id or not Order.objects.filter(data__courier__ride_ref=str(ride_id)).exclude(
            data__courier__status__in=list(TERMINAL_STATUSES)).exists():
        _forget_driver_caches(str(ride_id))
        return None
    url_key, bytes_key = _driver_photo_keys(str(ride_id))
    cached = cache.get(bytes_key)
    if isinstance(cached, dict) and cached.get("body"):
        return cached["body"], str(cached.get("type") or "image/jpeg")
    url = cache.get(url_key)
    if not url:
        return None
    import requests

    try:
        response = requests.get(url, timeout=5, stream=True, allow_redirects=False)
        content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip()
        body = response.raw.read(DRIVER_PHOTO_MAX_BYTES + 1, decode_content=True)
        response.close()
    except Exception:  # silêncio-deliberado: sem foto, a tela mostra a inicial
        logger.warning("courier.driver_photo_failed ride_ref=%s", ride_id)
        return None
    if response.status_code != 200 or not content_type.startswith("image/") or not body \
            or len(body) > DRIVER_PHOTO_MAX_BYTES:
        logger.warning("courier.driver_photo_refused ride_ref=%s status=%s type=%s size=%s",
                       ride_id, response.status_code, content_type or "-", len(body or b""))
        cache.delete(url_key)
        return None
    cache.set(bytes_key, {"body": body, "type": content_type}, DRIVER_PHOTO_SECONDS)
    return body, content_type


#: Tipo existente (sem migração) e fora da resolução automática da corrida viva:
#: o aviso de corrida retomada só sai quando o operador confere.
_RESTORED_ALERT_TYPE = "integration_failed"

_RESTORED_ALERT_MARKER = "constava como encerrada"


def orders_with_archived_ride(ride_id: str) -> list:
    """Pedidos ainda em andamento que têm esta corrida no histórico (``attempts``)."""
    ride_id = str(ride_id or "")
    if not ride_id:
        return []
    candidates = Order.objects.filter(status__in=RIDE_ORDER_STATUSES, data__courier__has_key="attempts").order_by("pk")
    return [order for order in candidates
            if any(isinstance(attempt, dict) and str(attempt.get("ride_ref") or "") == ride_id
                   for attempt in get_block(order).get("attempts") or [])]


def archived_ride_ended_at(order, ride_id: str):
    """Quando a corrida arquivada terminou (a hora da letra final; sem ela, a do arquivamento)."""
    for attempt in reversed(get_block(order).get("attempts") or []):
        if isinstance(attempt, dict) and str(attempt.get("ride_ref") or "") == str(ride_id):
            status_at = attempt.get("status_at") if isinstance(attempt.get("status_at"), dict) else {}
            return provider_instant(status_at.get(str(attempt.get("status") or ""))) or provider_instant(attempt.get("ended_at"))
    return None


def restore_archived_ride(order, ride_id: str, *, source: str) -> str:
    """A corrida que constava como encerrada (N/C) deu sinal de vida: volta a ser a corrida do pedido.

    Quem chama já provou que o sinal é mais novo que o encerramento. Devolve
    ``"restored"``, ``"live"`` (já é a corrida do pedido), ``"conflict"`` (o
    pedido já tem outra corrida) ou vazio (não achou no histórico). Avisa o
    operador nos dois casos que pedem conferência.
    """
    ride_id = str(ride_id)
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") == ride_id:
            return "live"
        attempts = [dict(attempt) for attempt in block.get("attempts") or [] if isinstance(attempt, dict)]
        index = next((i for i in range(len(attempts) - 1, -1, -1) if str(attempts[i].get("ride_ref") or "") == ride_id), None)
        if index is None:
            return ""
        if block.get("ride_ref") or order.status not in RIDE_ORDER_STATUSES:
            outcome = "conflict"
        else:
            attempt = attempts.pop(index)
            now_iso = timezone.now().isoformat()
            status_at = {letter: moment for letter, moment in (attempt.get("status_at") or {}).items()
                         if letter not in TERMINAL_STATUSES and letter not in ("A", "S")}
            block.update(provider="machine", ride_ref=ride_id, status="D", status_at=status_at or {"D": now_iso},
                         requested_at=str(attempt.get("requested_at") or now_iso), last_event_at=now_iso, last_source=source)
            if service_ref := delivery_services.new_ride_service_ref():
                block["service"] = service_ref
            if attempt.get("ride_orders"):
                block["ride_orders"] = list(attempt["ride_orders"])
            if attempt.get("reopens"):
                block["reopens"] = list(attempt["reopens"])
            if attempts:
                block["attempts"] = attempts
            else:
                block.pop("attempts", None)
            block.pop("error", None)
            order.emit_event(event_type="courier_ride_restored", actor=source, payload={"ride_ref": ride_id})
            _save_block(order, block, emit={"kind": "restored", "status": "D"})
            outcome = "restored"
    _alert_ride_restored(order, ride_id, outcome)
    return outcome


def _alert_ride_restored(order, ride_id: str, outcome: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.operator_orders import short_ref

    letter = ride_letter(get_block(order).get("ride_number"))
    code = short_ref(order.ref)
    if outcome == "restored":
        severity, message = "warning", (
            f"A TaOn retomou a corrida {letter + ' ' if letter else ''}do pedido {code}, que {_RESTORED_ALERT_MARKER}. "
            "Não chame outro entregador. Se o troco ou a maquininha voltaram para a casa, "
            "separe de novo antes de entregar a sacola."
        )
    else:
        severity, message = "critical", (
            f"A TaOn deu notícia de uma corrida do pedido {code} que {_RESTORED_ALERT_MARKER}, e o pedido já tem outra. "
            "Confira na central da TaOn para a casa não pagar duas corridas."
        )
    logger.warning("courier.archived_ride_alive order=%s ride_ref=%s outcome=%s", order.ref, ride_id, outcome)
    try:
        if alert_adapter.recent_exists(_RESTORED_ALERT_TYPE, None, order_ref=order.ref, message_contains=_RESTORED_ALERT_MARKER):
            return
        alert_adapter.create(_RESTORED_ALERT_TYPE, severity, message, order_ref=order.ref)
    except Exception:
        logger.warning("courier.alert_failed order=%s", order.ref, exc_info=True)


# ── Status (funil único: webhook + polling) ─────────────────────────

_STATUS_EVENT = "courier_status"


def _status_out_of_order(block: dict, status: str, *, source: str, at: str | None) -> bool:
    """Esta letra chegou fora de ordem e não pode mexer na corrida?

    A régua (:data:`_STATUS_RANK`) vale para as duas vias. Voltar atrás só é
    verdade num caso: aceita (A/S) que volta a procurar (D/G/P/U) antes da
    coleta, quando o entregador sai e a TaOn procura outro. Depois da coleta
    nada volta: um ``A`` atrasado não desfaz a sacola na moto, nem devolve o
    botão de cancelar. Entre avisos do webhook vale também a hora do evento
    (``last_provider_at``): o mais velho que o último aplicado é atraso de
    entrega, mesmo quando a letra é "maior".
    """
    previous = str(block.get("status") or "")
    if previous in TERMINAL_STATUSES:
        return True
    if source == "webhook":
        # Mais velho que o último aviso aplicado, ou que a hora em que a letra
        # de agora aconteceu (a leitura pode ter chegado antes do aviso).
        status_at = block.get("status_at") if isinstance(block.get("status_at"), dict) else {}
        provider_at = provider_instant(at)
        marks = [provider_instant(block.get("last_provider_at")), provider_instant(status_at.get(previous))]
        if provider_at and any(mark and provider_at < mark for mark in marks):
            return True
    if _STATUS_RANK.get(status, 0) >= _STATUS_RANK.get(previous, 0):
        return False
    return _STATUS_RANK.get(previous, 0) != 1 or bool(block.get("dispatched_at"))


def apply_status(order, machine_status: str, *, source: str, details: dict | None = None,
                 at: str | None = None) -> str:
    """Persist the external fact once; every replay retries its local derivation.

    ``at`` is when the provider says the step happened (``status_at``); absent,
    the moment it reached us.

    Enrichment uses the observed ride outside the lock. A replacement ride cannot
    adopt its response. A local custody refusal never rolls back the external fact.

    Devolve ``"applied"``, ``"noop"`` (a mesma letra de novo), ``"stale"`` (letra
    fora de ordem, recusada: ver :func:`_status_out_of_order`) ou vazio (o
    pedido não tem esta corrida).
    """
    status = (machine_status or "").strip().upper()
    observed = dict(get_block(order))
    ride_id = observed.get("ride_ref")
    if not status or not ride_id:
        return ""
    enrichment = dict(observed)
    if status == "A" and observed.get("status") != status and not observed.get("driver"):
        _enrich_accepted(enrichment, details, order_ref=order.ref)
    if status == "F" and observed.get("status") != status:
        _enrich_finished(enrichment, details)

    failed_ride = False
    outcome = "noop"
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") != ride_id:
            return ""
        previous = block.get("status")
        if previous != status and _status_out_of_order(block, status, source=source, at=at):
            logger.info("courier_status_ignored order=%s ride_ref=%s previous=%s received=%s source=%s",
                        order.ref, ride_id, previous, status, source)
            return "stale"
        if previous != status:
            outcome = "applied"
            now_iso = timezone.now().isoformat()
            for key in ("driver", "tracking_url", "confirmation_code", "tracking_match", "final_value_q"):
                if key in enrichment:
                    block[key] = enrichment[key]
            went_back = _STATUS_RANK.get(status, 0) < _STATUS_RANK.get(str(previous or ""), 0)
            if went_back:
                # Aceita que voltou a procurar: o entregador saiu (a mesma
                # desistência que o webhook traz com ``will_reopen``).
                name = _reopen(block, at=at or now_iso, source=source)
                order.emit_event(event_type=_REOPEN_EVENT, actor=source, payload={"ride_ref": ride_id, "driver": name})
            block.update(status=status, last_event_at=now_iso, last_source=source)
            if source == "webhook" and provider_instant(at):
                block["last_provider_at"] = at
            # Cada letra com a hora em que chegou pela primeira vez (A aceita, S em
            # espera, E coletou, F finalizou): o B.I. mede daqui o tempo de chegada do
            # entregador. ``last_event_at`` só guarda a última.
            status_at = dict(block.get("status_at") or {})
            status_at.setdefault(status, at or now_iso)
            block["status_at"] = status_at
            if status == "E":
                block.setdefault("dispatched_at", now_iso)
                # A cobrança que saiu com o entregador da TaOn, registrada na coleta.
                block.setdefault("door_charge", door_charge(order))
            if status == "F":
                block["finished_at"] = now_iso
            order.emit_event(event_type=_STATUS_EVENT, actor=source,
                             payload={"status": status, "ride_ref": ride_id})
            failed_ride = status in ("N", "C")
            if failed_ride:
                _archive_current_ride(block)
            kind = "ride_ended" if failed_ride else "reopened" if went_back else "status"
            _save_block(order, block, emit={"kind": kind, "status": status})
            if went_back or status in TERMINAL_STATUSES:
                # A foto e a posição eram da corrida: com ela encerrada (ou sem o
                # entregador que saiu), saem do cache.
                _forget_driver_caches(ride_id)
    if failed_ride and not source.startswith("operator:"):
        _alert_ride_failed(order, status)
    if failed_ride and not observed.get("dispatched_at"):
        # A corrida acabou sem coleta: o troco volta à gaveta e a maquininha
        # é liberada (custódia registrada na chamada).
        _return_custody(order, actor=f"courier:{status}", reason="not_attended" if status == "N" else "ride_cancelled")
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
    return outcome


def recover_local_status(order, *, ride_id: str) -> None:
    """Reconcile only the known ride's due local transitions, without provider I/O."""
    from shopman.shop.services import operator_orders

    order.refresh_from_db()
    block = get_block(order)
    if block.get("ride_ref") != ride_id:
        return
    status = block.get("status")
    if status in ("E", "F") and order.status in _BEFORE_READY_STATUSES:
        _collected_before_ready(order, ride_id=ride_id)
        order.refresh_from_db()
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


def _collected_before_ready(order, *, ride_id: str) -> None:
    """O entregador coletou um pedido que ninguém marcou pronto.

    O operador chamou a corrida sabendo que a sacola estava pronta (a chamada é
    consciente desde o aceite): a coleta é o fato de que ela saiu. O pedido sobe
    os degraus que faltam até o pronto pelo mesmo ``advance_order`` (avisos e
    trava de pagamento incluídos); a saída segue no fluxo de sempre. Se um degrau
    for recusado, o pedido fica onde está e o Gestor mostra a corrida em curso.
    """
    from shopman.shop.services import operator_orders

    for _ in range(len(_BEFORE_READY_STATUSES)):
        if order.status not in _BEFORE_READY_STATUSES:
            return
        try:
            operator_orders.advance_order(order, actor="courier:machine", expected_courier_id=ride_id)
        except Exception:
            logger.warning("courier.collected_before_ready_refused order=%s status=%s",
                           order.ref, order.status, exc_info=True)
            return
        order.refresh_from_db()


#: Como o link de rastreio foi casado com a parada DESTE pedido
#: (``courier.tracking_match``). Sem uma destas provas o link não é gravado.
TRACKING_MATCHES = ("id", "stop", "single", "position")

#: Onde a TaOn pode dizer de qual pedido é a parada. Só ``id_externo`` é enviado
#: por nós na abertura; vale como prova a igualdade exata com a ref do pedido.
_LINK_ORDER_KEYS = ("id_externo", "numero_pedido")

#: Por quanto tempo os pedidos de uma corrida dividem a MESMA leitura dos links
#: (o tempo de uma batida passar por todos), e o intervalo entre duas tentativas
#: quando o link ainda não veio.
_TRACKING_LINKS_SHARED_SECONDS = 60
_TRACKING_RETRY_SECONDS = 300


def _link_names(entry: dict, order_ref: str) -> bool:
    return any(str(entry.get(key) or "").strip() == order_ref for key in _LINK_ORDER_KEYS)


def link_for_order(order_ref: str, ride_refs, links, *, stop_id: str = "") -> dict:
    """O link de rastreio e o código da parada DESTE pedido, ou ``{}`` (falha fechada).

    Corrida com várias paradas tem um link por parada, e cada um mostra a entrega
    de UM cliente. Gravar o da parada errada entrega a rota de uma pessoa a outra
    (16/11/2026: todo pedido da corrida recebia ``links[0]``). O casamento só vale
    com prova, nesta ordem:

    1. ``id``: a entrada nomeia o pedido (``id_externo``/``numero_pedido`` igual à
       ref). Se a lista nomeia outros pedidos da corrida e não este, não há link.
    2. ``stop``: a entrada tem o ``parada_id`` já gravado no pedido (``courier.stop_id``).
    3. ``single``: a corrida é de um pedido só; não há outro cliente na rota.
    4. ``position``: uma entrada por parada, na ordem enviada à TaOn
       (``ride_orders``), e só quando os tamanhos batem e nenhuma parada ou link
       se repete.

    Fora disso (lista de outro tamanho, o formato único ``{"link"}`` numa corrida
    de várias paradas) devolve vazio, e o aviso e o botão do cliente somem sozinhos.
    """
    refs = [str(ref) for ref in ride_refs or [] if ref] or [order_ref]
    entries = [entry for entry in links or [] if isinstance(entry, dict)]
    if not entries or order_ref not in refs:
        return {}

    def proven(entry: dict, match: str) -> dict:
        link = str(entry.get("link_rastreio") or "").strip()
        code = entry.get("codigo_confirmacao")
        code = str(code).strip() if code is not None else ""
        if not link and not code:
            return {}
        return {"tracking_url": link, "confirmation_code": code, "tracking_match": match}

    named = [entry for entry in entries if _link_names(entry, order_ref)]
    if len(named) == 1:
        return proven(named[0], "id")
    if named or any(_link_names(entry, other) for entry in entries for other in refs):
        # A lista fala em pedidos e não aponta UM para este: não se adivinha.
        return {}
    if stop_id:
        same_stop = [entry for entry in entries if str(entry.get("parada_id") or "").strip() == stop_id]
        if len(same_stop) == 1:
            return proven(same_stop[0], "stop")
    if len(refs) == 1:
        return proven(entries[0], "single")
    if len(entries) != len(refs) or refs.count(order_ref) != 1:
        return {}
    stop_ids = [str(entry.get("parada_id") or "").strip() for entry in entries]
    urls = [str(entry.get("link_rastreio") or "").strip() for entry in entries]
    if any(stop_ids) and (not all(stop_ids) or len(set(stop_ids)) != len(stop_ids)):
        return {}
    if len({url for url in urls if url}) != len([url for url in urls if url]):
        return {}
    return proven(entries[refs.index(order_ref)], "position")


def proven_tracking(block) -> dict:
    """``{"url", "code"}`` da parada deste pedido; vazios quando o casamento não foi provado.

    Porta única de leitura do link e do código (aviso de saída, página do pedido,
    Gestor). Link gravado sem ``tracking_match`` é tratado como ausente: não há
    como saber de qual parada ele é.
    """
    empty = {"url": "", "code": ""}
    if not isinstance(block, dict):
        return empty
    match = block.get("tracking_match")
    if match not in TRACKING_MATCHES:
        return empty
    refs = block.get("ride_orders")
    if match == "single" and isinstance(refs, list) and len(refs) > 1:
        return empty
    return {"url": str(block.get("tracking_url") or ""), "code": str(block.get("confirmation_code") or "")}


def _ride_links(ride_id: str) -> list[dict]:
    """Os links da corrida, buscados UMA vez por corrida (os pedidos dela dividem a leitura)."""
    key = f"courier:tracking_links:{ride_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    adapter = delivery_services.courier_backend()
    if adapter is None:
        return []
    links = [dict(entry) for entry in adapter.tracking_links(ride_id) or [] if isinstance(entry, dict)]
    # Vale também para a lista vazia (a TaOn ainda não gerou os links): os pedidos
    # da corrida passam pela mesma leitura sem cada um bater de novo.
    cache.set(key, links, _TRACKING_LINKS_SHARED_SECONDS)
    return links


def _tracking_for(order_ref: str, block: dict, ride_id: str) -> dict:
    """Busca os links da corrida e devolve só o da parada deste pedido (ou ``{}``)."""
    try:
        links = _ride_links(str(ride_id))
    except CourierError as exc:
        logger.warning("courier.tracking_failed ride_ref=%s: %s", ride_id, exc)
        return {}
    if not links:
        return {}
    refs = block.get("ride_orders") if isinstance(block.get("ride_orders"), list) else None
    found = link_for_order(order_ref, refs, links, stop_id=str(block.get("stop_id") or ""))
    if not found and cache.add(f"courier:tracking_unmatched:{ride_id}:{order_ref}", 1, MAX_POLL_HOURS * 3600):
        # Uma vez por pedido da corrida, sem link e sem dado pessoal: só o tamanho do que não casou.
        logger.warning("courier.tracking_unmatched ride_ref=%s order=%s stops=%s links=%s",
                       ride_id, order_ref, len(refs or [order_ref]), len(links))
    return found


def _enrich_accepted(block: dict, details: dict | None, *, order_ref: str) -> None:
    """Corrida aceita: busca entregador + link de rastreio da parada (best-effort)."""
    adapter = delivery_services.courier_backend(block)
    if adapter is None:
        return
    try:
        # A leitura do polling já traz o entregador; o corpo do webhook não
        # (só a letra e os links): aí os detalhes vêm da central.
        info = details if isinstance(details, dict) and "driver" in details else adapter.get_details(block["ride_ref"])
        from shopman.shop.adapters.courier_machine import driver_from, driver_photo_url

        driver = driver_from(info)
        if driver:
            block["driver"] = driver
        remember_driver_photo(block["ride_ref"], driver_photo_url(info))
    except CourierError as exc:
        logger.warning("courier.details_failed ride_ref=%s: %s", block.get("ride_ref"), exc)
    block.update(_tracking_for(order_ref, block, block["ride_ref"]))


def _enrich_finished(block: dict, details: dict | None) -> None:
    """Corrida finalizada: valor final cobrado pela central (best-effort)."""
    adapter = delivery_services.courier_backend(block)
    if adapter is None:
        return
    if isinstance(details, dict) and details.get("final_value_q") is not None:
        block["final_value_q"] = int(details["final_value_q"])
        return
    try:
        info = details if isinstance(details, dict) and "finished" in details else adapter.get_details(block["ride_ref"])
        finished = info.get("finished") or {}
        final_value = finished.get("final_value")
        if final_value is not None:
            from shopman.shop.adapters.courier_machine import _to_q

            block["final_value_q"] = _to_q(final_value)
    except CourierError as exc:
        logger.warning("courier.finished_details_failed ride_ref=%s: %s", block.get("ride_ref"), exc)


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


# ── Leitura da corrida: progresso e falha de leitura ────────────────

#: Batidas seguidas sem conseguir ler a corrida até o aviso ao operador (~3 min).
SYNC_ALERT_AFTER = 3

#: Idade máxima da corrida para o polling seguir batendo. Corrida real dura
#: minutos; passado isto, ninguém mais acompanha e a batida só gasta cota.
MAX_POLL_HOURS = 6

_SYNC_ALERT_TYPE = "integration_failed"


def _sync_failures_key(ride_id: str) -> str:
    return f"courier:sync_failures:{ride_id}"


def _sync_alert_marker(ride_id: str) -> str:
    """O trecho do aviso que identifica a corrida na TaOn (dedupe e resolução).

    É a referência para achá-la no painel da central, não o nome dela: na casa a
    corrida se chama pela letra (:func:`ride_letter`).
    """
    return f"número {ride_id} na TaOn"


#: O que cada marco do progresso lido prova sobre a corrida, na ordem em que acontece.
_PROGRESS_STEPS = (("accepted_at", "A"), ("picked_up_at", "E"), ("finished_at", "F"))

#: Quão adiantada está cada letra (D/G/P/U, a procura, valem zero).
_STATUS_RANK = {"A": 1, "S": 1, "E": 2, "F": 3, "N": 3, "C": 3}


def _last_reopen_at(block: dict) -> str:
    reopens = block.get("reopens") if isinstance(block.get("reopens"), list) else []
    return str(reopens[-1].get("at") or "") if reopens and isinstance(reopens[-1], dict) else ""


def progress_since(progress: dict | None, since: str | None) -> dict:
    """O andamento lido, sem o que é do entregador que desistiu.

    A leitura pode seguir trazendo o aceite e a chegada de quem saiu da corrida.
    Marco com hora até a desistência (``since``) não é do entregador de agora:
    sai, e leva junto o que deriva dele (a previsão de chegada à loja).
    """
    from datetime import UTC

    from django.utils.dateparse import parse_datetime

    progress = dict(progress) if isinstance(progress, dict) else {}
    cutoff = provider_instant(since)
    if cutoff is None:
        return progress
    for key in ("accepted_at", "near_pickup_at", "arrived_pickup_at", "cancelled_at"):
        if not progress.get(key):
            continue
        try:
            moment = parse_datetime(str(progress[key]).replace("Z", "+00:00"))
        except ValueError:
            moment = None
        if moment is not None and moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)  # os campos ``*_utc`` da listagem
        # Hora ilegível não prova que o marco é do entregador de agora: sai.
        if moment is None or moment <= cutoff:
            progress.pop(key, None)
    if not progress.get("accepted_at"):
        for key in ("pickup_eta_at", "pickup_eta_minutes", "pickup_km"):
            progress.pop(key, None)
    if not progress.get("cancelled_at"):
        progress.pop("cancelled_reason", None)
    return progress


def statuses_from_reading(current: str | None, reported: str, progress: dict | None, *,
                          letter_only: bool = False) -> list[tuple[str, str | None]]:
    """As letras que uma leitura prova, em ordem, cada uma com a hora em que aconteceu.

    A letra que a central devolve pode ficar para trás do progresso da mesma
    leitura. Medido no alpha em 13/10/2026 (PDV-261013-L34, corrida 776753357):
    o progresso trouxe aceite 19:42, chegada à loja 19:44, coleta 19:45 e fim
    19:55, e a letra seguiu em D por 44 batidas; o pedido só soube do fim às
    20:26, quando a letra mudou. Vale o que estiver mais adiante: um marco do
    progresso avança o status sozinho, e os marcos pulados entram no caminho
    (a coleta registra a cobrança que saiu com o entregador antes do fim).

    Cancelada, só quando a letra lida é ``C``. Um ``cancelled_at`` no progresso
    não prova: a desistência de um entregador entra em ``cancellation[]`` e a
    TaOn segue procurando outro; concluir "cancelada" dali arquivava a corrida
    viva e mandava chamar de novo (duas corridas pagas).

    Uma letra sozinha (``letter_only``: a via que só devolve a letra) também
    não prova que a corrida voltou atrás, porque a letra pode estar atrasada:
    quem prova é a leitura completa, sem o aceite no andamento.
    """
    current = (current or "").strip().upper()
    reported = (reported or "").strip().upper()
    progress = progress if isinstance(progress, dict) else {}
    if reported == "C":
        return [("C", str(progress["cancelled_at"]) if progress.get("cancelled_at") else None)]
    if reported == "N":
        return [("N", None)]
    floor = _STATUS_RANK.get(current, 0)
    steps = [(letter, str(progress[key])) for key, letter in _PROGRESS_STEPS
             if progress.get(key) and _STATUS_RANK[letter] > floor]
    reached = max((_STATUS_RANK[letter] for key, letter in _PROGRESS_STEPS if progress.get(key)), default=0)
    if reported and _STATUS_RANK.get(reported, 0) < floor and letter_only:
        return steps
    if reported and _STATUS_RANK.get(reported, 0) >= reached and all(letter != reported for letter, _ in steps):
        steps.append((reported, None))
    return steps


def apply_snapshot(order, snapshot: dict, *, source: str) -> None:
    """Aplica uma leitura da corrida (``adapter.read_ride``): status, entregador e progresso.

    O status entra pelo funil de sempre (:func:`apply_status`). O resto
    (estimativa de chegada à loja, chegada, coleta, viagem, valor final) só é
    gravado quando muda, para a revisão do pedido não girar a cada batida.
    Uma leitura que deu certo encerra o aviso de "TaOn sem notícias".
    """
    if not snapshot:
        return
    ride_id = get_block(order).get("ride_ref")
    if not ride_id:
        return
    status = str(snapshot.get("status") or "")
    # Depois de uma desistência, o que a leitura ainda traz do entregador que
    # saiu não conta: nem avança a letra, nem volta para o andamento.
    letter_only = snapshot.get("via") == "status" or "progress" not in snapshot
    reading = progress_since(snapshot.get("progress"), _last_reopen_at(get_block(order)))
    for step, at in statuses_from_reading(get_block(order).get("status"), status, reading, letter_only=letter_only):
        apply_status(order, step, source=source, details={**snapshot, "progress": reading}, at=at)
    cache.delete(_sync_failures_key(ride_id))
    order.refresh_from_db()
    # A própria leitura pode ter registrado a desistência (aceita que voltou a procurar).
    reading = progress_since(snapshot.get("progress"), _last_reopen_at(get_block(order)))
    tracking = _tracking_retry(order.ref, get_block(order), ride_id, status)

    had_sync = False
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") == ride_id:
            had_sync = block.pop("sync", None) is not None
            changed = had_sync
            fresh = {k: v for k, v in reading.items() if v not in (None, "")}
            previous = dict(block.get("progress") or {})
            merged = {**previous, **fresh}
            if merged != previous:
                block["progress"] = merged
                changed = True
            driver = snapshot.get("driver")
            # Enquanto a TaOn procura (inclusive depois de uma desistência), o
            # entregador que a leitura ainda traz não é o da corrida.
            has_driver = _STATUS_RANK.get(str(block.get("status") or ""), 0) >= 1
            if has_driver and isinstance(driver, dict) and driver.get("name") and driver != block.get("driver"):
                block["driver"] = driver
                changed = True
            final_value_q = snapshot.get("final_value_q")
            if final_value_q is not None and final_value_q != block.get("final_value_q"):
                block["final_value_q"] = int(final_value_q)
                changed = True
            if tracking and not proven_tracking(block)["url"]:
                block.update(tracking)
                changed = True
            if changed:
                _save_block(order, block, emit={"kind": "progress", "status": block.get("status", "")})
        elif snapshot.get("final_value_q") is not None:
            # A leitura arquivou a corrida (N/C) antes de o valor ser gravado: a
            # taxa que a TaOn fechou fica com a corrida arquivada, para o B.I.
            attempts = [dict(attempt) for attempt in block.get("attempts") or []]
            for attempt in attempts:
                if attempt.get("ride_ref") == ride_id and attempt.get("final_value_q") is None:
                    attempt["final_value_q"] = int(snapshot["final_value_q"])
                    block["attempts"] = attempts
                    _save_block(order, block, emit={"kind": "progress", "status": block.get("status", "")})
                    break
    if had_sync or str(get_block(order).get("status") or "") in TERMINAL_STATUSES or not get_block(order).get("ride_ref"):
        _resolve_sync_alert(ride_id)


def _tracking_retry(order_ref: str, block: dict, ride_id: str, status: str) -> dict:
    """Link de rastreio que faltou no aceite: tenta de novo, no máximo a cada 5 min por corrida.

    A corrida com várias paradas faz UMA leitura: o primeiro pedido busca e os
    outros casam a própria parada na mesma lista (``_ride_links``).
    """
    if proven_tracking(block)["url"] or status not in ("A", "S", "E"):
        return {}
    if cache.get(f"courier:tracking_links:{ride_id}") is None and not cache.add(
            f"courier:tracking_retry:{ride_id}", 1, _TRACKING_RETRY_SECONDS):
        return {}
    return _tracking_for(order_ref, block, ride_id)


def record_sync_failure(order, exc: Exception, *, ride_id: str) -> None:
    """A batida não conseguiu ler a corrida: o operador precisa saber que a tela parou.

    O contador fica no cache (a revisão do pedido não gira a cada minuto). O
    pedido só muda duas vezes: na primeira falha (``sync.failing_since``, que a
    tela mostra) e quando vira aviso (``SYNC_ALERT_AFTER`` falhas seguidas).
    """
    key = _sync_failures_key(ride_id)
    failures = int(cache.get(key) or 0) + 1
    cache.set(key, failures, MAX_POLL_HOURS * 3600)
    first = "sync" not in get_block(order)
    if not first and failures != SYNC_ALERT_AFTER:
        return
    now_iso = timezone.now().isoformat()
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") != ride_id:
            return
        sync = dict(block.get("sync") or {})
        sync.setdefault("failing_since", now_iso)
        sync["last_error"] = str(exc)[:300]
        if failures >= SYNC_ALERT_AFTER:
            sync["alerted_at"] = now_iso
        block["sync"] = sync
        _save_block(order, block, emit={"kind": "sync_failed", "status": block.get("status", "")})
    if failures == SYNC_ALERT_AFTER:
        _alert_sync_failed(order, ride_id)


def _alert_sync_failed(order, ride_id: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.operator_orders import short_ref

    marker = _sync_alert_marker(ride_id)
    # Sem letra gravada, a frase diz só "corrida": o id da TaOn nunca faz de nome.
    letter = ride_letter(get_block(order).get("ride_number"))
    name = f"corrida {letter}" if letter else "corrida"
    try:
        if alert_adapter.recent_exists(_SYNC_ALERT_TYPE, None, order_ref=order.ref, message_contains=marker):
            return
        alert_adapter.create(
            _SYNC_ALERT_TYPE,
            "warning",
            f"A TaOn não está informando o andamento da {name} do pedido "
            f"{short_ref(order.ref)} ({marker}). "
            "O status na tela pode estar parado: confira no painel da TaOn.",
            order_ref=order.ref,
        )
    except Exception:
        logger.warning("courier.sync_alert_failed order=%s", order.ref, exc_info=True)


def _resolve_sync_alert(ride_id: str) -> None:
    from shopman.shop.adapters import alert as alert_adapter

    def _resolve():
        try:
            alert_adapter.resolve_matching(_SYNC_ALERT_TYPE, message_contains=_sync_alert_marker(ride_id),
                                           actor="courier:sync")
        except Exception:
            logger.warning("courier.sync_alert_resolve_failed ride_ref=%s", ride_id, exc_info=True)

    transaction.on_commit(_resolve)


def progress_view(block: dict) -> dict:
    """O que as telas mostram do andamento, em instantes ISO (o relógio é da tela).

    ``pickup_eta_at``: quando o entregador chega à loja (aceite + "tempo até o
    local de coleta" da TaOn). ``delivery_eta_at``: quando chega ao cliente
    (coleta, ou a chegada prevista à loja, + a viagem estimada; sem a viagem da
    central, a da cotação). ``sync_since``: desde quando a TaOn não informa a
    corrida (vazio quando a leitura está em dia).
    """
    from django.utils.dateparse import parse_datetime

    progress = block.get("progress") if isinstance(block.get("progress"), dict) else {}
    status_at = block.get("status_at") if isinstance(block.get("status_at"), dict) else {}
    estimate = block.get("estimate") if isinstance(block.get("estimate"), dict) else {}
    sync = block.get("sync") if isinstance(block.get("sync"), dict) else {}
    status = str(block.get("status") or "")

    pickup_eta_at = str(progress.get("pickup_eta_at") or "")
    picked_up_at = str(progress.get("picked_up_at") or (status_at.get("E") if status in ("E", "F") else "") or "")
    trip_minutes = progress.get("trip_minutes") or estimate.get("minutes")
    delivery_eta_at = ""
    base = parse_datetime(picked_up_at or pickup_eta_at) if (picked_up_at or pickup_eta_at) else None
    if base is not None and trip_minutes and status not in TERMINAL_STATUSES:
        delivery_eta_at = (base + timedelta(minutes=float(trip_minutes))).isoformat()
    return {
        "pickup_eta_at": pickup_eta_at if status in ("A", "S") else "",
        "near_pickup_at": str(progress.get("near_pickup_at") or "") if status in ("A", "S") else "",
        "arrived_pickup_at": str(progress.get("arrived_pickup_at") or "") if status in ("A", "S", "E", "F") else "",
        "waited_pickup_at": str(progress.get("waited_pickup_at") or "") if status in ("A", "S") else "",
        "picked_up_at": picked_up_at,
        "delivery_eta_at": delivery_eta_at,
        "arrived_dropoff_at": str(progress.get("arrived_dropoff_at") or ""),
        "sync_since": str(sync.get("failing_since") or ""),
    }


def poll_expired(block: dict) -> bool:
    """A corrida passou da idade em que o polling acompanha de perto."""
    from django.utils.dateparse import parse_datetime

    opened = parse_datetime(str(block.get("requested_at") or ""))
    return opened is not None and timezone.now() - opened > timedelta(hours=MAX_POLL_HOURS)


#: A batida lenta (ENT-07): a corrida que passou de :data:`MAX_POLL_HOURS`, ou
#: a casa com o polling desligado (só webhook), ainda é lida a cada 10 min.
#: Antes a batida parava, e a corrida aberta ficava na tela para sempre, sem
#: ninguém perguntar à TaOn se ela acabou.
SLOW_POLL_SECONDS = 600


def sync_interval(block: dict) -> int:
    """Quantos segundos até a próxima leitura desta corrida. Nunca zero."""
    seconds = poll_seconds()
    if seconds <= 0 or poll_expired(block):
        return max(seconds, SLOW_POLL_SECONDS)
    return seconds


def ride_open_too_long(block: dict) -> bool:
    """A corrida segue aberta além da idade em que uma corrida real dura."""
    return bool(block.get("ride_ref")) and block.get("status") not in TERMINAL_STATUSES and poll_expired(block)


# ── O que o cliente lê antes da coleta (L2 da revisão das Entregas) ─

#: Procurando entregador há mais que isso: no Gestor a corrida vira "Ninguém
#: aceitou ainda", e o cliente lê "Está demorando mais que o normal". Um número só
#: para as duas telas, para elas nunca discordarem sobre o mesmo minuto.
LATE_SEARCH_MINUTES = 10


def driver_first_name(name: str) -> str:
    """"Diego" de "DIEGO SOUZA LIMA": o cliente chama o entregador pelo primeiro nome."""
    parts = str(name or "").split()
    token = parts[0] if parts else ""
    if token.isupper() and len(token) > 1:
        token = token[:1] + token[1:].lower()
    return token


def customer_wait(block: dict) -> dict:
    """Onde a corrida está, no que importa ao cliente entre a chamada e a coleta.

    ``{"stage", "driver", "pickup_eta_at"}``. ``stage``:

    - ``""``: não há corrida viva (nunca chamada, cancelada ou encerrada); a
      página diz só que o pedido está pronto;
    - ``"called"``: chamada, ninguém a caminho ainda;
    - ``"late"``: ninguém aceitou há :data:`LATE_SEARCH_MINUTES` ou mais, ou o
      serviço desistiu de achar alguém;
    - ``"replaced"``: o entregador que aceitou desistiu e outro está sendo
      procurado (``driver`` é o nome de quem desistiu, que o cliente já leu);
    - ``"coming"``: alguém aceitou e vai até a loja (``pickup_eta_at`` quando o
      serviço informa a chegada);
    - ``"at_store"``: o entregador está na loja.

    Lê o estado NEUTRO (``delivery_services.ride_state``), então vale para a
    TaOn e para os entregadores da casa (DEV-2026-030) sem olhar a letra crua.
    """
    from django.utils.dateparse import parse_datetime

    from shopman.shop.protocols import RideState

    empty = {"stage": "", "driver": "", "pickup_eta_at": ""}
    if not isinstance(block, dict) or not block.get("ride_ref"):
        return empty
    state = delivery_services.ride_state(block)
    driver = block.get("driver") if isinstance(block.get("driver"), dict) else {}
    name = driver_first_name(driver.get("name") or "")
    if state in (RideState.CANCELLED, RideState.DONE):
        return empty
    if state == RideState.NOT_SERVED:
        return {**empty, "stage": "late"}
    if state in (RideState.ASSIGNED, RideState.AT_STORE, RideState.ON_ROUTE):
        progress = progress_view(block)
        if state != RideState.ASSIGNED or progress.get("arrived_pickup_at"):
            return {**empty, "stage": "at_store", "driver": name}
        return {"stage": "coming", "driver": name, "pickup_eta_at": progress.get("pickup_eta_at") or ""}
    # Procurando (inclusive trocando de entregador ou junto com outra corrida),
    # ou letra que a casa ainda não conhece: há corrida chamada, sem dono.
    reopened = reopen_view(block)
    if reopened["at"]:
        return {**empty, "stage": "replaced", "driver": driver_first_name(reopened["driver"])}
    if state == RideState.GROUPED:
        return {**empty, "stage": "called"}
    called = parse_datetime(str(block.get("called_at") or block.get("requested_at") or ""))
    if called is not None and timezone.now() - called >= timedelta(minutes=LATE_SEARCH_MINUTES):
        return {**empty, "stage": "late"}
    return {**empty, "stage": "called"}


def vehicle_line(driver: dict) -> str:
    """"Honda CG prata · ABC1D23": o que o balcão confere antes de entregar a sacola."""
    driver = driver if isinstance(driver, dict) else {}
    model = str(driver.get("vehicle_model") or "").strip()
    color = str(driver.get("vehicle_color") or "").strip()
    body = " ".join(part for part in (model, color.lower() if model else color) if part)
    if body:
        body = body[:1].upper() + body[1:]
    return " · ".join(part for part in (body, str(driver.get("vehicle_plate") or "").strip()) if part)


# ── Auto-conclusão da entrega com corrida viva (ENT-14) ──────────────

#: Sem notícia da TaOn há mais que isto, a leitura da corrida está parada.
STALE_READ_MINUTES = 30


def reading_is_fresh(block: dict) -> bool:
    """A casa sabe onde a corrida está: a leitura dá certo e é recente.

    Falha de leitura em curso (``sync``) ou corrida além da idade acompanhada
    não é leitura em dia. Com o polling ligado, a batida lê a cada minuto; sem
    ele (só webhook), vale o último aviso recebido.
    """
    from django.utils.dateparse import parse_datetime

    if block.get("sync") or poll_expired(block):
        return False
    if poll_seconds() > 0:
        return True
    last = parse_datetime(str(block.get("last_event_at") or ""))
    return last is not None and timezone.now() - last <= timedelta(minutes=STALE_READ_MINUTES)


def auto_complete_hold_until(order, *, grace_minutes: int):
    """Até quando a auto-conclusão espera, porque o entregador ainda está na rua.

    Com a corrida viva (coletada e não finalizada) e a leitura em dia, a TaOn
    sabe mais que o relógio: a conclusão vai para a entrega prevista por ela
    mais a folga (no mínimo a folga a partir de agora). ``None`` quando não há
    o que esperar: sem corrida viva, ou com o dado parado (aí conclui e avisa).
    """
    from django.utils.dateparse import parse_datetime

    block = get_block(order)
    if not block.get("ride_ref") or block.get("status") not in ("A", "S", "E"):
        return None
    if not reading_is_fresh(block):
        return None
    floor = timezone.now() + timedelta(minutes=max(grace_minutes, 1))
    eta = parse_datetime(progress_view(block).get("delivery_eta_at") or "")
    if eta is None:
        return floor
    return max(floor, eta + timedelta(minutes=grace_minutes))


def alert_auto_completed_blind(order) -> None:
    """A auto-conclusão marcou entregue um pedido com corrida aberta e sem notícia."""
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.operator_orders import short_ref

    letter = ride_letter(get_block(order).get("ride_number"))
    name = f"a corrida {letter}" if letter else "a corrida"
    try:
        alert_adapter.create(
            _SYNC_ALERT_TYPE,
            "warning",
            f"O pedido {short_ref(order.ref)} foi marcado entregue pelo prazo, mas {name} "
            "segue aberta e a TaOn não informa o andamento. Confira com o entregador.",
            order_ref=order.ref,
        )
    except Exception:
        logger.warning("courier.auto_complete_alert_failed order=%s", order.ref, exc_info=True)


#: Avisos do webhook que não são estado e que, ANTES da coleta, dizem onde o
#: entregador está em relação à loja (revisão das Entregas, TAON-12):
#: ``AN`` está nas redondezas; ``AW`` está esperando no local (a TaOn manda
#: quando a espera passa do combinado). ``AP`` (chegou) é :func:`record_arrival`.
PICKUP_EVENTS = {"AN": ("near_pickup_at",), "AW": ("arrived_pickup_at", "waited_pickup_at")}


def record_pickup_event(order, code: str, *, at: str | None = None, source: str = "webhook") -> None:
    """``AN``/``AW`` antes da coleta: grava o marco no andamento, uma vez cada.

    O ``AW`` também grava a chegada (quem espera, chegou), para o relógio da
    espera contar mesmo que o ``AP`` tenha se perdido. Depois da coleta, ou numa
    corrida encerrada, nada muda: a espera é no balcão.
    """
    keys = PICKUP_EVENTS.get(str(code or "").upper())
    block = get_block(order)
    ride_id = block.get("ride_ref")
    if not keys or not ride_id or block.get("status") in TERMINAL_STATUSES or block.get("dispatched_at"):
        return
    when = at or timezone.now().isoformat()
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") != ride_id or block.get("dispatched_at"):
            return
        progress = dict(block.get("progress") or {})
        fresh = {key: when for key in keys if not progress.get(key)}
        if not fresh:
            return
        block["progress"] = {**progress, **fresh}
        block.update(last_event_at=timezone.now().isoformat(), last_source=source)
        _save_block(order, block, emit={"kind": "progress", "status": block.get("status", "")})


def record_arrival(order, *, at: str | None = None, source: str = "webhook") -> None:
    """O entregador avisou que chegou (``AP`` do webhook): na loja antes da coleta, no cliente depois."""
    block = get_block(order)
    ride_id = block.get("ride_ref")
    if not ride_id or block.get("status") in TERMINAL_STATUSES:
        return
    key = "arrived_dropoff_at" if block.get("status") == "E" else "arrived_pickup_at"
    if key == "arrived_dropoff_at" and len(ride_orders(order)) > 1:
        # Corrida com várias paradas: o aviso não diz em qual cliente ele chegou.
        return
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        order.refresh_from_db()
        block = dict(get_block(order))
        if block.get("ride_ref") != ride_id:
            return
        progress = dict(block.get("progress") or {})
        if progress.get(key):
            return
        progress[key] = at or timezone.now().isoformat()
        block["progress"] = progress
        block.update(last_event_at=timezone.now().isoformat(), last_source=source)
        _save_block(order, block, emit={"kind": "progress", "status": block.get("status", "")})


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
    """Agenda (ou reagenda) o próximo poll de status. Idempotente.

    Corrida com várias paradas tem uma batida só, no primeiro pedido dela: a
    central limita as leituras por corrida, e a batida aplica a todos.
    """
    from shopman.shop.directives import COURIER_SYNC

    lead = ride_orders(order)[0]
    if lead != order.ref:
        order = Order.objects.filter(ref=lead).first() or order

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
