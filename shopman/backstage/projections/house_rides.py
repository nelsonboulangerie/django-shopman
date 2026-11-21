"""A corrida da casa na página Entregas (DEV-2026-030, frente M3b, #2898).

Quando quem leva é um entregador da casa (o serviço que sabe ``assign`` e não avisa sozinho,
``DeliveryCapabilities``), a corrida ganha o que a TaOn não tem: o nome de quem leva no
lugar do momento da central ("Diego leva", "Diego na rua · 1 de 2 entregues"), o estado do
link e os gestos do balcão para quando o entregador está sem celular ou sem sinal ("Despachar a corrida C",
"A47 entregue"), mais "Reenviar o link" e "Soltar o link". O acerto da volta continua o
"Entregador voltou" de sempre (``back_action`` da corrida).

Só leitura; os gestos vão a ``/api/v1/backstage/deliveries/couriers/rides/<ride>/…``, no
protocolo de intenção, com a revisão da rota (``house_couriers.ride_revision``).
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.orderman.models import Order
from shopman.utils.formatting import format_clock

from shopman.shop.projections.types import Action


@dataclass(frozen=True)
class HouseStopActionProjection:
    """O "Entregue" de UMA parada da rota, pelo balcão."""

    ref: str
    code: str
    action: Action


@dataclass(frozen=True)
class DeliveryHouseRideProjection:
    """O que a corrida da casa mostra e os gestos dela no Gestor."""

    courier_ref: str
    courier_name: str
    #: "Diego leva" · "Diego na rua · 1 de 2 entregues" · "Diego entregou tudo"
    moment: str
    #: "Entregador da casa · R$ 15,00 · Abriu o link às 12h31"
    hint: str
    delivered: int
    total: int
    #: O link está preso a um celular (só então "Soltar o link" faz sentido).
    link_claimed: bool
    depart_action: Action | None = None
    deliver_actions: tuple[HouseStopActionProjection, ...] = ()
    resend_action: Action | None = None
    release_action: Action | None = None


def is_house(block: dict) -> bool:
    """A corrida é de um serviço em que a pessoa é escolhida e o estado não vem sozinho."""
    from shopman.shop.services import delivery_services

    caps = delivery_services.capabilities(block) if block.get("service") else None
    return bool(caps and caps.assign and not caps.push_status)


def _hour(iso_or_dt) -> str:
    return format_clock(iso_or_dt)


def house_ride(lead: Order, *, user=None) -> DeliveryHouseRideProjection | None:
    """A corrida da casa a partir do pedido que a lidera, ou None (TaOn, sem link vivo)."""
    from shopman.backstage.projections.deliveries import _action
    from shopman.backstage.projections.order_queue import _money
    from shopman.backstage.services import house_couriers
    from shopman.shop.models.delivery_service import CourierLink
    from shopman.shop.services import courier
    from shopman.shop.services.operator_orders import short_ref

    block = courier.get_block(lead)
    ride_ref = str(block.get("ride_ref") or "")
    if not ride_ref or not is_house(block):
        return None
    link = (CourierLink.objects.select_related("courier")
            .filter(ride_ref=ride_ref, revoked_at__isnull=True).order_by("-created_at").first())
    if link is None:
        return None
    name = link.courier.name
    orders = house_couriers.ride_orders(link)
    live = [order for order in orders
            if order.status != Order.Status.CANCELLED and courier.get_block(order).get("ride_ref") == ride_ref]
    statuses = [str(courier.get_block(order).get("status") or "") for order in live]
    delivered = sum(1 for status in statuses if status == "F")
    total = len(live)
    if statuses and all(status == "F" for status in statuses):
        moment = f"{name} entregou tudo"
    elif "E" in statuses:
        moment = f"{name} na rua · {delivered} de {total} entregues"
    else:
        moment = f"{name} leva"
    value_q = (block.get("estimate") or {}).get("value_q")
    if link.opened_at and link.device_hash:
        link_word = f"Abriu o link às {_hour(link.opened_at)}"
    else:
        link_word = "Ainda não abriu o link"
    open_ride = link.expires_at is None and any(status in ("A", "E") for status in statuses)
    hint = " · ".join(part for part in (
        "Entregador da casa",
        _money(value_q) if isinstance(value_q, int) and value_q > 0 else "",
        link_word if open_ride else "",
    ) if part)
    revision = house_couriers.ride_revision(link)
    leaving = "A" in statuses and link.expires_at is None
    deliver = tuple(
        HouseStopActionProjection(
            ref=order.ref, code=short_ref(order.ref),
            action=_action("house-deliver", f"{short_ref(order.ref)} entregue", revision, user, confirmation={
                "required": True,
                "description": f"Marcar {short_ref(order.ref)} como entregue? O cliente recebe o aviso agora.",
            }),
        )
        for order, status in zip(live, statuses, strict=True) if status == "E" and link.expires_at is None
    )
    return DeliveryHouseRideProjection(
        courier_ref=link.courier.ref,
        courier_name=name,
        moment=moment,
        hint=hint,
        delivered=delivered,
        total=total,
        link_claimed=bool(link.device_hash),
        # O gesto de saída tem o nome do vocabulário, "Despachar <código>"; o código da
        # corrida é a letra, e "corrida" desfaz a dúvida de um código de uma letra só
        # (coordenação, 21/11, #3054). Sem letra, "Despachar a corrida".
        depart_action=_action("house-depart", " ".join(
            part for part in ("Despachar a corrida", courier.ride_letter(block.get("ride_number"))) if part
        ), revision, user, confirmation={
            "required": True,
            "description": f"{name} saiu com {'os pedidos' if total > 1 else 'o pedido'}? Os clientes recebem o aviso de saída.",
        }) if leaving else None,
        deliver_actions=deliver,
        resend_action=_action("house-resend", "Reenviar o link", revision, user, confirm=False) if open_ride else None,
        release_action=_action("house-release", "Soltar o link", revision, user, confirmation={
            "required": True,
            "description": "Soltar o link do celular em que está preso? O próximo celular que confirmar fica com ele.",
        }) if open_ride and link.device_hash else None,
    )
