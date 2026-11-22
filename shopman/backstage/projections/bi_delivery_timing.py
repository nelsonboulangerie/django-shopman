"""B.I. — tempo real de preparo e de chegada do entregador (WP-ENTREGADOR-CHAMADA-ANTECIPADA).

A chamada antecipada do entregador (depois do go-live) vai precisar de duas
previsões: quanto o preparo leva e quanto o entregador leva para chegar. Esta
leitura é o recorte que o dono vê enquanto o histórico se acumula, e é a mesma
conta que o modelo vai usar. Nada é estimado aqui: são medianas do que aconteceu.

- **Preparo real** = do primeiro "Iniciar preparo" do KDS (``KDSTicket.started_at``,
  que vale também para a comanda ainda não paga) até o Pronto do pedido
  (``Order.ready_at``). Sem início no KDS, o início é ``Order.preparing_at``, e o
  relatório conta quantos pedidos usaram essa troca (``prep_start_fallbacks``).
  Recortado por SKU (o pedido entra em cada SKU que contém), hora e dia da semana
  do início.
- **Chegada do entregador** = da corrida aberta na central
  (``Order.data["courier"]["requested_at"]``) até o aceite (``RideState.ASSIGNED``) e
  até a coleta (``RideState.ON_ROUTE``), pela hora de cada estado
  (``delivery_services.state_since``). Inclui as corridas que falharam e foram
  arquivadas em ``attempts`` (só têm aceite se a central aceitou). Recortado por
  hora e dia da semana da chamada.
- **Por serviço** (#2467): a mesma corrida, UMA vez por ``ride_ref`` (numa corrida
  com três pedidos, cada pedido tem o seu bloco, e a corrida conta uma vez), com o
  nome do cadastro do serviço e quatro medianas: até aceitar, até a coleta, na rua
  (da coleta à última entrega) e o total (da chamada à última entrega).

Tudo calculado na leitura (ADR-021 §3), janela default de 28 dias.
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

WEEKDAY_LABELS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass(frozen=True)
class BITimingRow:
    """Uma linha do recorte: quantos casos e a mediana, em minutos."""

    key: str
    label: str
    samples: int
    median_minutes: float


@dataclass(frozen=True)
class BIDeliveryTimingReport:
    date_from: str
    date_to: str
    #: Pedidos com preparo medido (início e Pronto).
    prep_samples: int
    #: Desses, quantos não tinham início no KDS e usaram ``preparing_at``.
    prep_start_fallbacks: int
    prep_by_sku: tuple[BITimingRow, ...]
    prep_by_hour: tuple[BITimingRow, ...]
    prep_by_weekday: tuple[BITimingRow, ...]
    #: Corridas com hora de abertura (a corrente e as arquivadas).
    rides: int
    courier_accept_by_hour: tuple[BITimingRow, ...]
    courier_accept_by_weekday: tuple[BITimingRow, ...]
    courier_pickup_by_hour: tuple[BITimingRow, ...]
    courier_pickup_by_weekday: tuple[BITimingRow, ...]
    #: Um serviço por linha, na ordem do nome, e o total embaixo (``service`` = ``TOTAL_KEY``).
    services: tuple[BIRideTimingService, ...] = ()


#: A chave da linha do total na tabela por serviço.
TOTAL_KEY = "__total__"


@dataclass(frozen=True)
class BIRideTimingService:
    """Os tempos das corridas de um serviço: quantas e a mediana de cada trecho, em minutos.

    ``None`` quando nenhuma corrida do serviço chegou àquele marco no período.
    """

    service: str
    name: str
    rides: int
    accept_minutes: float | None
    pickup_minutes: float | None
    street_minutes: float | None
    total_minutes: float | None


@dataclass
class _Ride:
    service: str
    requested: datetime
    assigned: datetime | None = None
    on_route: datetime | None = None
    done: datetime | None = None


def _earliest(current: datetime | None, other: datetime | None) -> datetime | None:
    return other if current is None or (other is not None and other < current) else current


def _latest(current: datetime | None, other: datetime | None) -> datetime | None:
    return other if current is None or (other is not None and other > current) else current


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    value = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return round(value, 1)


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _minutes(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None or end <= start:
        return None
    return (end - start).total_seconds() / 60


def _ride_minutes(start: datetime | None, end: datetime | None) -> float | None:
    """Como ``_minutes``, mas o marco no mesmo instante da chamada vale zero: o entregador
    da casa aceita quando é chamado, e esse zero é medida, não falta dela."""
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 60


def _window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    end = min(date_to or today, today)
    start = date_from or end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start > end:
        start = end
    if (end - start).days >= MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS - 1)
    return start, end


def _rows(groups: dict[str, list[float]], labels: dict[str, str], *, order: list[str] | None = None) -> tuple[BITimingRow, ...]:
    keys = order if order is not None else sorted(groups, key=lambda k: (-len(groups[k]), labels.get(k, k)))
    return tuple(
        BITimingRow(key=key, label=labels.get(key, key), samples=len(groups[key]), median_minutes=_median(groups[key]))
        for key in keys
        if groups.get(key)
    )


def _by_hour_and_weekday(samples: list[tuple[datetime, float]]) -> tuple[tuple[BITimingRow, ...], tuple[BITimingRow, ...]]:
    hours: dict[str, list[float]] = defaultdict(list)
    weekdays: dict[str, list[float]] = defaultdict(list)
    for moment, minutes in samples:
        local = timezone.localtime(moment)
        hours[f"{local.hour:02d}"].append(minutes)
        weekdays[str(local.weekday())].append(minutes)
    hour_labels = {f"{h:02d}": f"{h:02d}h" for h in range(24)}
    weekday_labels = {str(i): name for i, name in enumerate(WEEKDAY_LABELS)}
    return (
        _rows(hours, hour_labels, order=[f"{h:02d}" for h in range(24)]),
        _rows(weekdays, weekday_labels, order=[str(i) for i in range(7)]),
    )


def prep_start(order, ticket_starts: dict[str, datetime]) -> tuple[datetime | None, bool]:
    """O início do preparo do pedido e se veio da troca (``preparing_at``)."""
    started = ticket_starts.get(order.session_key or "")
    if started is not None:
        return started, False
    kds = [
        _parse(record.get("at"))
        for record in ((order.data or {}).get("kds_started") or {}).values()
        if isinstance(record, dict)
    ]
    kds = [moment for moment in kds if moment is not None]
    if kds:
        return min(kds), False
    return order.preparing_at, True


def build_bi_delivery_timing(*, date_from: date | None = None, date_to: date | None = None) -> BIDeliveryTimingReport:
    from django.db.models import Min
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSTicket

    start_day, end_day = _window(date_from, date_to)
    tz = timezone.get_current_timezone()
    since = datetime.combine(start_day, time.min, tzinfo=tz)
    until = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)

    # ── Preparo ──
    # Sem ``.only()``: o Order relê o status ao nascer, e campo adiado vira recursão.
    orders = list(Order.objects.filter(ready_at__gte=since, ready_at__lt=until))
    session_keys = [order.session_key for order in orders if order.session_key]
    ticket_starts = dict(
        KDSTicket.objects.filter(session_key__in=session_keys, started_at__isnull=False)
        .values("session_key")
        .annotate(first=Min("started_at"))
        .values_list("session_key", "first")
    )
    measured: dict[int, tuple[datetime, float]] = {}
    fallbacks = 0
    for order in orders:
        start, fallback = prep_start(order, ticket_starts)
        minutes = _minutes(start, order.ready_at)
        if minutes is None:
            continue
        measured[order.pk] = (start, minutes)
        fallbacks += int(fallback)

    by_sku: dict[str, list[float]] = defaultdict(list)
    sku_labels: dict[str, str] = {}
    seen: set[tuple[int, str]] = set()
    for order_id, sku, name in OrderItem.objects.filter(order_id__in=list(measured)).values_list("order_id", "sku", "name"):
        if (order_id, sku) in seen:
            continue
        seen.add((order_id, sku))
        by_sku[sku].append(measured[order_id][1])
        sku_labels.setdefault(sku, name or sku)
    prep_hour, prep_weekday = _by_hour_and_weekday(list(measured.values()))

    # ── Chegada do entregador ──
    # Uma corrida por ``ride_ref``: cada pedido dela guarda o seu bloco, com a sua parada.
    # A corrida chegou a cada marco quando o PRIMEIRO pedido chegou (aceite, coleta) e
    # terminou quando o ÚLTIMO foi entregue.
    from shopman.shop.models import DeliveryService

    default = DeliveryService.default()
    default_ref = default.ref if default else ""
    rides_by_key: dict[str, _Ride] = {}
    courier_orders = Order.objects.filter(data__has_key="courier", created_at__gte=since - timedelta(days=1), created_at__lt=until)
    for order in courier_orders:
        block = (order.data or {}).get("courier") or {}
        if not isinstance(block, dict):
            continue
        for index, ride in enumerate([*(block.get("attempts") or []), block]):
            if not isinstance(ride, dict):
                continue
            requested = _parse(ride.get("requested_at"))
            if requested is None or not (since <= requested < until):
                continue
            # A corrida arquivada antes de guardar o serviço abriu pelo do bloco (ou pelo padrão).
            service = str(ride.get("service") or block.get("service") or default_ref)
            reading = {**ride, "service": service}
            key = str(ride.get("ride_ref") or "") or f"{order.pk}:{index}"
            entry = rides_by_key.get(key)
            if entry is None:
                entry = rides_by_key[key] = _Ride(service=service, requested=requested)
            entry.requested = min(entry.requested, requested)
            # O estado da casa, não a letra do serviço (M1b-b, #2552).
            entry.assigned = _earliest(entry.assigned, _parse(delivery_services.state_since(reading, RideState.ASSIGNED)))
            entry.on_route = _earliest(entry.on_route, _parse(delivery_services.state_since(reading, RideState.ON_ROUTE)))
            entry.done = _latest(entry.done, _parse(delivery_services.state_since(reading, RideState.DONE)))
    rides = len(rides_by_key)
    accept = [(r.requested, m) for r in rides_by_key.values() if (m := _ride_minutes(r.requested, r.assigned)) is not None]
    pickup = [(r.requested, m) for r in rides_by_key.values() if (m := _ride_minutes(r.requested, r.on_route)) is not None]
    accept_hour, accept_weekday = _by_hour_and_weekday(accept)
    pickup_hour, pickup_weekday = _by_hour_and_weekday(pickup)

    return BIDeliveryTimingReport(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        prep_samples=len(measured),
        prep_start_fallbacks=fallbacks,
        prep_by_sku=_rows(by_sku, sku_labels),
        prep_by_hour=prep_hour,
        prep_by_weekday=prep_weekday,
        rides=rides,
        courier_accept_by_hour=accept_hour,
        courier_accept_by_weekday=accept_weekday,
        courier_pickup_by_hour=pickup_hour,
        courier_pickup_by_weekday=pickup_weekday,
        services=_service_rows(list(rides_by_key.values())),
    )


def _service_rows(rides: list[_Ride]) -> tuple[BIRideTimingService, ...]:
    """Um serviço por linha, na ordem do nome do cadastro, e o total embaixo."""
    from shopman.shop.models import DeliveryService

    if not rides:
        return ()
    names = dict(DeliveryService.objects.filter(ref__in={r.service for r in rides}).values_list("ref", "name"))

    def row(service: str, name: str, group: list[_Ride]) -> BIRideTimingService:
        def median(pairs) -> float | None:
            values = [m for start, end in pairs if (m := _ride_minutes(start, end)) is not None]
            return _median(values) if values else None

        return BIRideTimingService(
            service=service,
            name=name,
            rides=len(group),
            accept_minutes=median((r.requested, r.assigned) for r in group),
            pickup_minutes=median((r.requested, r.on_route) for r in group),
            street_minutes=median((r.on_route, r.done) for r in group),
            total_minutes=median((r.requested, r.done) for r in group),
        )

    by_service: dict[str, list[_Ride]] = defaultdict(list)
    for ride in rides:
        by_service[ride.service].append(ride)
    rows = sorted(
        (row(ref, names.get(ref) or delivery_services.SERVICE_FALLBACK_NAME, group) for ref, group in by_service.items()),
        key=lambda item: item.name.lower(),
    )
    return (*rows, row(TOTAL_KEY, "Todos os serviços", rides))


__all__ = ["TOTAL_KEY", "BIDeliveryTimingReport", "BIRideTimingService", "BITimingRow", "build_bi_delivery_timing", "prep_start"]
