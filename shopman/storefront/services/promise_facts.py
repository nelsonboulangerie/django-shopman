"""Os fatos por trás da promessa de quando, lidos de onde a casa já os decide.

A frase "Fica pronto amanhã, terça, a partir das 15h" é escrita em
``presentation/promise.py``. Este módulo só junta o que ela precisa saber, e
junta lendo os MESMOS serviços que o checkout e o envio do pedido consultam,
sem alterá-los:

- **o dia da fornada**: ``waitlist.next_batch_availability_for_skus``, a mesma
  pergunta que a reserva faz (``reserve_target_date``) quando o pronto de hoje
  não cobre;
- **o pronto de hoje**: a leitura de estoque de hoje do canal
  (``availability.stock_on_dates``), memorizada por request, a mesma que o
  cardápio já fez;
- **a hora de pronto**: ``product_readiness.ready_times_for``, a régua que corta
  os horários do checkout;
- **a grade do dia**: ``pickup_slots.annotate_slots_for_checkout``, a chamada
  exata que o checkout faz para montar os horários de retirada (meia hora hoje,
  turno da casa nos outros dias, nada em dia fechado ou depois do corte).

Mora em ``storefront/services`` e não na apresentação porque a apresentação não
lê ``shop.services`` (regra R-A de ``test_import_boundaries``). Só lê: nenhuma
escrita, nenhuma reserva.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

#: Até quantos dias à frente se procura um dia com horário para entregar a
#: promessa. Passado disso não há promessa: a tela não diz "hoje" nem inventa
#: uma data.
SEARCH_DAYS = 14


@dataclass
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


def _read_grid(day: date, *, now: datetime) -> tuple[time, ...]:
    from shopman.shop.services.product_readiness import parse_clock
    from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout

    try:
        context = annotate_slots_for_checkout([], delivery_date=day.isoformat(), now=now)
    except Exception:
        logger.warning("promise_facts: grid unavailable for %s", day, exc_info=True)
        return ()
    starts: list[time] = []
    for slot in context.get("pickup_slots") or []:
        start = parse_clock(slot.get("starts_at"))
        if start is not None and slot.get("enabled", True):
            starts.append(start)
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
    facts = PromiseFacts(now=current, today=today)
    unique = list(dict.fromkeys(sku for sku in skus if sku))
    if not unique:
        return facts

    if not day_known:
        facts.today_orderable = _today_orderable(
            unique, channel_ref=channel_ref, today=today, own_holds=own_holds or {}
        )
        waiting = [sku for sku in unique if not facts.today_orderable.get(sku, True)]
        if waiting:
            facts.next_batch = _next_batches(waiting, channel_ref=channel_ref)

    from shopman.shop.services.product_readiness import ReadinessUnavailable, ready_times_for

    try:
        facts.ready_at = ready_times_for(unique)
    except ReadinessUnavailable:
        logger.warning("promise_facts: readiness unavailable for %s", unique, exc_info=True)
        facts.readiness_unavailable = True
    return facts


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
        logger.warning("promise_facts: today stock unavailable for %s", skus, exc_info=True)
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
        logger.warning("promise_facts: next batch unavailable for %s", skus, exc_info=True)
        return {}
    return {sku: batch_day for sku, (batch_day, _info) in found.items()}
