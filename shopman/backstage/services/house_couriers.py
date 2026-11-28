"""Quem leva: os entregadores da casa no gesto de chamar (DEV-2026-030, frente M3, #2526).

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §3 (o gesto), §4.1 (a escala do dia) e
§4.2 (o link pelo WhatsApp do dispositivo). Três coisas, todas do Gestor:

- ``crew``: quem da casa está ativo, quem está na escala de hoje, quem está na rua, e o
  valor da tabela para os pedidos escolhidos (o chip "Diego · Livre · R$ 15,00").
- ``send_ride``: a corrida vai para uma pessoa da casa (``own_fleet.assign``), com a mesma
  custódia de troco e maquininha da chamada da TaOn e a mesma conferência do que a tela
  leu de cada pedido. Devolve o link e o texto pronto para o WhatsApp.
- ``set_shift``: liga e desliga a escala de hoje ("Entregadores de hoje").

O serviço padrão (o que vem marcado) é o do Admin (``DeliveryService.is_default``, decisão
do dono, 16/11/2026); a casa aparece como opção, nunca no lugar dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.formatting import format_clock

from shopman.backstage.services.exceptions import OrderError
from shopman.shop.models.delivery_service import Courier, CourierLink, DeliveryService
from shopman.shop.protocols import RideState
from shopman.shop.services import delivery_services

#: Os estados do chip, como o operador lê.
FREE = "free"
BUSY = "busy"
STATE_LABELS = {FREE: "Livre", BUSY: "Na rua"}


def own_service() -> DeliveryService | None:
    """O serviço dos entregadores da casa, quando está ativo."""
    return DeliveryService.objects.filter(kind=DeliveryService.KIND_OWN_FLEET, is_active=True).order_by(
        "sort_order", "pk").first()


def _live_ride(person: Courier) -> list[Order] | None:
    """Os pedidos da rota da casa que o balcão ainda não fechou (a régua do ``close_if_settled``).

    None quando a pessoa não está com rota nenhuma.
    """
    from shopman.shop.services import courier

    for link in person.links.filter(revoked_at__isnull=True, expires_at__isnull=True):
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=link.order_refs or [])}
        live = []
        holds = False
        for ref in link.order_refs or []:
            order = by_ref.get(ref)
            if order is None or order.status == Order.Status.CANCELLED:
                continue
            block = courier.get_block(order)
            if block.get("ride_ref") != link.ride_ref:
                continue
            live.append(order)
            dispatch = (order.data or {}).get("dispatch") or {}
            needs_back = bool(dispatch.get("custody_at")) and not dispatch.get("courier_back_at")
            holds = holds or delivery_services.ride_state(block) != RideState.DONE or needs_back
        if holds:
            return live
    return None


#: Minutos por parada (entregar, cobrar) somados ao percurso para estimar a volta.
STOP_MINUTES = 3


def back_at(orders: list[Order]):
    """Quando a pessoa deve voltar à loja: a saída mais o percurso de ida e volta pela cidade.

    None antes de sair, ou sem coordenada (a tela diz só "Na rua").
    """
    from datetime import timedelta

    from django.utils.dateparse import parse_datetime

    from shopman.shop.adapters import courier_own_fleet
    from shopman.shop.models import Shop
    from shopman.shop.services import courier
    from shopman.shop.services.dispatch_handoff import build_dispatch_payload

    departed = [parse_datetime(str(delivery_services.state_since(courier.get_block(order), RideState.ON_ROUTE) or ""))
                for order in orders]
    departed = [moment for moment in departed if moment is not None]
    shop = Shop.objects.first()
    if not departed or shop is None or shop.latitude is None or shop.longitude is None:
        return None
    places = []
    for order in orders:
        handoff = build_dispatch_payload(order)
        places.append({"lat": handoff.get("latitude"), "lng": handoff.get("longitude")})
    km = courier_own_fleet.route_km(pickup={"lat": shop.latitude, "lng": shop.longitude}, dropoff=places[-1],
                                    stops=places[:-1], with_return=True)
    if km is None:
        return None
    minutes = km / courier_own_fleet.CITY_SPEED_KMH * 60 + STOP_MINUTES * len(orders)
    return min(departed) + timedelta(minutes=minutes)


def busy_label(back) -> str:
    """ "Volta 12h50" com a hora estimada; "Na rua" sem ela; "Voltando" quando a hora passou."""
    if back is None:
        return STATE_LABELS[BUSY]
    if back <= timezone.now():
        return "Voltando"
    return f"Volta {format_clock(back)}"


def _money(value_q: int | None) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(value_q)}" if isinstance(value_q, int) else ""


def to_pay_today(name: str, total_q: int, rides: int) -> str:
    """ "A pagar a Diego hoje: R$ 56,00 (4 corridas)"; vazio sem rota fechada no dia.

    O acerto do dia (decisão 5 do dono): o sistema soma, o pagamento é por fora (Pix do dono).
    """
    if rides <= 0:
        return ""
    count = "1 corrida" if rides == 1 else f"{rides} corridas"
    return f"A pagar a {name} hoje: {_money(total_q)} ({count})"


def crew(refs: list[str] | None = None) -> dict:
    """Os entregadores da casa para o Gestor.

    ``active``: o serviço da casa está ativo (sem ele, nem a linha "Entregadores de hoje"
    nem o "Quem leva" aparecem). ``default``: o serviço padrão do Admin, o que vem marcado.
    ``couriers``: todos os ativos, com ``on_shift`` (na escala de hoje), ``state``
    (``free``/``busy``) e ``state_label`` ("Livre", "Volta 12h50" com a hora estimada da volta em
    ``back_at``, "Na rua" antes de sair); com ``refs`` (na ordem da
    rota), o valor da tabela de cada um na escala (``value_q``/``value``), ``None`` sem
    coordenada ou sem linha na tabela; ``to_pay_today``, o acerto do dia ("A pagar a Diego
    hoje: R$ 56,00 (4 corridas)", vazio sem rota fechada hoje).
    """
    from shopman.shop.services import own_fleet

    service = own_service()
    default = DeliveryService.default()
    body = {
        "active": service is not None,
        "service": {"ref": service.ref, "name": service.name} if service else None,
        "default": {"ref": default.ref, "name": default.name} if default else None,
        "couriers": [],
    }
    if service is None:
        return body
    orders: list[Order] = []
    if refs:
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=refs)}
        orders = [by_ref[ref] for ref in refs if ref in by_ref]
    today = timezone.localdate()
    for person in service.couriers.filter(is_active=True).order_by("name"):
        on_shift = person.is_on_shift(today)
        live = _live_ride(person) if on_shift else None
        state = BUSY if live is not None else FREE
        back = back_at(live) if live else None
        value_q = None
        if on_shift and orders:
            estimate = own_fleet._estimate(orders, person)
            value_q = estimate.value_q if estimate is not None else None
        today_q, today_rides = own_fleet.today_settlement(person)
        body["couriers"].append({
            "ref": person.ref, "name": person.name, "on_shift": on_shift, "state": state,
            "state_label": busy_label(back) if state == BUSY else STATE_LABELS[FREE],
            "back_at": back.isoformat() if back else None,
            "value_q": value_q, "value": _money(value_q),
            "to_pay_today": to_pay_today(person.name, today_q, today_rides),
        })
    return body


def set_shift(ref: str, on_shift: bool) -> Courier:
    """Liga ou desliga a escala de hoje de um entregador ativo da casa."""
    service = own_service()
    person = Courier.objects.filter(ref=ref, is_active=True, service=service).first() if service else None
    if person is None:
        raise OrderError("Este entregador não está ativo. Confira no Admin.")
    person.on_shift_on = timezone.localdate() if on_shift else None
    person.save(update_fields=["on_shift_on"])
    return person


@dataclass(frozen=True)
class SentRide:
    ride_ref: str
    link_url: str
    whatsapp_url: str
    detail: str
    ride_number: int | None


def ride_label(orders: list[Order], number: int | None) -> tuple[str, bool]:
    """ "Rota A" (várias paradas) ou "Pedido A47" (uma), e se o nome é feminino."""
    from shopman.shop.services import courier
    from shopman.shop.services.operator_orders import short_ref

    if len(orders) > 1 and number:
        return f"Rota {courier.ride_letter(number)}", True
    return f"Pedido {short_ref(orders[0].ref)}", False


def whatsapp_url(phone: str, text: str) -> str:
    """O link que abre o WhatsApp do dispositivo com o texto pronto para o entregador."""
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


def link_url(link: CourierLink) -> str:
    """A página do entregador na loja (``/rota/<token>``)."""
    from shopman.shop.services.storefront_links import storefront_url

    return storefront_url(f"/rota/{link.token}")


def send_ride(orders: list[Order], courier_ref: str, *, actor: str, operator=None,
              change_out_raw: dict | None = None, machine: str = "",
              expected_revisions: dict[str, str] | None = None, ride_number: int | None = None,
              note: str = "") -> SentRide:
    """Envia a corrida a um entregador da casa, com a custódia, e prepara o WhatsApp.

    A mesma porta da corrida da TaOn (``orders.courier_group_dispatch``): o troco de cada
    pedido sai da gaveta do turno aberto, a maquininha é uma para a rota, e o pedido que
    mudou depois que a tela foi lida recusa com ``revision_changed``. Tudo numa transação:
    se um pedido recusa, nada sai da gaveta e ninguém recebe link.
    """
    from shopman.backstage.services.exceptions import POSError
    from shopman.backstage.services.orders import OrderChangeOutRequired, OrderRideRevisionChanged
    from shopman.backstage.services.pos import parse_money_to_q
    from shopman.shop.services import courier, operator_orders, own_fleet

    service = own_service()
    person = Courier.objects.filter(ref=courier_ref, service=service, is_active=True).first() if service else None
    if person is None:
        raise OrderError("Este entregador não está ativo. Confira no Admin.")
    if not person.is_on_shift(timezone.localdate()):
        raise OrderError(f"{person.name} não está na escala de hoje. Ligue em Entregadores de hoje.")
    change_out_q: dict[str, int] = {}
    for ref, raw in (change_out_raw or {}).items():
        if raw is None or str(raw).strip() == "":
            continue
        try:
            change_out_q[str(ref)] = parse_money_to_q(str(raw))
        except POSError as exc:
            raise OrderError(f"Troco do pedido {operator_orders.short_ref(ref)}: {exc or 'valor inválido.'}") from exc
    shift = None
    if operator is not None and any(change_out_q.values()):
        from shopman.backstage.services import pos as pos_service

        shift = pos_service.current_shift()
    asks = {order.ref: operator_orders.partner_custody_asks(order) for order in orders}
    for order in orders:
        ask = asks[order.ref]
        if not ask["recorded"] and ask["change_out_suggested_q"] > 0 and order.ref not in change_out_q:
            raise OrderChangeOutRequired(
                f"O pedido {operator_orders.short_ref(order.ref)} pede troco: diga quanto o entregador leva.",
                suggested_q=ask["change_out_suggested_q"],
            )
    needs_machine = any(ask["needs_machine"] for ask in asks.values())
    try:
        with transaction.atomic():
            locked = {o.pk: o for o in Order.objects.select_for_update().filter(pk__in=[o.pk for o in orders])}
            if expected_revisions is not None:
                changed = [o.ref for o in orders
                           if expected_revisions.get(o.ref) != courier.dispatch_revision(locked[o.pk])]
                if changed:
                    raise courier.RideRevisionChanged(changed)
            assignment = own_fleet.assign(
                orders, person, actor=actor, change_out=change_out_q, cash_shift=shift,
                equipment=[machine] if machine and needs_machine else None, ride_number=ride_number,
                note=note,
            )
    except courier.RideRevisionChanged as exc:
        raise OrderRideRevisionChanged(str(exc), refs=exc.refs) from exc
    except operator_orders.ChangeOutRequired as exc:
        raise OrderChangeOutRequired("Um pedido pede troco: diga quanto o entregador leva.",
                                     suggested_q=exc.suggested_q) from exc
    except own_fleet.OwnFleetRefused as exc:
        raise OrderError(str(exc)) from exc
    except ValueError as exc:
        raise OrderError(str(exc) or "Não foi possível enviar a corrida.") from exc
    return _sent(assignment.link, orders, verb=("enviada", "enviado"))


def _sent(link: CourierLink, orders: list[Order], *, verb: tuple[str, str]) -> SentRide:
    """O link e o WhatsApp pronto da rota, e a frase do toast ("Rota C enviada para Diego.")."""
    from shopman.shop.services import courier

    first = Order.objects.get(pk=orders[0].pk)
    number = courier.get_block(first).get("ride_number")
    label, feminine = ride_label(orders, number)
    url = link_url(link)
    text = f"Corrida para você: {label}. Abra o link no seu celular: {url}"
    return SentRide(
        ride_ref=link.ride_ref, link_url=url, whatsapp_url=whatsapp_url(link.courier.phone, text),
        detail=f"{label} {verb[0] if feminine else verb[1]} para {link.courier.name}.",
        ride_number=number if isinstance(number, int) else None,
    )


# ── Os gestos do balcão na corrida da casa (M3b, #2898) ─────────────────────
# Quando o entregador está sem celular ou sem sinal, o operador faz por ele, pelo mesmo
# funil do link (``own_fleet.depart``/``deliver``), com a fonte ``operator:<nome>``. E o
# link: reenviar (o MESMO link, pelo WhatsApp do dispositivo) e soltar do celular errado.


def live_link(ride_ref: str) -> CourierLink:
    """O link vivo da rota, ou a recusa com a frase da tela."""
    link = (CourierLink.objects.select_related("courier")
            .filter(ride_ref=ride_ref, revoked_at__isnull=True, expires_at__isnull=True).first())
    if link is None:
        raise OrderError("Esta corrida não é mais da casa, ou já fechou. Atualize a tela.")
    return link


def ride_orders(link: CourierLink) -> list[Order]:
    by_ref = {order.ref: order for order in Order.objects.filter(ref__in=link.order_refs or [])}
    return [by_ref[ref] for ref in link.order_refs or [] if ref in by_ref]


def ride_revision(link: CourierLink) -> str:
    """O que a tela leu da rota: a revisão de cada pedido dela, numa marca só."""
    from shopman.shop.services import courier
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    return mutation_fingerprint({"ride": link.ride_ref,
                                 "orders": [courier.dispatch_revision(order) for order in ride_orders(link)]})


def check_revision(link: CourierLink, expected: str | None) -> None:
    from shopman.backstage.services.exceptions import OrderConflict

    if expected is not None and expected != ride_revision(link):
        raise OrderConflict("A corrida mudou depois que você abriu esta tela. Confira e toque de novo.")


def operator_source(actor: str) -> str:
    return f"operator:{actor}"


def depart(ride_ref: str, *, actor: str, expected: str | None = None) -> str:
    """ "Saiu": a rota sai para entrega pelo balcão. Devolve a frase do toast."""
    from shopman.shop.services import courier, own_fleet

    link = live_link(ride_ref)
    check_revision(link, expected)
    try:
        applied = own_fleet.depart(link, source=operator_source(actor))
    except own_fleet.OwnFleetRefused as exc:
        raise OrderError(str(exc)) from exc
    if not applied:
        raise OrderError("Nenhum pedido desta corrida estava esperando sair.")
    orders = ride_orders(link)
    label, _ = ride_label(orders, courier.get_block(orders[0]).get("ride_number"))
    return f"{label}: {link.courier.name} saiu para entrega."


def deliver(ride_ref: str, order_ref: str, *, actor: str, expected: str | None = None) -> str:
    """ "Entregue" de UM pedido da rota, pelo balcão. O aviso vai só àquele cliente."""
    from shopman.shop.services import own_fleet
    from shopman.shop.services.operator_orders import short_ref

    link = live_link(ride_ref)
    check_revision(link, expected)
    try:
        own_fleet.deliver(link, order_ref, source=operator_source(actor))
    except own_fleet.OwnFleetRefused as exc:
        raise OrderError(str(exc)) from exc
    except Order.DoesNotExist as exc:
        raise OrderError("Este pedido não é desta rota.") from exc
    return f"{short_ref(order_ref)} entregue."


def resend(ride_ref: str) -> SentRide:
    """O MESMO link de novo, pelo WhatsApp do dispositivo (a mensagem se perdeu)."""
    link = live_link(ride_ref)
    return _sent(link, ride_orders(link), verb=("reenviada", "reenviado"))


def release(ride_ref: str) -> str:
    """Solta o link do celular em que ele está preso; o próximo a confirmar fica com ele."""
    from shopman.shop.services import courier_links

    link = live_link(ride_ref)
    if not link.device_hash:
        raise OrderError("O link ainda não está preso a nenhum celular.")
    courier_links.release(ride_ref)
    return f"Link de {link.courier.name} solto. O próximo celular que confirmar fica com ele."
