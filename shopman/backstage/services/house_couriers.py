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

from shopman.backstage.services.exceptions import OrderError
from shopman.shop.models.delivery_service import Courier, CourierLink, DeliveryService

#: Os estados do chip, como o operador lê.
FREE = "free"
BUSY = "busy"
STATE_LABELS = {FREE: "Livre", BUSY: "Na rua"}


def own_service() -> DeliveryService | None:
    """O serviço dos entregadores da casa, quando está ativo."""
    return DeliveryService.objects.filter(kind=DeliveryService.KIND_OWN_FLEET, is_active=True).order_by(
        "sort_order", "pk").first()


def _holds_live_ride(person: Courier) -> bool:
    """Está com uma rota da casa que o balcão ainda não fechou (a mesma régua do ``close_if_settled``)."""
    from shopman.shop.services import courier

    for link in person.links.filter(revoked_at__isnull=True, expires_at__isnull=True):
        by_ref = {order.ref: order for order in Order.objects.filter(ref__in=link.order_refs or [])}
        for ref in link.order_refs or []:
            order = by_ref.get(ref)
            if order is None or order.status == Order.Status.CANCELLED:
                continue
            block = courier.get_block(order)
            if block.get("id_mch") != link.ride_ref:
                continue
            dispatch = (order.data or {}).get("dispatch") or {}
            needs_back = bool(dispatch.get("custody_at")) and not dispatch.get("courier_back_at")
            if block.get("status") != "F" or needs_back:
                return True
    return False


def _money(value_q: int | None) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(value_q)}" if isinstance(value_q, int) else ""


def crew(refs: list[str] | None = None) -> dict:
    """Os entregadores da casa para o Gestor.

    ``active``: o serviço da casa está ativo (sem ele, nem a linha "Entregadores de hoje"
    nem o "Quem leva" aparecem). ``default``: o serviço padrão do Admin, o que vem marcado.
    ``couriers``: todos os ativos, com ``on_shift`` (na escala de hoje), ``state``
    (``free``/``busy``) e ``state_label`` ("Livre"/"Na rua"); com ``refs`` (na ordem da
    rota), o valor da tabela de cada um na escala (``value_q``/``value``), ``None`` sem
    coordenada ou sem linha na tabela.
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
        state = BUSY if on_shift and _holds_live_ride(person) else FREE
        value_q = None
        if on_shift and orders:
            estimate = own_fleet._estimate(orders, person)
            value_q = estimate.value_q if estimate is not None else None
        body["couriers"].append({
            "ref": person.ref, "name": person.name, "on_shift": on_shift, "state": state,
            "state_label": STATE_LABELS[state], "value_q": value_q, "value": _money(value_q),
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
              expected_revisions: dict[str, str] | None = None, ride_number: int | None = None) -> SentRide:
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
    first = Order.objects.get(pk=orders[0].pk)
    number = courier.get_block(first).get("ride_number")
    label, feminine = ride_label(orders, number)
    url = link_url(assignment.link)
    text = f"Corrida para você: {label}. Abra o link no seu celular: {url}"
    return SentRide(
        ride_ref=assignment.ride_ref, link_url=url, whatsapp_url=whatsapp_url(person.phone, text),
        detail=f"{label} {'enviada' if feminine else 'enviado'} para {person.name}.",
        ride_number=number if isinstance(number, int) else None,
    )
