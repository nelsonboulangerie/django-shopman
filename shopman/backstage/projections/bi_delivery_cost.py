"""B.I. — quanto a casa paga pelas entregas, por serviço, e quanto o frete cobre.

A corrida é custo da casa: o frete do cliente não muda com ela. Esta leitura
soma o custo das corridas do período e põe ao lado o frete que os clientes
pagaram nos mesmos pedidos. A diferença é o que a entrega deixa ou custa à casa.

A casa entrega por mais de um serviço (a TaOn, os entregadores da casa: DEV-2026-030),
e o multisserviço existe para comparar: o relatório traz uma linha por serviço, com o
nome do cadastro, e o total (decisão da coordenação em 21/11/2026, #3144; o B.I. é só
do Dono, então o agregado vale aqui). A corrida sem serviço gravado conta no padrão do
Admin, que é por onde ela abriu.

- **Custo** = ``final_value_q`` de cada corrida (o valor que a TaOn fecha no
  ``F``), contado UMA vez por corrida (``ride_ref``): numa corrida com várias
  paradas cada pedido guarda o valor inteiro, e somar por pedido contaria em
  dobro. Corrida terminada sem valor final entra pela cotação
  (``estimate.value_q``) e é contada em ``estimated_rides``. Corrida cancelada
  sem valor não custa nada e fica de fora; com valor (taxa de cancelamento),
  entra.
- **Entregas** = as paradas da corrida (``ride_orders``, ou o próprio pedido),
  sem os pedidos cancelados. Pedido que aparece em duas corridas conta uma vez,
  no dia da primeira.
- **Frete cobrado** = a linha de frete (``__DELIVERY_FEE__``) dos pedidos
  levados, sem os cancelados. É o que o cliente pagou, não o que o modificador
  sugeriu.

O dia é o da chamada (``requested_at``), no fuso da loja. Inclui as corridas
arquivadas em ``attempts``. Tudo calculado na leitura (ADR-021 §3).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from shopman.shop.protocols import RideState
from shopman.shop.services import delivery_services

DEFAULT_WINDOW_DAYS = 28
MAX_WINDOW_DAYS = 366

FEE_SKU = "__DELIVERY_FEE__"


@dataclass(frozen=True)
class BIDeliveryCostDay:
    """Um dia: corridas, entregas, custo das corridas e frete cobrado."""

    date: str
    rides: int
    deliveries: int
    cost_q: int
    fee_q: int


@dataclass(frozen=True)
class BIDeliveryCostService:
    """Um serviço de entrega no período: corridas, entregas, custo e frete cobrado."""

    #: O ``ref`` do cadastro (``DeliveryService.ref``); "" sem serviço cadastrado.
    service: str
    #: O nome como o cadastro diz ("TaOn", "Entregadores da casa").
    name: str
    rides: int
    deliveries: int
    cost_q: int
    fee_q: int
    #: Frete cobrado menos custo, deste serviço.
    balance_q: int
    #: Custo por pedido levado por este serviço (zero sem entregas).
    cost_per_delivery_q: int


@dataclass(frozen=True)
class BIDeliveryCostReport:
    date_from: str
    date_to: str
    #: Corridas com custo (terminadas, ou canceladas com taxa).
    rides: int
    #: Pedidos levados nessas corridas (uma corrida pode levar vários).
    deliveries: int
    #: O que a casa paga pelas corridas no período, uma vez por corrida.
    cost_q: int
    #: Corridas terminadas sem valor final, que entraram pela cotação.
    estimated_rides: int
    #: Frete que os clientes pagaram nos pedidos levados.
    fee_q: int
    #: Frete cobrado menos custo: negativo é o que a casa põe do bolso.
    balance_q: int
    #: Custo por pedido levado (zero sem entregas).
    cost_per_delivery_q: int
    days: tuple[BIDeliveryCostDay, ...]
    #: Uma linha por serviço, do que mais custou ao que menos; a soma é o total acima.
    services: tuple[BIDeliveryCostService, ...] = ()


def _window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= MAX_WINDOW_DAYS:
        date_from = date_to - timedelta(days=MAX_WINDOW_DAYS - 1)
    return date_from, date_to


def _parse(raw) -> datetime | None:
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment


def ride_cost_q(ride: dict) -> tuple[int, bool] | None:
    """``(custo, pela cotação?)`` de uma corrida, ou ``None`` quando ela não custou.

    O valor final da TaOn vale sempre (inclusive a taxa de uma cancelada).
    Terminada sem ele, vale a cotação. Sem nenhum dos dois, não há custo.
    """
    final = ride.get("final_value_q")
    if final is not None:
        return int(final), False
    # Na corrida com várias paradas, só vale a cotação da ROTA (gravada com as
    # paradas na chamada); a de um pedido sozinho não diz o custo da corrida.
    if delivery_services.ride_state(ride) == RideState.DONE:
        estimate = ride.get("estimate") or {}
        members = ride.get("ride_orders")
        if members and sorted(estimate.get("stops") or []) != sorted(members):
            return None
        if estimate.get("value_q") is not None:
            return int(estimate["value_q"]), True
    return None


def build_bi_delivery_cost(*, date_from: date | None = None, date_to: date | None = None) -> BIDeliveryCostReport:
    from django.db.models import Q, Sum
    from shopman.orderman.models import Order, OrderItem

    start_day, end_day = _window(date_from, date_to)
    tz = timezone.get_current_timezone()
    since = datetime.combine(start_day, time.min, tzinfo=tz)
    until = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)

    # Uma corrida chamada no período mexeu no pedido depois do começo dele; a
    # encomenda criada dias antes entra pelo ``updated_at``.
    candidates = Order.objects.filter(data__has_key="courier", updated_at__gte=since, created_at__lt=until)
    from shopman.shop.models import DeliveryService

    default = DeliveryService.default()
    default_ref = default.ref if default else ""
    seen: set[str] = set()
    per_day: dict[date, dict] = defaultdict(lambda: {"rides": 0, "refs": [], "cost_q": 0})
    per_service: dict[str, dict] = defaultdict(lambda: {"rides": 0, "refs": [], "cost_q": 0})
    #: Quem levou cada pedido por último (a corrida mais recente dele): o que entregou.
    last_ride: dict[str, tuple[datetime, str]] = {}
    estimated = 0
    for order in candidates:
        block = (order.data or {}).get("courier") or {}
        if not isinstance(block, dict):
            continue
        for ride in [*(block.get("attempts") or []), block]:
            if not isinstance(ride, dict):
                continue
            ride_id = str(ride.get("ride_ref") or "")
            if not ride_id or ride_id in seen:
                continue
            requested = _parse(ride.get("requested_at"))
            if requested is None or not (since <= requested < until):
                continue
            cost = ride_cost_q(ride)
            if cost is None:
                continue
            seen.add(ride_id)
            day = timezone.localtime(requested, tz).date()
            refs = [str(ref) for ref in (ride.get("ride_orders") or [order.ref])]
            per_day[day]["rides"] += 1
            per_day[day]["refs"] += refs
            per_day[day]["cost_q"] += cost[0]
            # A corrida sem serviço gravado abriu pelo padrão do Admin.
            service_ref = str(ride.get("service") or default_ref)
            service = per_service[service_ref]
            for ref in refs:
                if ref not in last_ride or requested >= last_ride[ref][0]:
                    last_ride[ref] = (requested, service_ref)
            service["rides"] += 1
            service["refs"] += refs
            service["cost_q"] += cost[0]
            estimated += int(cost[1])

    all_refs = {ref for row in per_day.values() for ref in row["refs"]}
    cancelled = set(
        Order.objects.filter(ref__in=all_refs, status=Order.Status.CANCELLED).values_list("ref", flat=True)
    )
    fees = dict(
        OrderItem.objects.filter(order__ref__in=all_refs - cancelled)
        .filter(Q(sku=FEE_SKU) | Q(meta__type="delivery_fee"))
        .values("order__ref")
        .annotate(total=Sum("line_total_q"))
        .values_list("order__ref", "total")
    )

    days = []
    counted: set[str] = set()
    for day in sorted(per_day):
        row = per_day[day]
        refs = [ref for ref in dict.fromkeys(row["refs"]) if ref not in cancelled and ref not in counted]
        counted.update(refs)
        days.append(BIDeliveryCostDay(
            date=day.isoformat(), rides=row["rides"], deliveries=len(refs), cost_q=row["cost_q"],
            fee_q=sum(int(fees.get(ref) or 0) for ref in refs),
        ))
    cost_q = sum(day.cost_q for day in days)
    fee_q = sum(day.fee_q for day in days)
    deliveries = sum(day.deliveries for day in days)
    services = _service_rows(
        per_service, cancelled=cancelled, fees=fees, owner={ref: ride[1] for ref, ride in last_ride.items()},
    )
    return BIDeliveryCostReport(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        rides=sum(day.rides for day in days),
        deliveries=deliveries,
        cost_q=cost_q,
        estimated_rides=estimated,
        fee_q=fee_q,
        balance_q=fee_q - cost_q,
        cost_per_delivery_q=round(cost_q / deliveries) if deliveries else 0,
        days=tuple(days),
        services=services,
    )


def _service_rows(
    per_service: dict[str, dict], *, cancelled: set[str], fees: dict, owner: dict[str, str],
) -> tuple[BIDeliveryCostService, ...]:
    """As linhas por serviço, com o nome do cadastro. O pedido levado por dois serviços
    (a TaOn não atendeu, a casa levou) conta a entrega e o frete no da corrida MAIS
    RECENTE (``owner``), o que entregou; as corridas e o custo ficam onde aconteceram."""
    from shopman.shop.models import DeliveryService
    from shopman.shop.services import delivery_services

    names = dict(DeliveryService.objects.filter(ref__in=list(per_service)).values_list("ref", "name"))
    rows = []
    for service, row in per_service.items():
        refs = [ref for ref in dict.fromkeys(row["refs"]) if ref not in cancelled and owner.get(ref) == service]
        fee_q = sum(int(fees.get(ref) or 0) for ref in refs)
        rows.append(BIDeliveryCostService(
            service=service,
            name=names.get(service) or delivery_services.SERVICE_FALLBACK_NAME,
            rides=row["rides"], deliveries=len(refs), cost_q=row["cost_q"], fee_q=fee_q,
            balance_q=fee_q - row["cost_q"],
            cost_per_delivery_q=round(row["cost_q"] / len(refs)) if refs else 0,
        ))
    return tuple(sorted(rows, key=lambda row: (-row.cost_q, row.name)))


__all__ = ["BIDeliveryCostDay", "BIDeliveryCostReport", "BIDeliveryCostService", "build_bi_delivery_cost", "ride_cost_q"]
