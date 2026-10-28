"""B.I. — quanto a casa paga à TaOn pelas entregas, e quanto o frete cobre.

A corrida da TaOn é custo da casa: o frete do cliente não muda com ela. Esta
leitura soma o custo das corridas do período e põe ao lado o frete que os
clientes pagaram nos mesmos pedidos. A diferença é o que a entrega deixa ou
custa à casa.

- **Custo** = ``final_value_q`` de cada corrida (o valor que a TaOn fecha no
  ``F``), contado UMA vez por corrida (``id_mch``): numa corrida com várias
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

DEFAULT_WINDOW_DAYS = 28
MAX_WINDOW_DAYS = 366

FEE_SKU = "__DELIVERY_FEE__"


@dataclass(frozen=True)
class BIDeliveryCostDay:
    """Um dia: corridas, entregas, custo da TaOn e frete cobrado."""

    date: str
    rides: int
    deliveries: int
    cost_q: int
    fee_q: int


@dataclass(frozen=True)
class BIDeliveryCostReport:
    date_from: str
    date_to: str
    #: Corridas com custo (terminadas, ou canceladas com taxa).
    rides: int
    #: Pedidos levados nessas corridas (uma corrida pode levar vários).
    deliveries: int
    #: O que a casa paga à TaOn no período, uma vez por corrida.
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
    # A cotação é de uma parada só: na corrida com várias, ela não vale.
    if ride.get("status") == "F" and not ride.get("ride_orders"):
        estimate = ride.get("estimate") or {}
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
    seen: set[str] = set()
    per_day: dict[date, dict] = defaultdict(lambda: {"rides": 0, "refs": [], "cost_q": 0})
    estimated = 0
    for order in candidates:
        block = (order.data or {}).get("courier") or {}
        if not isinstance(block, dict):
            continue
        for ride in [*(block.get("attempts") or []), block]:
            if not isinstance(ride, dict):
                continue
            ride_id = str(ride.get("id_mch") or "")
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
    )


__all__ = ["BIDeliveryCostDay", "BIDeliveryCostReport", "build_bi_delivery_cost", "ride_cost_q"]
