"""Quanto a casa paga ao entregador da casa por uma corrida.

A régua da tabela de valores (decisão do dono, 16/11/2026: tabela da casa por distância, mais
um valor por parada a mais e pela volta, com exceção por entregador). Plano:
``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §5.

A distância é a da rota inteira (loja, paradas e, quando houver, a volta), a mesma que a
TaOn cotaria. O valor é custo interno da casa: o frete do cliente não muda com ele.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from shopman.shop.models.delivery_service import Courier, CourierRate, DeliveryService


@dataclass(frozen=True)
class RideValue:
    value_q: int
    rate: CourierRate
    #: "courier" quando valeu o combinado com o entregador; "house" quando valeu a tabela da casa.
    source: str


def _pick(rates: list[CourierRate], km: Decimal) -> CourierRate | None:
    bounded = sorted((r for r in rates if r.max_km is not None), key=lambda r: r.max_km)
    for rate in bounded:
        if km <= rate.max_km:
            return rate
    return next((r for r in rates if r.max_km is None), None)


def ride_value(
    service: DeliveryService,
    *,
    km: float | Decimal,
    stops: int = 1,
    with_return: bool = False,
    courier: Courier | None = None,
) -> RideValue | None:
    """O valor da corrida pela tabela, ou None quando nenhuma linha cobre a distância.

    - Entregador com linhas próprias: só elas valem para ele (o combinado substitui a casa).
    - Senão, a tabela da casa (linhas sem entregador).
    - A linha escolhida é a de menor "até (km)" que alcança a distância; sem nenhuma, a linha
      sem distância (qualquer distância). Sem essa também, None: a tela pede o valor.
    - Soma ``extra_stop_q`` por pedido além do primeiro e ``return_q`` com volta.
    """
    if not service.is_own_fleet:
        return None
    if stops < 1:
        raise ValueError("Uma corrida tem pelo menos uma parada.")
    distance = Decimal(str(km))
    rates = list(CourierRate.objects.filter(service=service).select_related("courier"))
    own = [r for r in rates if courier is not None and r.courier_id == courier.pk]
    pool, source = (own, "courier") if own else ([r for r in rates if r.courier_id is None], "house")
    rate = _pick(pool, distance)
    if rate is None:
        return None
    value = rate.value_q + rate.extra_stop_q * (stops - 1) + (rate.return_q if with_return else 0)
    return RideValue(value_q=value, rate=rate, source=source)
