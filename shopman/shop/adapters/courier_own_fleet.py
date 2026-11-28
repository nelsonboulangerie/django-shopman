"""O serviço "entregadores da casa": a segunda implementação do contrato de entrega.

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §2.2 e §4 (DEV-2026-030, frente M2).
Não há central nem rede: quem leva é uma pessoa da casa, escolhida pelo operador, e quem
avança a corrida é ela, pelo link (``services/own_fleet``), ou o operador no Gestor.

Para entrar no funil de sempre (``courier.apply_status``) sem tocá-lo, a corrida da casa usa
as mesmas letras internas que a TaOn: ``A`` designada, ``E`` saiu da loja, ``F`` entregue,
``C`` cancelada. O vocabulário que a tela lê é o da casa (``ride_state``). Renomear as letras
para o vocabulário neutro no bloco é a M1b (#2552).
"""

from __future__ import annotations

import math

from shopman.shop.adapters.courier_machine import CourierError, CourierEstimate, ride_state  # noqa: F401
from shopman.shop.protocols import DeliveryCapabilities

#: O que a casa sabe fazer: cota pela tabela, leva várias paradas, a pessoa é escolhida
#: pelo operador, leva cobrança na porta. Não avisa sozinha nem tem rastreio de terceiro.
CAPABILITIES = DeliveryCapabilities(
    quote=True,
    multi_stop=4,
    cancel_reasons=False,
    customer_tracking=False,
    push_status=False,
    door_charge=True,
    needs_return=False,
    assign=True,
)

#: Prefixo do identificador da corrida da casa (o `ride_ref` do bloco, o mesmo campo da TaOn).
RIDE_PREFIX = "CASA-"

#: Velocidade média para estimar o tempo da rota na cidade (km/h). É palpite até o B.I.
#: medir as corridas da casa.
CITY_SPEED_KMH = 25.0


def is_configured() -> bool:
    return True


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em km entre dois pontos (haversine), com 25% a mais pelo traçado das ruas."""
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h)) * 1.25


def _point(place: dict | None) -> tuple[float, float] | None:
    place = place or {}
    try:
        return float(place["lat"]), float(place["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def route_km(*, pickup: dict, dropoff: dict, stops: list[dict] | None = None, with_return: bool = False) -> float | None:
    """O km da rota inteira: loja, paradas do meio, a última e, com volta, de novo a loja."""
    points = [_point(pickup), *[_point(stop) for stop in stops or []], _point(dropoff)]
    if any(point is None for point in points):
        return None
    if with_return:
        points.append(points[0])
    return round(sum(_km(a, b) for a, b in zip(points, points[1:], strict=False)), 1)


def estimate(*, pickup: dict, dropoff: dict, with_return: bool = False, stops: list[dict] | None = None,
             courier=None) -> CourierEstimate | None:
    """A cotação da casa: o valor da tabela para o km da rota. None sem coordenada ou sem linha."""
    from shopman.shop.models.delivery_service import DeliveryService
    from shopman.shop.services.delivery_rates import ride_value

    km = route_km(pickup=pickup, dropoff=dropoff, stops=stops, with_return=with_return)
    service = DeliveryService.objects.filter(kind=DeliveryService.KIND_OWN_FLEET, is_active=True).first()
    if km is None or service is None:
        return None
    value = ride_value(service, km=km, stops=1 + len(stops or []), with_return=with_return, courier=courier)
    if value is None:
        return None
    return CourierEstimate(value_q=value.value_q, minutes=round(km / CITY_SPEED_KMH * 60, 1), km=km)


def dispatch(payload: dict):
    """A casa não abre corrida por central: o operador escolhe a pessoa (``own_fleet.assign``)."""
    raise CourierError("A corrida da casa é enviada a um entregador pelo operador.", transient=False)


def read_ride(courier_ref: str) -> dict:
    """A leitura é o próprio pedido: a casa não tem central para consultar."""
    from shopman.orderman.models import Order

    order = Order.objects.filter(data__courier__ride_ref=courier_ref).order_by("pk").first()
    block = ((order.data or {}).get("courier") or {}) if order else {}
    return {"status": block.get("status", ""), "driver": block.get("driver") or {}, "progress": {},
            "final_value_q": block.get("final_value_q"), "via": "own_fleet"}


def get_details(courier_ref: str) -> dict:
    """A casa não tem detalhes de central; o entregador e o valor já estão no bloco."""
    return {}


def get_status(courier_ref: str) -> str:
    return read_ride(courier_ref)["status"]


def cancel(courier_ref: str, *, reason_id: int | None = None) -> bool:
    """Cancelar a corrida da casa é revogar o link: o entregador vê que não precisa vir."""
    from shopman.shop.services import courier_links

    courier_links.revoke(courier_ref, reason=courier_links.CANCELLED)
    return True


def tracking_links(courier_ref: str) -> list[dict]:
    """A casa não tem link de rastreio de terceiro para o cliente."""
    return []
