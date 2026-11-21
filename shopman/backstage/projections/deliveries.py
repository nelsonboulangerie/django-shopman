"""Projection da seção Entregas do Gestor: as corridas da TaOn num lugar só.

Três partes, as mesmas no mapa e na coluna (desenho do dono, 14/11/2026, PR #2462):

- **Aguardando**: entregas do dia, prontas ou em preparo, que a casa despacha e
  que ainda não têm corrida chamada. É o que o operador junta em corridas.
- **Editando**: não mora aqui. É estado da tela (as corridas que o operador
  está juntando antes de chamar), nada é gravado até o "Chamar".
- **Corridas**: as chamadas e vivas, agrupadas pela corrida da TaOn (``ride_ref``),
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

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order

from shopman.backstage.projections.courier_position import (
    DeliveryCourierPositionProjection,
    courier_position_projection,
)
from shopman.backstage.projections.house_rides import DeliveryHouseRideProjection, house_ride
from shopman.shop.google_maps_credentials import browser_api_key
from shopman.shop.projections.types import Action
from shopman.shop.protocols import RideState
from shopman.shop.services import delivery_services

logger = logging.getLogger(__name__)

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
    #: A NFC-e do pedido, a MESMA chave da pílula do cartão (``order_queue._FISCAL_PILL``):
    #: ``failed`` pede o "Reprocessar NFC-e" no pedido. Só avisa: nunca segura a
    #: chamada nem a saída (dono, 17/09/2026).
    fiscal_status: str = ""
    #: A DANFE da NFC-e, os MESMOS campos do cartão (``services/order_danfe``):
    #: ``not_printed`` é a DANFE por imprimir, e ``danfe_problem`` diz por quê.
    danfe_state: str = ""
    danfe_problem: str = ""


@dataclass(frozen=True)
class DeliveryDriverProjection:
    name: str
    phone: str
    #: "Honda CG prata · ABC1D23": modelo e cor juntos, a placa depois.
    vehicle: str
    #: A foto do entregador, servida pelo servidor (``deliveries/<corrida>/driver-photo/``)
    #: só enquanto a corrida vive. Vazio sem foto: a tela mostra a inicial.
    photo_url: str = ""


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
    #: O nome do serviço da corrida como o cadastro diz ("TaOn"), para as frases da tela.
    service_name: str = ""
    position: DeliveryCourierPositionProjection | None = None
    called_at: str = ""
    called_by: str = ""
    pickup_eta_at: str = ""
    #: A TaOn avisou que o entregador está nas redondezas da loja (``AN``).
    near_pickup_at: str = ""
    arrived_pickup_at: str = ""
    #: A TaOn avisou que o entregador espera na loja além do combinado (``AW``).
    waited_pickup_at: str = ""
    picked_up_at: str = ""
    delivery_eta_at: str = ""
    tracking_url: str = ""
    cost_display: str = ""
    # "Valor pago à TaOn" (o valor final dela) ou "Cotação da corrida" (a cotação da
    # rota inteira, gravada na chamada). Vazio quando não há número honesto (J13).
    cost_label: str = ""
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
    #: ``withdrew`` (o entregador desistiu) ou ``transfer`` (a TaOn trocou o entregador).
    reopened_reason: str = ""
    #: Antes da coleta, o que vai na mão do entregador e o que conferir:
    #: "Leva a maquininha e o troco. Confira a placa antes de entregar."
    custody_line: str = ""
    #: A corrida passou da idade em que se acompanha de perto
    #: (``courier.ride_open_too_long``): a leitura segue lenta e a tela avisa.
    open_too_long: bool = False
    #: O cancelamento pedido desta corrida: "" · pending · unknown · failed
    #: (``courier.cancel_state``, a mesma fonte do Painel do pedido) e a frase.
    cancel_state: str = ""
    cancel_message: str = ""
    #: Desde quando a TaOn não informa a corrida (``courier.progress_view``, o
    #: mesmo do Painel); vazio com a leitura em dia.
    sync_since: str = ""
    #: A corrida da casa (quem leva, o link e os gestos do balcão); None na TaOn
    #: (``house_rides.house_ride``, M3b #2898).
    house: DeliveryHouseRideProjection | None = None


@dataclass(frozen=True)
class RideSuggestionProjection:
    """Uma corrida que a casa sugere juntar (``ride_plan``), no topo de Aguardando."""

    #: Os refs em ordem, juntos por "+": identifica a sugestão (o "Agora não" esconde por ela).
    key: str
    #: As paradas na ordem do percurso (a da cotação, quando veio).
    refs: tuple[str, ...]
    codes: tuple[str, ...]
    #: Os bairros, sem repetir: "Gleba Palhano, Centro".
    places: str
    #: Todas as cotações vieram (a da corrida junta e a de cada pedido sozinho).
    quoted: bool
    #: Cotada e mais barata junta pela régua do Admin: vem marcada.
    suggested: bool
    #: Quem mais espera a mais com a corrida junta, e quantos minutos.
    late_code: str
    late_minutes: int
    #: A cotação junta (centavos, minutos, km) e a soma das sozinhas; ``None`` sem cotação.
    together_q: int | None = None
    minutes: int | None = None
    km: float | None = None
    with_return: bool = False
    separate_q: int | None = None
    saving_q: int | None = None


@dataclass(frozen=True)
class DeliveryServiceOptionProjection:
    ref: str
    name: str
    kind: str
    is_default: bool


@dataclass(frozen=True)
class RidePlanProjection:
    """O plano das corridas (``ride_plan``): o MESMO do sheet de chamar e do Painel.

    ``service`` é o serviço sugerido (o padrão do Admin), ``service_reason`` diz por quê
    (``default``) e ``service_options`` são os serviços ativos: o contrato com a frente
    M3 ("Quem leva", #2526).
    """

    suggestions: tuple[RideSuggestionProjection, ...] = ()
    service: str = ""
    service_reason: str = ""
    service_options: tuple[DeliveryServiceOptionProjection, ...] = ()


@dataclass(frozen=True)
class DeliveriesProjection:
    origin: DeliveryPointProjection | None
    waiting: tuple[DeliveryStopProjection, ...]
    rides: tuple[DeliveryRideProjection, ...]
    max_stops: int
    #: Maquininhas livres para a corrida que leva cartão.
    machines: tuple[dict, ...] = field(default_factory=tuple)
    #: A integração com a TaOn está ligada.
    courier_on: bool = True
    #: Os entregadores da casa estão ativos (M3c, #2899): com eles a página funciona
    #: mesmo sem a TaOn; sem nenhum dos dois, a página só informa.
    house_on: bool = False
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
    #: As corridas que a casa sugere juntar (``ride_plan``). ``None`` no selo do menu,
    #: que nunca pergunta à central.
    ride_plan: RidePlanProjection | None = None


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


@dataclass(frozen=True)
class _Reads:
    """O que a página lê em lote, uma consulta por fonte, nunca uma por pedido."""

    #: As tarefas de despacho de cada pedido (``courier.dispatch_tasks_for``).
    tasks: dict
    #: A evidência fiscal (``order_queue._fiscal_states_for``).
    fiscal: object = None
    #: A última DANFE de cada pedido e o destino (``order_danfe.read_for``).
    danfe: object = None


def _ride_cost(block: dict, stop_refs: list[str]) -> tuple[int, str]:
    """O custo da corrida que a tela pode afirmar, e o nome dele (J13).

    O valor final do serviço vale sempre ("Valor pago à TaOn"). Sem ele, vale a cotação,
    mas só a da MESMA rota: numa corrida com várias paradas, a cotação sozinha do
    principal (a de antes de juntar) mentia o custo. A cotação da rota grava as
    paradas (``estimate.stops``) e só vale quando elas são as da corrida.
    """
    final = block.get("final_value_q")
    if isinstance(final, int) and final > 0:
        return final, f"Valor pago à {delivery_services.service_name(block)}"
    estimate = block.get("estimate") if isinstance(block.get("estimate"), dict) else {}
    value = estimate.get("value_q")
    if not isinstance(value, int) or value <= 0:
        return 0, ""
    quoted = estimate.get("stops")
    if len(stop_refs) > 1 and sorted(quoted or []) != sorted(stop_refs):
        return 0, ""
    return value, "Cotação da corrida"


def _stop(order: Order, *, reads: _Reads, with_asks: bool = False, user=None) -> DeliveryStopProjection:
    from shopman.backstage.projections.order_queue import (
        _courier_change_fields,
        _declared_volumes,
        _fiscal_status,
        courier_dispatch_again_confirmation,
        courier_no_answer_message,
    )
    from shopman.backstage.services import order_danfe
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
    # Sem a TaOn, a casa ainda chama pelos próprios entregadores (M3c, #2899).
    callable_here = with_asks and (courier.is_enabled_for(order) or _house_callable(order)) \
        and not courier.has_active_ride(order)
    # A chamada sem resposta trava qualquer outra (não se sabe se a corrida abriu
    # lá): a mesma regra e a mesma frase do Painel (``order_queue._courier_block``).
    unresolved = courier.unresolved_dispatch(order, tasks=reads.tasks) is not None if callable_here else False
    fiscal_status = _fiscal_status(
        order,
        directive_status=reads.fiscal.directive_status.get(order.ref, ""),
        emit_failed_alert=order.ref in reads.fiscal.failed_alert_refs,
    )[0]
    danfe = order_danfe.card_state(order, reads=reads.danfe)
    if unresolved:
        message = courier_no_answer_message(delivery_services.service_name(block))
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
        group_refusal=courier.group_refusal(order, tasks=reads.tasks) if with_asks else "",
        error=message if with_asks else "",
        dispatch_action=_action("courier-dispatch", "Chamar sozinho", courier.dispatch_revision(order), user)
        if callable_here and not unresolved else None,
        dispatch_again_action=_action(
            "courier-dispatch-again", "Chamar de novo", courier.dispatch_revision(order), user,
            confirmation={"required": True, "description": courier_dispatch_again_confirmation(
                delivery_services.service_name(block))},
        ) if unresolved else None,
        charge_outdated=None if with_asks else courier.charge_outdated(order),
        fiscal_status=fiscal_status,
        danfe_state=danfe.state,
        danfe_problem=danfe.problem,
    )


def _minutes_since(iso: str) -> float | None:
    moment = parse_datetime(iso) if iso else None
    if moment is None:
        return None
    return (timezone.now() - moment).total_seconds() / 60


def _state(block: dict, progress: dict, *, back: bool) -> str:
    from shopman.shop.services import courier

    # O estado da casa, não a letra do serviço (M1b-b, #2552).
    state = delivery_services.ride_state(block)
    if back:
        return "back"
    if block.get("ride_ref") and state == RideState.GROUPED:
        # A própria TaOn juntou esta corrida a outra, que já tem entregador:
        # nunca é "Ninguém aceitou", e não há o que chamar de novo.
        return "grouped"
    if courier.reopen_view(block)["at"]:
        # O entregador desistiu e a TaOn já redistribui a mesma corrida: a
        # espera conta de novo, e chamar outra seria pagar duas.
        return "reopened"
    if not block.get("ride_ref") or state == RideState.SEARCHING:
        waited = _minutes_since(str(block.get("called_at") or block.get("requested_at") or ""))
        return "late" if waited is not None and waited >= courier.LATE_SEARCH_MINUTES else "searching"
    if state == RideState.ASSIGNED:
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


def _ride(orders: list[Order], *, reads: _Reads, user=None) -> DeliveryRideProjection:
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
    stops = tuple(_stop(by_ref[ref], reads=reads) for ref in sequence)
    progress = courier.progress_view(block)
    back_members = (operator_orders.courier_return_members(lead)
                    if delivery_services.ride_state(block) == RideState.DONE else [])
    back = bool(back_members)
    state = _state(block, progress, back=back)
    raw_driver = block.get("driver") if isinstance(block.get("driver"), dict) else None
    driver = None
    if raw_driver and raw_driver.get("name"):
        ride_id = str(block.get("ride_ref") or "")
        driver = DeliveryDriverProjection(
            name=str(raw_driver["name"]),
            phone=str(raw_driver.get("phone") or ""),
            vehicle=courier.vehicle_line(raw_driver),
            photo_url=(f"/api/v1/backstage/deliveries/{ride_id}/driver-photo/"
                       if state in ("coming", "atStore", "route") and courier.has_driver_photo(ride_id) else ""),
        )
    position = None
    if block.get("ride_ref") and state in ("coming", "atStore", "route"):
        position = courier_position_projection(block["ride_ref"], service=delivery_services.service_name(block))
    # A cotação da rota mora no pedido que abriu a corrida, que nem sempre é o
    # primeiro da fila: vale a primeira parada que tem um custo honesto.
    stop_refs = [stop.ref for stop in stops]
    cost_q, cost_label = next(
        (found for found in (_ride_cost(courier.get_block(by_ref[ref]), stop_refs) for ref in sequence) if found[0]),
        (0, ""),
    )
    pending = [stop for stop in stops if not stop.done]
    trip = _trip_fields(lead) if back else {}
    cancel = courier_cancel_state(lead)
    can_cancel = courier_can_cancel(lead, cancel)
    reopened = courier.reopen_view(block) if state == "reopened" else {"at": "", "driver": "", "reason": ""}
    custody_line = (_custody_line([by_ref[ref] for ref in sequence])
                    if driver is not None and state in ("coming", "atStore") else "")
    return DeliveryRideProjection(
        key=str(block.get("ride_ref") or f"call:{lead.ref}"),
        number=int(block.get("ride_number") or 0),
        letter=courier.ride_letter(block.get("ride_number")),
        state=state,
        status_label=_STATE_LABELS[state],
        stops=stops,
        driver=driver,
        service_name=delivery_services.service_name(block),
        position=position,
        called_at=str(block.get("called_at") or ""),
        called_by=str(block.get("called_by") or ""),
        pickup_eta_at=progress.get("pickup_eta_at", ""),
        near_pickup_at=progress.get("near_pickup_at", ""),
        arrived_pickup_at=progress.get("arrived_pickup_at", ""),
        waited_pickup_at=progress.get("waited_pickup_at", ""),
        picked_up_at=progress.get("picked_up_at", ""),
        delivery_eta_at=progress.get("delivery_eta_at", ""),
        # O link é de UMA parada. Com várias, "o link da corrida" seria o de um
        # cliente só, pronto para ser copiado para outro: não aparece.
        tracking_url=courier.proven_tracking(block)["url"] if len(stops) == 1 else "",
        cost_display=_money(cost_q) if cost_q else "",
        cost_label=cost_label if cost_q else "",
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
        reopened_reason=reopened["reason"],
        custody_line=custody_line,
        open_too_long=courier.ride_open_too_long(block),
        sync_since=progress.get("sync_since", ""),
        house=house_ride(lead, user=user),
    )


def _custody_line(orders: list[Order]) -> str:
    """O que sai com o entregador da TaOn nesta corrida, e a conferência que isso pede.

    Só a maquininha e o troco que de fato saíram (a custódia registrada na
    chamada): quem leva dinheiro ou equipamento da casa é conferido pela placa.
    """
    from shopman.shop.services import operator_orders

    machine = any(operator_orders.equipment_custody(order).pending for order in orders)
    change = any(operator_orders.courier_change(order).pending for order in orders)
    things = " e ".join(word for word, out in (("a maquininha", machine), ("o troco", change)) if out)
    return f"Leva {things}. Confira a placa antes de entregar." if things else ""


def _delivery_orders() -> list[Order]:
    """As entregas que a casa despacha, nos estados em que a página as mostra.

    UMA consulta: o resto (entrega? balcão do PDV? quem leva?) é leitura do
    ``Order.data`` já carregado.
    """
    from shopman.backstage.projections.order_queue import _is_delivery
    from shopman.shop.services import courier
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    statuses = (*courier.RIDE_ORDER_STATUSES, Order.Status.DISPATCHED, Order.Status.DELIVERED)
    return [
        order for order in Order.objects.filter(status__in=statuses).order_by("created_at")
        if _is_delivery(order) and not is_pos_counter_order(order) and courier.house_dispatches(order)
    ]


def _split(orders: list[Order], tasks: dict) -> tuple[dict[str, list[Order]], list[Order]]:
    """As corridas vivas (por corrida) e o que aguarda entregador."""
    from shopman.backstage.projections.order_queue import _is_future_preorder
    from shopman.shop.services import courier

    today = timezone.localdate()
    rides: dict[str, list[Order]] = {}
    waiting: list[Order] = []
    for order in orders:
        block = courier.get_block(order)
        if block.get("ride_number") and courier.ride_is_live(order, tasks=tasks):
            key = str(block.get("ride_ref") or f"call:{block.get('ride_number')}:{block.get('called_at') or order.ref}")
            rides.setdefault(key, []).append(order)
        elif order.status in courier.RIDE_ORDER_STATUSES and not _is_future_preorder(order, today=today):
            waiting.append(order)
    return rides, waiting


def _tasks_needed(orders: list[Order]) -> list[Order]:
    """Os pedidos cuja leitura pergunta pelas tarefas de despacho.

    Os que têm corrida chamada sem resposta da central ainda (``ride_is_live``) e
    os que aguardam entregador (o "Chamar de novo", ``unresolved_dispatch``).
    """
    from shopman.shop.services import courier

    needed = []
    for order in orders:
        block = courier.get_block(order)
        if not block.get("ride_ref") or order.status in courier.RIDE_ORDER_STATUSES:
            needed.append(order)
    return needed


def _ride_plan(waiting: list[Order], stops: tuple[DeliveryStopProjection, ...], *, tasks: dict) -> RidePlanProjection:
    from shopman.shop.services import ride_plan

    try:
        plan = ride_plan.ride_plan(waiting, tasks=tasks)
    except Exception:  # o plano nunca derruba a página: sem ele, monta-se à mão
        logger.warning("deliveries.ride_plan_failed", exc_info=True)
        plan = {"suggestions": [], **ride_plan._service()}
    places = {stop.ref: stop.place for stop in stops}
    suggestions = []
    for item in plan["suggestions"]:
        together = item.get("together") or {}
        suggestions.append(RideSuggestionProjection(
            key=item["key"],
            refs=tuple(item["refs"]),
            codes=tuple(item["codes"]),
            places=", ".join(dict.fromkeys(places[ref] for ref in item["refs"] if places.get(ref))),
            quoted=bool(item["quoted"]),
            suggested=bool(item["suggested"]),
            late_code=item["late_code"],
            late_minutes=int(item["late_minutes"]),
            together_q=together.get("value_q"),
            minutes=round(together["minutes"]) if together.get("minutes") is not None else None,
            km=together.get("km"),
            with_return=bool(together.get("with_return")),
            separate_q=item.get("separate_q"),
            saving_q=item.get("saving_q"),
        ))
    return RidePlanProjection(
        suggestions=tuple(suggestions),
        service=plan["service"],
        service_reason=plan["service_reason"],
        service_options=tuple(DeliveryServiceOptionProjection(**option) for option in plan["service_options"]),
    )


def build_deliveries(*, user=None, with_plan: bool = True) -> DeliveriesProjection:
    from shopman.backstage.models import DeliveryDevice
    from shopman.backstage.projections.order_queue import _fiscal_states_for, courier_ride_action
    from shopman.backstage.services import order_danfe
    from shopman.backstage.services.delivery_devices import PREFIX
    from shopman.shop.models import Shop
    from shopman.shop.services import courier, delivery_services

    shop = Shop.load()
    origin = None
    if shop is not None and shop.latitude is not None and shop.longitude is not None:
        origin = DeliveryPointProjection(latitude=float(shop.latitude), longitude=float(shop.longitude))

    orders = _delivery_orders()
    # As tarefas de despacho, a NFC-e e a DANFE em lote: uma consulta por fonte.
    reads = _Reads(
        tasks=courier.dispatch_tasks_for(_tasks_needed(orders)),
        fiscal=_fiscal_states_for(orders),
        danfe=order_danfe.read_for(orders),
    )
    rides, waiting = _split(orders, reads.tasks)
    waiting.sort(key=lambda order: order.status != Order.Status.READY)
    ride_rows = sorted((_ride(group, reads=reads, user=user) for group in rides.values()), key=lambda ride: (ride.number or 99, ride.called_at))
    devices = DeliveryDevice.objects.filter(active=True, current_order__isnull=True)
    stops = tuple(_stop(order, reads=reads, with_asks=True, user=user) for order in waiting)
    joinable = {stop.ref for stop in stops if not stop.group_refusal}
    free_numbers = tuple(courier.free_ride_numbers())
    return DeliveriesProjection(
        origin=origin,
        waiting=stops,
        rides=tuple(ride_rows),
        max_stops=courier.MAX_RIDE_STOPS,
        machines=tuple({"ref": PREFIX + str(device.ref), "label": device.label} for device in devices),
        courier_on=delivery_services.courier_backend() is not None,
        house_on=_house_on(),
        maps_key=browser_api_key(),
        group_action=courier_ride_action([order for order in waiting if order.ref in joinable], user=user),
        free_numbers=free_numbers,
        next_number=free_numbers[0] if free_numbers else None,
        ride_plan=_ride_plan(waiting, stops, tasks=reads.tasks) if with_plan else None,
    )


def _house_on() -> bool:
    from shopman.backstage.services.house_couriers import own_service

    return own_service() is not None


def _house_callable(order) -> bool:
    """Entrega da casa que um entregador da casa pode levar (serviço da casa ativo)."""
    from shopman.shop.services import courier
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return _house_on() and get_fulfillment_type(order) == "delivery" and courier.house_dispatches(order)


def deliveries_waiting_count() -> int | None:
    """O selo de Entregas no menu: entregas do dia sem corrida chamada.

    A MESMA régua da lista Aguardando (``_split``), sem montar a página: uma
    consulta de pedidos e, só quando há corrida chamada à espera da central,
    uma das tarefas de despacho, em lote. Se a leitura falhar, ``None``: a tela
    mostra "?", nunca um zero que diria "nada aguardando".
    """
    from shopman.shop.services import courier

    try:
        orders = _delivery_orders()
        pending = [
            order for order in orders
            if courier.get_block(order).get("ride_number") and not courier.get_block(order).get("ride_ref")
        ]
        tasks = courier.dispatch_tasks_for(pending) if pending else {}
        return len(_split(orders, tasks)[1])
    except Exception:  # o selo nunca derruba o menu
        logger.warning("deliveries.waiting_count_failed", exc_info=True)
        return None


def deliveries_waiting_summary() -> dict:
    """O selo de Entregas e o "Chamar entregador" do cartão Pronto (#2876).

    ``{waiting, call_refs}``: ``waiting`` é o selo (:func:`deliveries_waiting_count`,
    ``None`` quando a leitura falhou) e ``call_refs`` os pedidos PRONTOS de Aguardando
    que dá para chamar daqui agora, com a régua da lista (``_stop``): um serviço que
    leva (a TaOn ou a casa), sem corrida viva e sem chamada sem resposta. Só com algum
    pronto lê as tarefas de despacho, em lote.
    """
    from shopman.shop.services import courier

    waiting = deliveries_waiting_count()
    if not waiting:
        return {"waiting": waiting, "call_refs": []}
    try:
        orders = _delivery_orders()
        ready = [order for order in _split(orders, courier.dispatch_tasks_for(_tasks_needed(orders)))[1]
                 if order.status == Order.Status.READY]
        callable_now = [order for order in ready
                        if (courier.is_enabled_for(order) or _house_callable(order))
                        and not courier.has_active_ride(order)]
        tasks = courier.dispatch_tasks_for(callable_now) if callable_now else {}
        refs = [order.ref for order in callable_now if courier.unresolved_dispatch(order, tasks=tasks) is None]
    except Exception:  # o botão nunca derruba o menu: sem a lista, o cartão fica como era
        logger.warning("deliveries.call_refs_failed", exc_info=True)
        refs = []
    return {"waiting": waiting, "call_refs": refs}
