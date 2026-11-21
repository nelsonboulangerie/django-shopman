"""A corrida do entregador da casa, de ponta a ponta (DEV-2026-030, frente M2).

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §4 e §4.5.2 (telas aprovadas pelo dono
em 16/11/2026). O operador designa a rota a uma pessoa da casa (``assign``); ela recebe o
link (``courier_links``) e avança pelos toques: "Saí da loja" (``depart``), "Entreguei"
por parada (``deliver``) e "Problema" (``report_problem``). Quem fecha a rota é o balcão,
no "Entregador voltou" de sempre.

Nada aqui fala com o funil de outro jeito: as transições entram por
``courier.apply_status`` com as letras internas (``A``, ``E``, ``F``), e a custódia do troco
e da maquininha pela mesma ``operator_orders.record_partner_custody`` da TaOn.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models.delivery_service import Courier, CourierLink, DeliveryService
from shopman.shop.services import courier, courier_links

logger = logging.getLogger(__name__)

#: Fonte das transições que vêm do link (aparece na trilha do pedido).
SOURCE = "courier_link"

#: Os casos da folha "Problema" (tela aprovada, §4.5.2).
OTHER_PAYMENT = "other_payment"
NO_ANSWER = "no_answer"
ADDRESS_NOT_FOUND = "address_not_found"
REFUSED = "refused"
ORDER_PROBLEM = "order_problem"
PROBLEMS = {
    OTHER_PAYMENT: "Pagou de outro jeito",
    NO_ANSWER: "Ninguém atendeu",
    ADDRESS_NOT_FOUND: "Não achei o endereço",
    REFUSED: "Recusou o pedido",
    ORDER_PROBLEM: "Pedido com problema",
}
#: Como pagou, quando pagou de outro jeito. Pix só pela maquininha (ele não confere outro).
PAYMENT_METHODS = {"card": "No cartão, na maquininha", "pix": "No Pix, na maquininha", "cash": "Em dinheiro"}


#: O tamanho da observação da casa para o entregador.
NOTE_MAX = 200


class OwnFleetRefused(ValueError):
    """A ação não pode acontecer agora; a mensagem é a que a tela mostra."""


@dataclass(frozen=True)
class Assignment:
    ride_ref: str
    link: CourierLink


def _order_label(order) -> str:
    from shopman.shop.services.operator_orders import short_ref

    return short_ref(order.ref)


@transaction.atomic
def assign(orders: list[Order], courier_person: Courier, *, actor: str, change_out: dict[str, int] | None = None,
           cash_shift=None, equipment: list[str] | None = None, ride_number: int | None = None,
           note: str = "") -> Assignment:
    """Designa a rota a um entregador da casa e emite o link dele.

    ``orders`` já vem na ordem da rota. Cada pedido grava o bloco ``courier`` da corrida da
    casa (``service`` = o serviço dos entregadores da casa, letra interna ``A``) e a
    custódia de troco e maquininha. A saída é a do primeiro pedido (``trip_ref``), e a
    maquininha é uma só para a rota. ``ride_number`` é o número (letra e cor) que a tela
    mostrava; vale se ainda estiver livre. ``note`` é a observação da casa para o entregador
    (a página do link mostra), até ``NOTE_MAX`` caracteres.
    """
    from shopman.shop.services import operator_orders

    service = courier_person.service
    if not courier_person.is_active or not service.is_active or service.kind != DeliveryService.KIND_OWN_FLEET:
        raise OwnFleetRefused(f"{courier_person.name} não está ativo como entregador da casa.")
    if not orders:
        raise OwnFleetRefused("Escolha pelo menos um pedido.")
    if len(orders) > courier.MAX_RIDE_STOPS:
        raise OwnFleetRefused(f"Cabem {courier.MAX_RIDE_STOPS} pedidos por rota.")
    locked = list(Order.objects.select_for_update().filter(pk__in=[o.pk for o in orders]))
    by_pk = {o.pk: o for o in locked}
    locked = [by_pk[o.pk] for o in orders]
    for order in locked:
        label = _order_label(order)
        if not courier.house_dispatches(order):
            raise OwnFleetRefused(f"{label} não é entrega da casa.")
        if order.status not in courier.RIDE_ORDER_STATUSES or order.status == Order.Status.DISPATCHED:
            raise OwnFleetRefused(f"{label} não está pronto para sair.")
        if courier.has_active_ride(order):
            raise OwnFleetRefused(f"{label} já tem corrida.")

    refs = [order.ref for order in locked]
    estimate = _estimate(locked, courier_person)
    ride_ref = f"{_RIDE_PREFIX()}{uuid.uuid4().hex[:10].upper()}"
    number = courier.next_ride_number(exclude_refs=refs, prefer=ride_number)
    now_iso = timezone.now().isoformat()
    driver = {"name": courier_person.name, "phone": courier_person.phone, "vehicle_model": courier_person.vehicle}
    trip_ref = refs[0] if len(refs) > 1 else ""
    shared_device: dict | None = None
    for order in locked:
        custody = operator_orders.record_partner_custody(
            order, actor=actor, change_out_q=(change_out or {}).get(order.ref), cash_shift=cash_shift,
            equipment=equipment if shared_device is None else None, trip_ref=trip_ref, shared_device=shared_device,
        )
        if custody.get("device_ref") and shared_device is None:
            shared_device = {"device_ref": custody["device_ref"], "device_label": custody.get("device_label", "")}
        order.refresh_from_db()
        block = dict(courier.get_block(order))
        if block.get("id_mch"):
            # Corrida anterior encerrada (N/C): vai para o histórico, como no "Chamar de novo".
            attempts = list(block.get("attempts") or [])
            attempts.append({k: block[k] for k in ("id_mch", "status", "requested_at", "status_at") if k in block})
            block = {"attempts": attempts}
        block.update(
            provider="own_fleet", service=service.ref, id_mch=ride_ref, status="A",
            status_at={"A": now_iso}, requested_at=now_iso, called_at=now_iso, called_by=actor,
            ride_number=number, driver=driver, courier_ref=courier_person.ref,
            last_event_at=now_iso, last_source=actor,
        )
        if len(refs) > 1:
            block["ride_orders"] = refs
        if note.strip():
            block["note"] = note.strip()[:NOTE_MAX]
        else:
            block.pop("note", None)
        if estimate is not None:
            block["estimate"] = {"value_q": estimate.value_q, "minutes": estimate.minutes, "km": estimate.km,
                                 "with_return": False}
        courier._save_block(order, block, emit={"kind": "status", "status": "A"})
        order.emit_event(event_type="courier_assigned", actor=actor,
                         payload={"id_mch": ride_ref, "courier": courier_person.ref})
    link = courier_links.issue(courier_person, ride_ref, refs)
    return Assignment(ride_ref=ride_ref, link=link)


def _estimate(orders: list[Order], courier_person: Courier):
    """O valor da rota pela tabela (combinado do entregador, ou a da casa). None sem coordenada."""
    from shopman.shop.adapters import courier_own_fleet
    from shopman.shop.models import Shop
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    shop = Shop.objects.first()
    if shop is None or shop.latitude is None or shop.longitude is None:
        return None
    places = []
    for order in orders:
        handoff = build_dispatch_payload(order)
        places.append({"lat": handoff.get("latitude"), "lng": handoff.get("longitude")})
    return courier_own_fleet.estimate(
        pickup={"lat": shop.latitude, "lng": shop.longitude}, dropoff=places[-1], stops=places[:-1],
        courier=courier_person,
    )


def _RIDE_PREFIX() -> str:
    from shopman.shop.adapters.courier_own_fleet import RIDE_PREFIX

    return RIDE_PREFIX


def _ride_orders(link: CourierLink) -> list[Order]:
    by_ref = {o.ref: o for o in Order.objects.filter(ref__in=link.order_refs)}
    return [by_ref[ref] for ref in link.order_refs if ref in by_ref]


def _live(order: Order, link: CourierLink) -> bool:
    return courier.get_block(order).get("id_mch") == link.ride_ref and order.status != Order.Status.CANCELLED


def depart(link: CourierLink) -> list[str]:
    """ "Saí da loja": todos os pedidos da rota saem para entrega. Só com todos prontos."""
    orders = [o for o in _ride_orders(link) if _live(o, link)]
    waiting = [_order_label(o) for o in orders if o.status != Order.Status.READY and courier.get_block(o).get("status") == "A"]
    if waiting:
        raise OwnFleetRefused(f"Espere {', '.join(waiting)} ficar pronto.")
    applied = []
    for order in orders:
        if courier.apply_status(order, "E", source=SOURCE) == "applied":
            applied.append(order.ref)
    return applied


def deliver(link: CourierLink, order_ref: str) -> bool:
    """ "Entreguei A47": só aquele pedido fica entregue, e o aviso vai só àquele cliente."""
    if order_ref not in link.order_refs:
        raise OwnFleetRefused("Este pedido não é desta rota.")
    order = Order.objects.get(ref=order_ref)
    if not _live(order, link):
        raise OwnFleetRefused("Este pedido saiu da rota.")
    if courier.get_block(order).get("status") != "E":
        raise OwnFleetRefused("Toque em Saí da loja antes de entregar.")
    value = (courier.get_block(order).get("estimate") or {}).get("value_q")
    details = {"final_value_q": value} if value is not None else None
    return courier.apply_status(order, "F", source=SOURCE, details=details) == "applied"


def report_problem(link: CourierLink, order_ref: str, kind: str, *, payment: str = "") -> None:
    """A folha "Problema": grava o caso no pedido e avisa o balcão. Nunca muda o pedido sozinha."""
    from shopman.shop.adapters import alert as alert_adapter

    if kind not in PROBLEMS:
        raise OwnFleetRefused("Escolha um dos casos.")
    if kind == OTHER_PAYMENT and payment not in PAYMENT_METHODS:
        raise OwnFleetRefused("Diga como pagou.")
    if order_ref not in link.order_refs:
        raise OwnFleetRefused("Este pedido não é desta rota.")
    with transaction.atomic():
        order = Order.objects.select_for_update().get(ref=order_ref)
        if not _live(order, link):
            raise OwnFleetRefused("Este pedido saiu da rota.")
        block = dict(courier.get_block(order))
        problems = list(block.get("problems") or [])
        entry = {"kind": kind, "at": timezone.now().isoformat(), "by": f"courier:{link.courier.ref}"}
        if payment:
            entry["payment"] = payment
        problems.append(entry)
        block["problems"] = problems
        courier._save_block(order, block, emit={"kind": "problem", "status": block.get("status", "")})
        order.emit_event(event_type="courier_problem", actor=entry["by"], payload=entry)
    label = _order_label(order)
    detail = PROBLEMS[kind] + (f": {PAYMENT_METHODS[payment].lower()}" if payment else "")
    try:
        alert_adapter.create("courier_stop_problem", "warning",
                             f"{label}: {detail}. {link.courier.name} avisou pelo link.", order_ref=order.ref)
    except Exception:
        logger.warning("own_fleet.alert_failed order=%s", order.ref, exc_info=True)


def close_if_settled(link: CourierLink) -> bool:
    """A rota fecha quando o balcão conferiu a volta de todos os pedidos dela."""
    if link.expires_at is not None or link.revoked_at is not None:
        return False
    orders = _ride_orders(link)
    if not orders:
        return False
    def settled(o):
        block = courier.get_block(o)
        dispatch = (o.data or {}).get("dispatch") or {}
        ended = block.get("id_mch") != link.ride_ref or o.status == Order.Status.CANCELLED
        delivered = block.get("status") == "F"
        needs_back = bool(dispatch.get("custody_at")) and not dispatch.get("courier_back_at")
        return ended or (delivered and not needs_back)
    if all(settled(o) for o in orders):
        courier_links.close(link.ride_ref)
        return True
    return False


# ── A leitura da rota para a página do entregador (telas do §4.5.2) ──────────


def _stop_view(order: Order, link: CourierLink, *, on_route: bool) -> dict:
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    block = courier.get_block(order)
    handoff = build_dispatch_payload(order)
    charge = courier.door_charge(order)
    paid_other = next((p.get("payment") for p in reversed(block.get("problems") or [])
                       if p.get("kind") == OTHER_PAYMENT), "")
    if order.status == Order.Status.CANCELLED or block.get("id_mch") != link.ride_ref:
        state = "cancelled"
    elif block.get("status") == "F":
        state = "done"
    else:
        state = "open"
    cash_q, card_q = charge["cash_q"], charge["card_q"]
    if paid_other in ("card", "pix"):
        card_q, cash_q = card_q + cash_q, 0
    elif paid_other == "cash":
        cash_q, card_q = cash_q + card_q, 0
    change_for_q = charge["change_for_q"] if cash_q and paid_other != "cash" else 0
    view = {
        "ref": order.ref,
        "code": _order_label(order),
        "name": (handoff["customer_name"].split() or [""])[0],
        "street": " ".join(p for p in (handoff["route"], handoff["street_number"]) if p) or handoff["formatted_address"],
        "complement": handoff["complement"],
        "neighborhood": handoff["neighborhood"],
        "instructions": handoff["delivery_instructions"],
        "bags": int((order.data or {}).get("volumes") or 0),
        "ready": order.status in (Order.Status.READY, Order.Status.DISPATCHED, Order.Status.DELIVERED),
        "state": state,
        "receive": {"cash_q": cash_q, "card_q": card_q, "pays_with_q": change_for_q,
                    "change_back_q": max(change_for_q - cash_q, 0), "paid_other": paid_other},
        "lat": handoff["latitude"],
        "lng": handoff["longitude"],
    }
    # Telefone só com a parada aberta e a rota na rua (plano §4.4: o mínimo, com prazo).
    if on_route and state == "open":
        view["phone"] = handoff["customer_phone"]
    return view


def ride_view(link: CourierLink) -> dict:
    """O que a página do entregador mostra agora. Sem endereço depois que a rota fecha."""
    from shopman.utils.monetary import format_money

    close_if_settled(link)
    link.refresh_from_db()
    base = {"courier": link.courier.name, "ride_ref": link.ride_ref}
    if link.revoked_at is not None:
        return {**base, "moment": "cancelled" if link.revoked_reason == courier_links.CANCELLED else "reassigned"}
    orders = _ride_orders(link)
    blocks = [courier.get_block(o) for o in orders]
    first = blocks[0] if blocks else {}
    number = first.get("ride_number")
    value_q = (first.get("estimate") or {}).get("value_q")
    many = len(orders) > 1
    label = f"Rota {courier.ride_letter(number)}" if many and number else (
        f"Pedido {_order_label(orders[0])}" if orders else "")
    base.update(label=label, letter=courier.ride_letter(number) if (many and number) else "", value_q=value_q)
    if first.get("note"):
        base["note"] = str(first["note"])
    if link.expires_at is not None:
        return {**base, "moment": "closed", "today_q": _today_q(link.courier)}
    live = [(o, b) for o, b in zip(orders, blocks, strict=False) if _live(o, link)]
    statuses = {b.get("status") for _, b in live}
    on_route = "E" in statuses
    stops = [_stop_view(o, link, on_route=on_route) for o in orders]
    if "A" in statuses:
        moment = "pickup" if all(s["ready"] for s in stops if s["state"] != "cancelled") else "pickup_wait"
    elif on_route:
        moment = "route"
    else:
        moment = "back"
    machine = next((((o.data or {}).get("dispatch") or {}).get("device_label") for o, _ in live
                    if ((o.data or {}).get("dispatch") or {}).get("device_label")), "")
    open_or_back = [s for s in stops if s["state"] != "cancelled"]
    cash_back_q = sum(s["receive"]["cash_q"] for s in open_or_back if s["state"] == "done") + sum(
        s["receive"]["change_back_q"] for s in open_or_back if s["state"] != "done")
    return {
        **base,
        "moment": moment,
        "stops": stops,
        "machine": machine,
        "settle": {"cash_q": cash_back_q, "cash": f"R$ {format_money(cash_back_q)}", "machine": machine,
                   "bags_back": [s["code"] for s in stops if s["state"] == "cancelled"]},
    }


def _today_q(courier_person: Courier) -> int:
    """O que a casa deve ao entregador hoje: o valor das rotas fechadas dele no dia."""
    today = timezone.localdate()
    total = 0
    seen: set[str] = set()
    for link in courier_person.links.filter(created_at__date=today, revoked_at__isnull=True,
                                             expires_at__isnull=False):
        if link.ride_ref in seen or not link.order_refs:
            continue
        seen.add(link.ride_ref)
        order = Order.objects.filter(ref=link.order_refs[0]).first()
        block = courier.get_block(order) if order else {}
        total += int(block.get("final_value_q") or (block.get("estimate") or {}).get("value_q") or 0)
    return total
