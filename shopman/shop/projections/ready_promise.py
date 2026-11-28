"""Quando o item fica pronto: UM fato, para a Loja e para o Google.

A Loja escreve a frase ("Fica pronto amanhã, terça, a partir das 15h") em
``storefront/presentation/promise.py``; o envio ao Google
(``adapters/catalog_projection_google``) manda o ``pickupSla`` de cada item. Os
dois leem o dia daqui, de :func:`ready_window`, e por isso nunca divergem: o
Google cruza o inventário local com a página do produto, e a divergência sozinha
nega a "retirada no mesmo dia" (recusa de 01/11/2026, issue #2652).

Mora no ``shop`` porque o ``storefront`` importa o ``shop``, nunca o contrário; e
em ``projections`` porque a apresentação da Loja só lê ``shop.projections``
(regra R-A de ``test_import_boundaries``). Só lê: nenhuma escrita, nenhuma
reserva.

Os fatos vêm dos MESMOS serviços que o checkout e o envio do pedido consultam:

- **o dia da fornada**: ``waitlist.next_batch_availability_for_skus``, a mesma
  pergunta que a reserva faz (``reserve_target_date``) quando o pronto de hoje
  não cobre;
- **o pronto de hoje**: a leitura de estoque de hoje do canal
  (``availability.stock_on_dates``);
- **a hora de pronto**: ``product_readiness.ready_times_for``, a régua que corta
  os horários do checkout;
- **a grade do dia**: ``fulfillment_window.annotate``, a chamada que monta os
  horários de retirada do checkout (meia hora hoje, turno da casa nos outros
  dias, nada em dia fechado ou depois do corte).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

#: Até quantos dias à frente se procura um dia com horário para entregar a
#: promessa. Passado disso não há promessa: ninguém diz "hoje" nem inventa data.
SEARCH_DAYS = 14


@dataclass(frozen=True)
class PromiseFacts:
    """O que a promessa precisa saber, para um conjunto de SKUs, num instante."""

    now: datetime
    today: date
    #: SKU → dia da primeira fornada planejada elegível do canal.
    next_batch: dict[str, date] = field(default_factory=dict)
    #: SKU → há o que vender HOJE (pronto ou em produção) para uma unidade.
    today_orderable: dict[str, bool] = field(default_factory=dict)
    #: SKU → hora a partir da qual o checkout aceita a retirada.
    ready_at: dict[str, time] = field(default_factory=dict)
    #: A prontidão não pôde ser apurada. O checkout recusa todo horário nesse
    #: caso, então nenhuma promessa sai.
    readiness_unavailable: bool = False
    #: Grade lida por dia, memorizada nesta leitura (o dicionário muda, o fato não).
    _grids: dict[date, tuple[time, ...]] = field(default_factory=dict)

    def grid(self, day: date) -> tuple[time, ...]:
        """Os inícios dos horários que o checkout oferece em ``day``, sem o carrinho.

        Vazio: não há horário nesse dia (fechado, feriado, ou hoje depois do
        corte). O corte da prontidão é aplicado por quem pergunta, com a mesma
        comparação de ``fulfillment_window.annotate`` (começo ≥ hora de pronto).
        """
        if day not in self._grids:
            self._grids[day] = _read_grid(day, now=self.now)
        return self._grids[day]

    def first_window(self, day: date, ready_at: time | None) -> tuple[date, time] | None:
        """O primeiro horário oferecível a partir de ``day``, para um item que fica pronto às ``ready_at``.

        Dia sem horário (casa fechada, corte do dia, dia sem expediente) passa
        para o próximo dia com horário. ``None`` quando nenhum dia da busca tem.
        """
        for offset in range(SEARCH_DAYS + 1):
            candidate = day + timedelta(days=offset)
            for start in self.grid(candidate):
                if ready_at is None or start >= ready_at:
                    return candidate, start
        return None


@dataclass(frozen=True)
class ReadyWindow:
    """O primeiro horário em que a casa entrega o item.

    ``target`` é o dia em que o item existe (hoje, ou o da fornada); ``day`` é o
    dia do primeiro horário com retirada a partir dele, que pode ser posterior
    (casa fechada, corte do dia).
    """

    target: date
    day: date
    start: time
    ready_at: time | None


def ready_window(
    sku: str,
    facts: PromiseFacts,
    *,
    orderable: bool,
    planned_for: date | None = None,
) -> ReadyWindow | None:
    """Quando ``sku`` fica pronto para retirada, ou ``None`` quando não há promessa.

    ``orderable`` é a decisão de venda que quem pergunta já tomou (o botão
    Adicionar acende; o item vai disponível ao Google). ``planned_for`` é o dia
    da fornada que uma linha da sacola já reservou: ali a data é fato da
    reserva, não estimativa.

    Sem promessa: item que não se vende, prontidão que não pôde ser apurada,
    fornada que não se achou, ou nenhum dia com horário na busca. Nunca "hoje"
    por falta de dado.
    """
    if not orderable or facts.readiness_unavailable:
        return None

    if planned_for is not None:
        target = max(planned_for, facts.today)
    elif facts.today_orderable.get(sku, True):
        target = facts.today
    else:
        target = facts.next_batch.get(sku)
        if target is None:
            return None

    ready_at = facts.ready_at.get(sku)
    found = facts.first_window(target, ready_at)
    if found is None:
        return None
    day, start = found
    return ReadyWindow(target=target, day=day, start=start, ready_at=ready_at)


_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def day_label_for(day: date, *, today: date) -> str:
    """O dia como a loja o diz: "hoje", "amanhã, terça", "quinta, 26/11".

    Fonte única: a promessa da loja (``storefront/presentation/promise``) e a frase
    da troca de dia da sacola (``policies.preorder_date``) dizem o dia daqui.
    """
    weekday = _WEEKDAYS[day.weekday()]
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return f"amanhã, {weekday}"
    return f"{weekday}, {day:%d/%m}"


def opening_slot(day: date, *, now: datetime | None = None) -> time | None:
    """O primeiro horário que o checkout oferece em ``day``, ou ``None`` (dia sem horário).

    É a "abertura" do dia escolhido no cardápio (OC-33 B1): o item que fica
    disponível nesse horário não ganha frase; o que fica depois diz a hora.
    """
    from django.utils import timezone

    grid = _read_grid(day, now=now or timezone.now())
    return grid[0] if grid else None


def _read_grid(day: date, *, now: datetime) -> tuple[time, ...]:
    from shopman.shop.services import fulfillment_window

    try:
        context = fulfillment_window.annotate(day, [], now=now)
    except Exception:
        logger.warning("ready_promise: grid unavailable for %s", day, exc_info=True)
        return ()
    starts: list[time] = []
    for window in context.get("windows") or []:
        start = fulfillment_window.slot_start(window)
        if start is not None and window.get("enabled"):
            starts.append(start.replace(second=0, microsecond=0))
    return tuple(sorted(starts))


def read_promise_facts(
    skus: list[str],
    *,
    channel_ref: str,
    own_holds: dict[str, int | Decimal] | None = None,
    now: datetime | None = None,
    day_known: bool = False,
) -> PromiseFacts:
    """Lê, em lote, os fatos da promessa para ``skus`` neste canal.

    ``own_holds`` é a reserva da própria sessão por SKU: o que esta cliente já
    reservou para hoje continua sendo dela, e não empurra a promessa dela para a
    fornada de amanhã. ``day_known``: quem pergunta já sabe o dia de cada item
    (a linha da sacola, pela reserva), e o estoque não é lido.
    """
    from django.utils import timezone

    current = now or timezone.now()
    today = timezone.localtime(current).date() if timezone.is_aware(current) else current.date()
    unique = list(dict.fromkeys(sku for sku in skus if sku))
    if not unique:
        return PromiseFacts(now=current, today=today)

    today_orderable: dict[str, bool] = {}
    next_batch: dict[str, date] = {}
    if not day_known:
        today_orderable = _today_orderable(
            unique, channel_ref=channel_ref, today=today, own_holds=own_holds or {}
        )
        waiting = [sku for sku in unique if not today_orderable.get(sku, True)]
        if waiting:
            next_batch = _next_batches(waiting, channel_ref=channel_ref)

    from shopman.shop.services.product_readiness import ReadinessUnavailable, ready_times_for

    ready_at: dict[str, time] = {}
    readiness_unavailable = False
    try:
        ready_at = ready_times_for(unique)
    except ReadinessUnavailable:
        logger.warning("ready_promise: readiness unavailable for %s", unique, exc_info=True)
        readiness_unavailable = True
    return PromiseFacts(
        now=current,
        today=today,
        next_batch=next_batch,
        today_orderable=today_orderable,
        ready_at=ready_at,
        readiness_unavailable=readiness_unavailable,
    )


def _today_orderable(
    skus: list[str],
    *,
    channel_ref: str,
    today: date,
    own_holds: dict[str, int | Decimal],
) -> dict[str, bool]:
    """Por SKU: dá para vender uma unidade com o que existe para HOJE.

    Mesma pergunta de ``waitlist.reserve_target_date``: a fornada só entra
    quando o pronto (e o em produção) de hoje não cobre. SKU sem leitura de
    estoque (bundle, sem ledger) é de hoje, como o cardápio já o trata.
    """
    from shopman.shop.projections.catalog_context import promised_ceiling
    from shopman.shop.services import waitlist
    from shopman.shop.services.availability import stock_on_dates

    try:
        reading = stock_on_dates(skus, [today], **waitlist.scope_kwargs(channel_ref))[today]
    except Exception:
        logger.warning("ready_promise: today stock unavailable for %s", skus, exc_info=True)
        return {}
    out: dict[str, bool] = {}
    for sku in skus:
        raw = reading.get(sku)
        if raw is None:
            out[sku] = True
            continue
        can_order, ceiling = promised_ceiling(raw)
        if ceiling is None:
            out[sku] = bool(can_order)
            continue
        own = Decimal(str(own_holds.get(sku) or 0))
        out[sku] = ceiling + own >= 1
    return out


def _next_batches(skus: list[str], *, channel_ref: str) -> dict[str, date]:
    from shopman.shop.services import waitlist

    try:
        found = waitlist.next_batch_availability_for_skus(skus, channel_ref=channel_ref)
    except Exception:
        logger.warning("ready_promise: next batch unavailable for %s", skus, exc_info=True)
        return {}
    return {sku: batch_day for sku, (batch_day, _info) in found.items()}
