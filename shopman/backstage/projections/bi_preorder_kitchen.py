"""B.I. — os dois tempos da encomenda na Cozinha, por pedido (decisão do dono, 09/11/2026).

A encomenda chega à Cozinha em hora combinada − preparo − antecedência, e chegar
NÃO é começar: o pedido fica Aceito até o "Iniciar" do posto. Por isso são dois
tempos, medidos por pedido (não por estação):

- **Espera na Cozinha** = de ``Order.data["kitchen_released_at"]`` (o despertador
  tocou, ou alguém liberou antes com ``release_preorder_now``) até o "Iniciar"
  (``Order.preparing_at``). Diz se a antecedência está folgada ou apertada.
- **Preparo** = do "Iniciar" (``Order.preparing_at``) ao "Pronto"
  (``Order.ready_at``). Diz se o tempo de preparo configurado
  (``Shop.defaults["preorder_kitchen"]``) bate com o real.

Só entra o pedido com ``kitchen_released_at``: venda do dia vai à Cozinha no
aceite e não tem espera de encomenda, e encomenda anterior ao carimbo não tem a
hora da chegada. Nenhum dos dois vira zero: fica de fora. Pedido que chegou e
ainda não foi iniciado aparece na lista sem os tempos (``None``), e as medianas
só contam os tempos medidos. Pedido cancelado fica de fora. O dia é o da
chegada à Cozinha, no fuso da loja. Tudo calculado na leitura (ADR-021 §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from shopman.shop.lifecycle import KITCHEN_RELEASED_AT_KEY

DEFAULT_WINDOW_DAYS = 28
MAX_WINDOW_DAYS = 366


@dataclass(frozen=True)
class BIPreorderKitchenRow:
    """Uma encomenda: quando chegou à Cozinha, quando começou, quando ficou pronta."""

    ref: str
    released_at: str
    started_at: str | None
    ready_at: str | None
    #: Chegada à Cozinha até o "Iniciar", em minutos; ``None`` sem "Iniciar".
    wait_minutes: float | None
    #: "Iniciar" até o "Pronto", em minutos; ``None`` sem os dois.
    prep_minutes: float | None


@dataclass(frozen=True)
class BIPreorderKitchenReport:
    date_from: str
    date_to: str
    #: Encomendas que chegaram à Cozinha no período (sem as canceladas).
    orders: int
    #: Dessas, quantas já tiveram o "Iniciar".
    started: int
    #: Dessas, quantas já ficaram prontas depois do "Iniciar".
    ready: int
    #: Mediana da espera na Cozinha (minutos); ``None`` sem nenhuma medida.
    wait_median_minutes: float | None
    #: Mediana do preparo (minutos); ``None`` sem nenhuma medida.
    prep_median_minutes: float | None
    #: Uma linha por encomenda, a chegada mais recente primeiro.
    rows: tuple[BIPreorderKitchenRow, ...]


def _window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    end = min(date_to or today, today)
    start = date_from or end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start > end:
        start = end
    if (end - start).days >= MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS - 1)
    return start, end


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _minutes(start: datetime | None, end: datetime | None) -> float | None:
    """Minutos de ``start`` a ``end``; zero vale (liberada e iniciada no mesmo gesto)."""
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 60, 1)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    value = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return round(value, 1)


def _iso(moment: datetime | None) -> str | None:
    return timezone.localtime(moment).replace(microsecond=0).isoformat() if moment else None


def build_bi_preorder_kitchen(
    *, date_from: date | None = None, date_to: date | None = None
) -> BIPreorderKitchenReport:
    from shopman.orderman.models import Order

    start_day, end_day = _window(date_from, date_to)
    tz = timezone.get_current_timezone()
    since = datetime.combine(start_day, time.min, tzinfo=tz)
    until = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)

    # O carimbo é ISO num JSON: o recorte do período é feito aqui, depois do parse.
    # A encomenda nasce antes de chegar à Cozinha, então ``created_at < until`` é
    # seguro como pré-filtro. Sem ``.only()``: o Order relê o status ao nascer.
    candidates = Order.objects.filter(
        data__has_key=KITCHEN_RELEASED_AT_KEY, created_at__lt=until
    ).exclude(status=Order.Status.CANCELLED)

    measured: list[tuple[datetime, BIPreorderKitchenRow]] = []
    for order in candidates:
        released = _parse((order.data or {}).get(KITCHEN_RELEASED_AT_KEY))
        if released is None or not (since <= released < until):
            continue
        started = order.preparing_at
        ready = order.ready_at if started is not None else None
        measured.append(
            (
                released,
                BIPreorderKitchenRow(
                    ref=order.ref,
                    released_at=_iso(released),
                    started_at=_iso(started),
                    ready_at=_iso(ready),
                    wait_minutes=_minutes(released, started),
                    prep_minutes=_minutes(started, ready),
                ),
            )
        )
    measured.sort(key=lambda item: (item[0], item[1].ref), reverse=True)
    rows = tuple(row for _, row in measured)
    waits = [row.wait_minutes for row in rows if row.wait_minutes is not None]
    preps = [row.prep_minutes for row in rows if row.prep_minutes is not None]

    return BIPreorderKitchenReport(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        orders=len(rows),
        started=sum(1 for row in rows if row.started_at is not None),
        ready=len(preps),
        wait_median_minutes=_median(waits),
        prep_median_minutes=_median(preps),
        rows=rows,
    )


__all__ = ["BIPreorderKitchenReport", "BIPreorderKitchenRow", "build_bi_preorder_kitchen"]
