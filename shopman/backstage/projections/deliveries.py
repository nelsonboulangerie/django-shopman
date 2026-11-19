"""Projection da seção Entregas do Gestor: as corridas da TaOn num lugar só.

Três partes, as mesmas no mapa e na coluna (desenho do dono, 14/11/2026, PR #2462):

- **Aguardando**: entregas do dia, prontas ou em preparo, que a casa despacha e
  que ainda não têm corrida chamada. É o que o operador junta em corridas.
- **Editando**: não mora aqui. É estado da tela (as corridas que o operador
  está juntando antes de chamar), nada é gravado até o "Chamar".
- **Corridas**: as chamadas e vivas, agrupadas pela corrida da TaOn (``id_mch``),
  com o número que a corrida ganhou na chamada (``courier.next_ride_number``):
  ele dá a cor e a LETRA dela na tela (``courier.ride_letter``; corrida se nomeia
  por letra, nunca por número), o entregador, a posição, as paradas na ordem do
  percurso e as sacolas (volumes declarados).

Só leitura; os gestos usam os endpoints de sempre (``courier-ride``,
``courier-dispatch``, ``courier-back``, ``courier-cancel``). A corrida de
vários pedidos sai pela ação ``group_action``, no protocolo de intenção.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order

from shopman.shop.google_maps_credentials import browser_api_key
from shopman.shop.projections.types import Action

logger = logging.getLogger(__name__)

#: Procurando entregador há mais que isso: a corrida vira "Ninguém aceitou ainda".
LATE_SEARCH_MINUTES = 10


@dataclass(frozen=True)
class DeliveryPointProjection:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class DeliveryStopProjection:
    """Um pedido de entrega: na lista Aguardando ou como parada de uma corrida."""

    ref: str
    code: str
    customer: str
    place: str
    address: str
    latitude: float | None
    longitude: float | None
    #: "Pronto" ou "Em preparo".
    stage: str
    #: Volumes declarados (``Order.data["volumes"]``); 0 = ninguém declarou.
    volumes: int = 0
    #: Parada concluída (pedido entregue).
    done: bool = False
    #: O que a chamada pergunta: troco da gaveta e maquininha da casa.
    change_out_suggested_q: int = 0
    needs_machine: bool = False
    change_label: str = ""
    #: Recusa para ir junto com outros (vazio = pode).
    group_refusal: str = ""
    #: A última falha da chamada deste pedido ("A TaOn não achou entregador").
    error: str = ""
    #: "Chamar sozinho" (``courier-dispatch``), com a revisão e quem chama.
    dispatch_action: Action | None = None
    #: A última chamada ficou sem resposta da TaOn: "Chamar de novo"
    #: (``courier-dispatch-again``), a MESMA ação do Painel do pedido. Com ela, o
    #: "Chamar sozinho" some (o servidor recusaria) e o pedido não entra em corrida.
    dispatch_again_action: Action | None = None
    #: Numa parada de corrida: o pedido mudou depois da chamada e a cobrança que o
    #: entregador leu ficou para trás (``courier.charge_outdated``):
    #: ``{sent, current, collected}``, ou ``None``.
    charge_outdated: dict | None = None


@dataclass(frozen=True)
class DeliveryDriverProjection:
    name: str
    phone: str
    vehicle: str


@dataclass(frozen=True)
class DeliveryRideProjection:
    """Uma corrida chamada, viva: do "procurando" à volta do entregador."""

    key: str
    #: O número gravado na chamada: escolhe a cor. Nunca se mostra.
    number: int
    #: O nome da corrida na tela e na fala: A, B, C… (``courier.ride_letter``).
    letter: str
    #: searching · late · reopened · grouped · coming · atStore · route · back
    state: str
    status_label: str
    stops: tuple[DeliveryStopProjection, ...]
    driver: DeliveryDriverProjection | None = None
    position: DeliveryPointProjection | None = None
    called_at: str = ""
    called_by: str = ""
    pickup_eta_at: str = ""
    arrived_pickup_at: str = ""
    picked_up_at: str = ""
    delivery_eta_at: str = ""
    tracking_url: str = ""
    cost_display: str = ""
    #: Soma dos volumes declarados das paradas e quem ainda não declarou.
    bags: int = 0
    undeclared: tuple[str, ...] = ()
    #: O pedido pelo qual os gestos da corrida vão (o primeiro da corrida).
    lead_ref: str = ""
    #: "Entregador voltou" (``courier-back``) e o que a mão recebe.
    back_action: Action | None = None
    back_lines: tuple[str, ...] = ()
    #: Cancelar a corrida (``courier-cancel``), só antes da coleta. A confirmação
    #: traz a pergunta e, depois do aceite, os motivos (``confirmation.reasons``).
    cancel_action: Action | None = None
    #: O entregador desistiu e a TaOn procura outro para a MESMA corrida
    #: (``courier.reopen_view``): quando, e o nome de quem saiu (pode faltar).
    #: Só com ``state == "reopened"``.
    reopened_at: str = ""
    reopened_driver: str = ""
    #: O cancelamento pedido desta corrida: "" · pending · unknown · failed
    #: (``courier.cancel_state``, a mesma fonte do Painel do pedido) e a frase.
    cancel_state: str = ""
    cancel_message: str = ""
    #: Desde quando a TaOn não informa a corrida (``courier.progress_view``, o
    #: mesmo do Painel); vazio com a leitura em dia.
    sync_since: str = ""


@dataclass(frozen=True)
class DeliveriesProjection:
    origin: DeliveryPointProjection | None
    waiting: tuple[DeliveryStopProjection, ...]
    rides: tuple[DeliveryRideProjection, ...]
    max_stops: int
    #: Maquininhas livres para a corrida que leva cartão.
    machines: tuple[dict, ...] = field(default_factory=tuple)
    #: A integração com a TaOn está ligada (sem ela, a página só informa).
    courier_on: bool = True
    #: A chave PÚBLICA do Google Maps (a do navegador, a mesma do PDV e da loja):
    #: com ela o mapa é o de verdade; vazia, o desenho próprio fica no lugar.
    maps_key: str = ""
    #: Chamar UMA corrida para vários pedidos de Aguardando (``courier-ride``):
    #: quem a tela leu e a revisão de cada pedido que pode ir junto
    #: (``order_queue.courier_ride_action``). ``None`` com menos de dois.
    group_action: Action | None = None
    #: Os números de corrida livres agora, do menor ao maior (1 a 26, a letra e a
    #: cor de cada corrida; ``courier.free_ride_numbers``). É daqui que a tela
    #: tira o número das corridas em edição; quem grava é a chamada.
    free_numbers: tuple[int, ...] = ()
    #: O primeiro livre (``None`` quando as 26 letras estão ocupadas).
    next_number: int | None = None


def _point(address: dict) -> tuple[float | None, float | None]:
    try:
        return float(address["latitude"]), float(address["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _authorized(user) -> bool:
    return bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))


def _action(ref: str, label: str, revision: str, user, *, confirm: bool = True,
            confirmation: dict | None = None) -> Action:
    authorized = _authorized(user)
    return Action(
        ref=ref, kind="mutation", label=label, enabled=authorized,
        reason="" if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos.",
        method="POST", idempotency="required", confirmation=confirmation or {"required": confirm},
        payload_schema={"base_revision": revision, "expected_actor_id": getattr(user, "pk", None)},
    )


def _stop(order: Order, *, with_asks: bool = False, user=None) -> DeliveryStopProjection:
    from shopman.backstage.projections.order_queue import (
        COURIER_DISPATCH_AGAIN_CONFIRMATION,
        COURIER_NO_ANSWER_MESSAGE,
        _courier_change_fields,
        _declared_volumes,
    )
    from shopman.shop.services import courier, operator_orders

    data = order.data or {}
    address = data.get("delivery_address_structured") or {}
    latitude, longitude = _point(address)
    customer = str((data.get("customer") or {}).get("name") or "").strip()
    place = str(address.get("neighborhood") or "").strip()
    street = " ".join(p for p in (str(address.get("route") or ""), str(address.get("street_number") or "")) if p).strip()
    asks = operator_orders.partner_custody_asks(order) if with_asks else {}
    change_q = int(asks.get("change_out_suggested_q") or 0)
    block = courier.get_block(order)
    error = block.get("error") if isinstance(block.get("error"), dict) else {}
    message = str(error.get("message") or "")
    callable_here = with_asks and courier.is_enabled_for(order) and not courier.has_active_ride(order)
    # A chamada sem resposta trava qualquer outra (não se sabe se a corrida abriu
    # lá): a mesma regra e a mesma frase do Painel (``order_queue._courier_block``).
    unresolved = courier.unresolved_dispatch(order) is not None if callable_here else False
    if unresolved:
        message = COURIER_NO_ANSWER_MESSAGE
    return DeliveryStopProjection(
        ref=order.ref,
        code=operator_orders.short_ref(order.ref),
        customer=customer,
        place=place or street or str(data.get("delivery_address") or ""),
        address=" · ".join(p for p in (street or str(address.get("formatted_address") or ""), place) if p),
        latitude=latitude,
        longitude=longitude,
        stage="Pronto" if order.status == Order.Status.READY else "Em preparo",
        volumes=_declared_volumes(order),
        done=order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED),
        change_out_suggested_q=change_q,
        needs_machine=bool(asks.get("needs_machine")),
        change_label=_courier_change_fields(order).get("change_label", "") if change_q else "",
        group_refusal=courier.group_refusal(order) if with_asks else "",
        error=message if with_asks else "",
        dispatch_action=_action("courier-dispatch", "Chamar sozinho", courier.dispatch_revision(order), user)
        if callable_here and not unresolved else None,
        dispatch_again_action=_action(
            "courier-dispatch-again", "Chamar de novo", courier.dispatch_revision(order), user,
            confirmation={"required": True, "description": COURIER_DISPATCH_AGAIN_CONFIRMATION},
        ) if unresolved else None,
        charge_outdated=None if with_asks else courier.charge_outdated(order),
    )


def _minutes_since(iso: str) -> float | None:
    moment = parse_datetime(iso) if iso else None
    if moment is None:
        return None
    return (timezone.now() - moment).total_seconds() / 60


def _state(block: dict, progress: dict, *, back: bool) -> str:
    from shopman.shop.services import courier

    status = str(block.get("status") or "")
    if back:
        return "back"
    if block.get("id_mch") and status == "U":
        # A própria TaOn juntou esta corrida a outra, que já tem entregador:
        # nunca é "Ninguém aceitou", e não há o que chamar de novo.
        return "grouped"
    if courier.reopen_view(block)["at"]:
        # O entregador desistiu e a TaOn já redistribui a mesma corrida: a
        # espera conta de novo, e chamar outra seria pagar duas.
        return "reopened"
    if not block.get("id_mch") or status in ("D", "G", "P"):
        waited = _minutes_since(str(block.get("called_at") or block.get("requested_at") or ""))
        return "late" if waited is not None and waited >= LATE_SEARCH_MINUTES else "searching"
    if status in ("A", "S"):
        return "atStore" if progress.get("arrived_pickup_at") else "coming"
    return "route"


_STATE_LABELS = {
    "searching": "Procurando entregador",
    "late": "Ninguém aceitou ainda",
    "reopened": "Procurando outro entregador",
    "grouped": "Junto com outra corrida",
    "coming": "Entregador a caminho da loja",
    "atStore": "Entregador na loja",
    "route": "Em rota",
    "back": "Tudo entregue",
}


def _ride(orders: list[Order], *, user=None) -> DeliveryRideProjection:
    from shopman.backstage.projections.order_queue import (
        _money,
        _trip_fields,
        courier_can_cancel,
        courier_cancel_confirmation,
        courier_cancel_state,
    )
    from shopman.shop.services import courier, operator_orders

    by_ref = {order.ref: order for order in orders}
    lead = orders[0]
    block = courier.get_block(lead)
    sequence = [ref for ref in courier.ride_orders(lead) if ref in by_ref]
    sequence += [order.ref for order in orders if order.ref not in sequence]
    stops = tuple(_stop(by_ref[ref]) for ref in sequence)
    progress = courier.progress_view(block)
    back_members = operator_orders.courier_return_members(lead) if str(block.get("status") or "") == "F" else []
    back = bool(back_members)
    state = _state(block, progress, back=back)
    raw_driver = block.get("driver") if isinstance(block.get("driver"), dict) else None
    driver = None
    if raw_driver and raw_driver.get("name"):
        vehicle = " · ".join(p for p in (str(raw_driver.get("vehicle_model") or ""), str(raw_driver.get("vehicle_plate") or "")) if p)
        driver = DeliveryDriverProjection(name=str(raw_driver["name"]), phone=str(raw_driver.get("phone") or ""), vehicle=vehicle)
    position = None
    if block.get("id_mch") and state in ("coming", "atStore", "route"):
        cached = cache.get(f"courier:pos:{block['id_mch']}")
        if isinstance(cached, dict) and cached.get("lat") is not None and cached.get("lng") is not None:
            try:
                position = DeliveryPointProjection(latitude=float(cached["lat"]), longitude=float(cached["lng"]))
            except (TypeError, ValueError):
                position = None
    estimate = block.get("estimate") if isinstance(block.get("estimate"), dict) else {}
    cost_q = block.get("final_value_q") if block.get("final_value_q") is not None else estimate.get("value_q")
    pending = [stop for stop in stops if not stop.done]
    trip = _trip_fields(lead) if back else {}
    cancel = courier_cancel_state(lead)
    can_cancel = courier_can_cancel(lead, cancel)
    reopened = courier.reopen_view(block) if state == "reopened" else {"at": "", "driver": ""}
    return DeliveryRideProjection(
        key=str(block.get("id_mch") or f"call:{lead.ref}"),
        number=int(block.get("ride_number") or 0),
        letter=courier.ride_letter(block.get("ride_number")),
        state=state,
        status_label=_STATE_LABELS[state],
        stops=stops,
        driver=driver,
        position=position,
        called_at=str(block.get("called_at") or ""),
        called_by=str(block.get("called_by") or ""),
        pickup_eta_at=progress.get("pickup_eta_at", ""),
        arrived_pickup_at=progress.get("arrived_pickup_at", ""),
        picked_up_at=progress.get("picked_up_at", ""),
        delivery_eta_at=progress.get("delivery_eta_at", ""),
        # O link é de UMA parada. Com várias, "o link da corrida" seria o de um
        # cliente só, pronto para ser copiado para outro: não aparece.
        tracking_url=courier.proven_tracking(block)["url"] if len(stops) == 1 else "",
        cost_display=_money(int(cost_q)) if isinstance(cost_q, int) and cost_q > 0 else "",
        bags=sum(stop.volumes for stop in pending),
        undeclared=tuple(stop.code for stop in pending if not stop.volumes),
        lead_ref=lead.ref,
        back_action=_action("courier-back", "Entregador voltou", operator_orders.trip_revision(lead), user) if back else None,
        back_lines=tuple(trip.get("courier_return_lines", ())),
        cancel_action=_action("courier-cancel", "Cancelar corrida", courier.dispatch_revision(lead), user,
                              confirmation=courier_cancel_confirmation(lead)) if can_cancel else None,
        cancel_state=cancel["state"],
        cancel_message=cancel["message"],
        reopened_at=reopened["at"],
        reopened_driver=reopened["driver"],
        sync_since=progress.get("sync_since", ""),
    )


def build_deliveries(*, user=None) -> DeliveriesProjection:
    from shopman.backstage.models import DeliveryDevice
    from shopman.backstage.projections.order_queue import _is_delivery, _is_future_preorder, courier_ride_action
    from shopman.backstage.services.delivery_devices import PREFIX
    from shopman.shop.models import Shop
    from shopman.shop.services import courier, delivery_services
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    shop = Shop.load()
    origin = None
    if shop is not None and shop.latitude is not None and shop.longitude is not None:
        origin = DeliveryPointProjection(latitude=float(shop.latitude), longitude=float(shop.longitude))

    statuses = (*courier.RIDE_ORDER_STATUSES, Order.Status.DISPATCHED, Order.Status.DELIVERED)
    orders = [
        order for order in Order.objects.filter(status__in=statuses).order_by("created_at")
        if _is_delivery(order) and not is_pos_counter_order(order) and courier.house_dispatches(order)
    ]
    rides: dict[str, list[Order]] = {}
    waiting: list[Order] = []
    for order in orders:
        block = courier.get_block(order)
        if block.get("ride_number") and courier.ride_is_live(order):
            key = str(block.get("id_mch") or f"call:{block.get('ride_number')}:{block.get('called_at') or order.ref}")
            rides.setdefault(key, []).append(order)
        elif order.status in courier.RIDE_ORDER_STATUSES and not _is_future_preorder(order):
            waiting.append(order)
    waiting.sort(key=lambda order: order.status != Order.Status.READY)
    ride_rows = sorted((_ride(group, user=user) for group in rides.values()), key=lambda ride: (ride.number or 99, ride.called_at))
    devices = DeliveryDevice.objects.filter(active=True, current_order__isnull=True)
    stops = tuple(_stop(order, with_asks=True, user=user) for order in waiting)
    joinable = {stop.ref for stop in stops if not stop.group_refusal}
    free_numbers = tuple(courier.free_ride_numbers())
    return DeliveriesProjection(
        origin=origin,
        waiting=stops,
        rides=tuple(ride_rows),
        max_stops=courier.MAX_RIDE_STOPS,
        machines=tuple({"ref": PREFIX + str(device.ref), "label": device.label} for device in devices),
        courier_on=delivery_services.courier_backend() is not None,
        maps_key=browser_api_key(),
        group_action=courier_ride_action([order for order in waiting if order.ref in joinable], user=user),
        free_numbers=free_numbers,
        next_number=free_numbers[0] if free_numbers else None,
    )


def deliveries_waiting_count() -> int:
    """O selo de Entregas no menu: entregas do dia sem corrida chamada."""
    try:
        return len(build_deliveries().waiting)
    except Exception:  # o selo nunca derruba o menu
        logger.warning("deliveries.waiting_count_failed", exc_info=True)
        return 0
