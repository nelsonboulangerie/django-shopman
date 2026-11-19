"""A promessa do pedido ainda tem lastro? (WP-G08, "Promessa em risco").

Leitura pura. O Gestor mostrava a encomenda aceita e paga como se nada tivesse
acontecido depois de o lote dela ser cancelado: a reserva era solta, o vínculo
com o lote sumia do pedido e o cartão passava a parecer sem pendência (P0-1 do
plano do Gestor). Aqui a saúde da reserva é DERIVADA na leitura, do que o
estoque e a Produção dizem agora, e não de um carimbo que alguém esqueceu de
gravar.

## O que é "ter lastro"

A régua é a que o orquestrador já usa, lida em lote:

- **reserva presa a um saldo** tem lastro (``adapters/stock.hold_backing``:
  ``quant`` preenchido), enquanto o saldo cobrir o que está reservado nele;
- **reserva acima do saldo** perdeu lastro: é a mesma conta de
  ``handlers/_stock_receivers._overbooked_holds_on_production_quants`` (o que
  sobra de reserva acima do saldo), com a mesma ordem de quem fica (o pedido
  antes da sacola, quem reservou primeiro antes de quem chegou depois);
- **reserva solta ou vencida** de um pedido ainda aberto é reserva perdida;
- **demanda sem saldo** (``quant`` vazio) só conta como coberta pelo que a
  produção DA DATA ainda tem livre. A sobra de hoje nunca lastreia encomenda
  (dono, 18/11/2026): a encomenda mede só o lote da data.

O saldo de produção de um produto numa data é UM bolo, mesmo quando o Stockman
o guarda em dois saldos (o planejado e o que já entrou em produção,
``batch="started"``): o lote que abre tira a quantidade do primeiro e põe no
segundo. Desde o conserto da #2709 as reservas vão junto; o bolo único continua
valendo porque um lote parcialmente aberto deixa quantidade nos dois saldos, e
medir saldo a saldo acusaria pedido que o outro saldo cobre.

## O que a leitura responde

Por pedido, só quando há o que dizer (:class:`OrderPromiseProjection`):

- ``at_risk`` ("Promessa em risco"): algum item ficou sem lastro, no todo ou
  em parte, ou o lote dele está atrasado. Cada item diz o produto, quanto
  falta e por quê (lote cancelado, fechado com menos que o planejado, atrasado,
  produção que não cobre, estoque menor que o reservado);
- ``waiting_batch`` ("Esperando o lote"): a reserva está inteira, mas o lote de
  hoje ainda não ficou pronto. Não é risco, é espera; o preparo não começa
  antes do pão existir. Não depende do estado da fila de espera
  (``waitlist.state_for`` devolve ``none`` para o pedido pago e para a
  encomenda, e o selo do Gestor pegava carona nele: P1-22).

Pedido com a reserva inteira num lote de data FUTURA não aparece aqui: está
como deve estar.

## O próximo passo

Aviso que não diz o que fazer não é aviso (regra de omotenashi do dono,
19/11/2026). Cada item em risco traz ``next_step``, a frase do que o operador
faz agora, pela causa; a promessa traz a frase do pedido inteiro e
``recommended_action``, a saída que resolve:

- o item não vai existir (lote cancelado, fechado com menos, reserva de fora,
  estoque menor, reserva solta): avisar o cliente. Quando a casa tem o que
  oferecer no lugar, a frase diz o quê e quanto (``alternatives``), pelo MESMO
  mecanismo de substitutos da loja (``shop/services/substitutes.find``); para a
  encomenda de outro dia, a conta é a do lote da data, nunca a sobra de hoje.
  Sem alternativa, remarcar para o próximo lote: a frase não promete o que não há;
- o lote está atrasado: avisar do atraso (a leitura não conhece hora nova, e
  não inventa uma);
- a Produção ainda pode resolver (sem lote planejado, plano que não cobre):
  pedir à Produção, e a saída recomendada é abrir o plano daquele dia.

"Esperando o lote" não tem próximo passo: é espera, ninguém precisa agir.

## Custo

Uma leitura por painel, com um número FIXO de consultas, qualquer que seja o
número de pedidos (as reservas dos pedidos; as reservas que disputam os mesmos
saldos; os saldos de produção; os lotes; os nomes; a hora de prontidão). Com
todas as reservas já baixadas, que é o caso do pedido de agora, é uma consulta
só. Nada aqui grava.

As alternativas custam uma busca de substitutos por item EM RISCO distinto
(produto, quanto falta, canal e data), nunca por pedido do painel: doze
encomendas que perderam o mesmo lote com a mesma quantidade custam uma busca.
Painel sem pedido em risco não busca nada.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.formatting import format_clock

from shopman.shop.projections.types import Action

logger = logging.getLogger(__name__)

STATE_AT_RISK = "at_risk"
STATE_WAITING_BATCH = "waiting_batch"

LABEL_AT_RISK = "Promessa em risco"
LABEL_WAITING_BATCH = "Esperando o lote"
_STATE_LABELS = {STATE_AT_RISK: LABEL_AT_RISK, STATE_WAITING_BATCH: LABEL_WAITING_BATCH}

#: A reserva do item: inteira, em parte ou perdida.
RESERVATION_WHOLE = "whole"
RESERVATION_PARTIAL = "partial"
RESERVATION_LOST = "lost"

#: Por que o item aparece. Só ``batch_waiting`` não é risco.
CAUSE_BATCH_WAITING = "batch_waiting"
CAUSE_BATCH_LATE = "batch_late"
CAUSE_BATCH_CANCELLED = "batch_cancelled"
CAUSE_BATCH_SHORT = "batch_short"
CAUSE_BATCH_CLOSED = "batch_closed"
CAUSE_PLAN_SHORT = "plan_short"
CAUSE_NO_BATCH = "no_batch"
CAUSE_STOCK_SHORT = "stock_short"
CAUSE_HOLD_RELEASED = "hold_released"

#: Da causa que mais pesa à que menos pesa, quando um item tem mais de uma reserva.
_CAUSE_ORDER = (
    CAUSE_BATCH_CANCELLED,
    CAUSE_BATCH_SHORT,
    CAUSE_BATCH_CLOSED,
    CAUSE_PLAN_SHORT,
    CAUSE_NO_BATCH,
    CAUSE_STOCK_SHORT,
    CAUSE_HOLD_RELEASED,
    CAUSE_BATCH_LATE,
    CAUSE_BATCH_WAITING,
)
#: A reserva segue inteira; o que falta é o lote ficar pronto.
BATCH_NOT_OUT = frozenset({CAUSE_BATCH_WAITING, CAUSE_BATCH_LATE})

#: Causas que não falam de lote nenhum: o item não ganha dia de lote.
_NO_BATCH_CAUSES = frozenset({CAUSE_STOCK_SHORT, CAUSE_HOLD_RELEASED})

#: As saídas de uma promessa em risco. A recomendada vem primeiro
#: (``order_queue._promise_card_actions``); "Abrir a Produção" só existe quando o
#: item ainda pode ser produzido e para quem opera a Produção.
ACTION_CONTACT_CUSTOMER = "contact-customer"
ACTION_RESCHEDULE_AT_POS = "reschedule-at-pos"
ACTION_OPEN_PRODUCTION = "open-production"
ACTION_CANCEL = "cancel"

#: Causas que a Produção ainda resolve: planejar o lote, ou aumentá-lo.
PRODUCTION_CAUSES = frozenset({CAUSE_NO_BATCH, CAUSE_PLAN_SHORT})
#: Causas em que o item não vai existir como combinado: a casa oferece outro no lugar.
_ALTERNATIVE_CAUSES = frozenset({
    CAUSE_BATCH_CANCELLED, CAUSE_BATCH_SHORT, CAUSE_BATCH_CLOSED, CAUSE_STOCK_SHORT, CAUSE_HOLD_RELEASED,
})
#: A ordem das frases do pedido: primeiro o que protege o cliente, depois o que
#: se pede à Produção.
_NEXT_STEP_ORDER = (
    CAUSE_BATCH_CANCELLED,
    CAUSE_BATCH_SHORT,
    CAUSE_BATCH_CLOSED,
    CAUSE_STOCK_SHORT,
    CAUSE_HOLD_RELEASED,
    CAUSE_BATCH_LATE,
    CAUSE_PLAN_SHORT,
    CAUSE_NO_BATCH,
)
#: Quantas alternativas a frase oferece, no máximo.
ALTERNATIVES_LIMIT = 2

#: O lote fechou com menos e não há o que oferecer no lugar: as duas saídas do que faltou.
STEP_SHORT = "Remarque o que faltou ou devolva a diferença."
STEP_PLAN = "Peça à Produção para planejar."
STEP_PLAN_MORE = "Peça à Produção para aumentar o lote."

#: O bloqueio do preparo de quem espera o lote, nas palavras que o cartão já usa.
BATCH_WAIT_BLOCK_LABEL = "Esperando o lote…"
BATCH_WAIT_BLOCK_REASON = "O preparo abre quando o lote ficar pronto."

_LOT_STATUS_PHRASE = {"planned": "não começou", "started": "está em andamento"}
_ORDER_REFERENCE_PREFIX = "order:"
_ZERO = Decimal("0")


@dataclass(frozen=True)
class OrderPromiseAlternativeProjection:
    """Um produto que a casa pode oferecer no lugar do item em risco.

    Vem de ``shop/services/substitutes.find``, o mesmo mecanismo da loja.
    ``available_display`` diz quanto há e para quando: "12 livres para amanhã"
    (o que o lote da data ainda tem sem encomenda) ou "8 disponíveis hoje".
    A tela escreve uma por linha, sob "Sugestões:" (dono, 19/11/2026), e o
    ``sku`` segue para o PDV no "Remarcar no PDV" (:func:`pos_suggestions`). O
    preço fica de fora, porque nenhuma tela o lê (#2765).
    """

    sku: str
    name: str
    available_display: str


@dataclass(frozen=True)
class OrderPromiseItemProjection:
    """Um produto do pedido cuja promessa pede atenção, ou espera o lote.

    ``reservation``: ``whole`` | ``partial`` | ``lost``. ``cause``: por que o
    item aparece (``batch_waiting``, ``batch_late``, ``batch_cancelled``,
    ``batch_short``, ``batch_closed``, ``plan_short``, ``no_batch``,
    ``stock_short``, ``hold_released``). ``qty`` é o que o pedido reservou do
    produto e ``missing_qty`` o que ficou sem lastro, já como texto de tela
    ("10", "0,35"). ``label`` diz o produto e quanto falta; ``detail``, o
    porquê, com a hora do lote quando ela é conhecida.

    ``batch_date`` (ISO) é o dia do lote que a reserva mede; ``batch_status``
    o estado dele (``planned`` | ``started`` | ``finished`` | ``void`` | "");
    ``batch_ready_at_iso`` quando ele deve ficar pronto (a hora de prontidão do
    produto, ``product_readiness``), vazio quando a casa não sabe a hora.

    ``label`` é o fato em português de balcão ("Faltam 4x Focaccia"; a palavra
    "reserva" não aparece, dono 19/11/2026). ``alternatives`` é o que a casa pode
    oferecer no lugar (até :data:`ALTERNATIVES_LIMIT`), quando o item não vai
    existir como combinado: a tela as lista sob "Sugestões:". ``next_step`` só
    diz o que a tela ainda não disse: o que pedir à Produção, as saídas do lote
    que fechou com menos, ou que não há produto parecido. Nunca repete o verbo
    do botão ("Avisar o cliente" já é a saída cheia) nem cita as alternativas;
    vazio em quem só espera o lote, no lote atrasado e quando há sugestões.
    """

    sku: str
    name: str
    reservation: str
    cause: str
    at_risk: bool
    qty: str
    missing_qty: str
    label: str
    detail: str
    batch_date: str = ""
    batch_status: str = ""
    batch_ready_at_iso: str = ""
    work_order_refs: tuple[str, ...] = ()
    next_step: str = ""
    alternatives: tuple[OrderPromiseAlternativeProjection, ...] = ()


@dataclass(frozen=True)
class OrderPromiseProjection:
    """A promessa de um pedido que pede atenção ou espera: o selo e os itens.

    ``state``: ``at_risk`` ("Promessa em risco") | ``waiting_batch``
    ("Esperando o lote"). ``blocks_start``: o preparo não começa agora, porque
    o lote de um item reservado ainda não ficou pronto. ``since_iso``: desde
    quando a promessa está em risco, quando há um instante para dizer (a
    reserva solta, o lote fechado com menos). ``actions`` só existe no risco:
    avisar o cliente, remarcar no PDV, abrir a Produção, cancelar (preenchidas
    por quem monta o cartão ou o detalhe, :func:`with_actions`).

    ``next_step`` é a frase do pedido inteiro, quando algum item tem uma (ver
    :class:`OrderPromiseItemProjection`). ``recommended_action`` é a ``ref`` da
    saída que a situação pede: ``contact-customer`` quando algum item não vai
    existir como combinado ou está atrasado; ``open-production`` quando tudo o
    que falta a Produção ainda resolve. Em ``actions`` ela vem primeiro, com
    ``priority="primary"``; quem não pode abrir a Produção não recebe a ação, e
    a frase segue dizendo o que fazer.
    """

    state: str
    label: str
    items: tuple[OrderPromiseItemProjection, ...]
    blocks_start: bool = False
    since_iso: str = ""
    actions: tuple[Action, ...] = ()
    next_step: str = ""
    recommended_action: str = ""


# ── Leitura ──────────────────────────────────────────────────────────────────


@dataclass
class _Claim:
    """Uma reserva de ``Order.data["hold_ids"]``, com o que a leitura apurou dela."""

    order_ref: str
    sku: str
    pk: int
    qty: Decimal
    missing: Decimal = _ZERO
    cause: str = ""
    day: date | None = None
    since: datetime | None = None


def _decimal(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def _qty_text(value: Decimal) -> str:
    """A quantidade como a tela a escreve: "10", "0,35"."""
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f").replace(".", ",")


def _is_order_hold(metadata) -> bool:
    return str((metadata or {}).get("reference") or "").startswith(_ORDER_REFERENCE_PREFIX)


def _order_claims(orders) -> list[_Claim]:
    """As reservas que cada pedido aberto diz ter (``Order.data["hold_ids"]``).

    É a lista que a baixa e o cancelamento leem (``services/stock``): a reserva
    que saiu dela por edição ou remarcação não é mais do pedido. Pedido de teste
    e SKU sem ledger não reservam; entrada fora do formato canônico é defeito de
    quem gravou, e o pedido fica de fora da leitura com erro no log, para um
    registro torto não derrubar o painel inteiro.
    """
    from shopman.shop.services.order_helpers import is_test_order
    from shopman.shop.services.production_promise import OPEN_STATUSES
    from shopman.shop.services.stock import is_untracked_hold_entry

    claims: list[_Claim] = []
    for order in orders:
        if order.status not in OPEN_STATUSES or is_test_order(order):
            continue
        own: list[_Claim] = []
        try:
            for entry in (order.data or {}).get("hold_ids") or ():
                if is_untracked_hold_entry(entry) or not entry.get("hold_id"):
                    continue
                prefix, _sep, number = str(entry["hold_id"]).partition(":")
                if prefix != "hold" or not number.isdigit():
                    raise ValueError(f"hold_id fora do formato canônico: {entry['hold_id']!r}")
                own.append(_Claim(
                    order_ref=order.ref, sku=str(entry.get("sku") or ""), pk=int(number), qty=_decimal(entry.get("qty")),
                ))
        except (AttributeError, TypeError, ValueError, ArithmeticError):
            logger.error("order_promise: hold_ids ilegível order=%s", order.ref, exc_info=True)
            continue
        claims.extend(own)
    return claims


def _cover(supply: Decimal, rows: list[dict]) -> dict[int, Decimal]:
    """Reparte ``supply`` entre as reservas e devolve o que ficou SEM cobertura, por reserva.

    Primeiro quem está preso ao saldo, depois a demanda sem saldo; dentro de
    cada grupo, o pedido antes da sacola, a prioridade carimbada na reserva
    (``StockPlanning.realize``) e, por fim, quem reservou primeiro.
    """

    def rank(row):
        metadata = row["metadata"] or {}
        try:
            priority = (0, int(metadata["priority"])) if metadata.get("priority") is not None else (1, 0)
        except (TypeError, ValueError):
            priority = (1, 0)
        return (
            0 if row["quant_id"] is not None else 1,
            0 if _is_order_hold(metadata) else 1,
            priority,
            row["created_at"],
            row["pk"],
        )

    uncovered: dict[int, Decimal] = {}
    remaining = max(supply, _ZERO)
    for row in sorted(rows, key=rank):
        covered = min(row["quantity"], remaining)
        remaining -= covered
        if covered < row["quantity"]:
            uncovered[row["pk"]] = row["quantity"] - covered
    return uncovered


def _gap_cause(lots: list[dict], day: date, today: date, *, anchored: bool) -> str:
    """Por que a produção de ``day`` não cobre a reserva. ``""`` = ainda não é risco.

    Só a demanda de data futura sem lote nenhum fica de fora: a Produção ainda
    não planejou o dia, e é assim que toda encomenda feita com antecedência
    nasce (o plano vem depois, e a cobre sem ancorar).
    """
    if not lots:
        if anchored:
            return CAUSE_PLAN_SHORT
        return CAUSE_NO_BATCH if day <= today else ""
    void = [lot for lot in lots if lot["status"] == "void"]
    live = [lot for lot in lots if lot["status"] in ("planned", "started")]
    done = [lot for lot in lots if lot["status"] == "finished"]
    if void and not live and not done:
        return CAUSE_BATCH_CANCELLED
    if any(_is_short(lot) for lot in done):
        return CAUSE_BATCH_SHORT
    if void:
        return CAUSE_BATCH_CANCELLED
    return CAUSE_PLAN_SHORT if live else CAUSE_BATCH_CLOSED


def _is_short(lot: dict) -> bool:
    return lot["finished"] is not None and lot["finished"] < lot["quantity"]


def _lot_status(lots: list[dict]) -> str:
    """O estado do lote do dia, no que interessa a quem espera por ele."""
    statuses = {lot["status"] for lot in lots}
    for status in ("started", "planned", "finished", "void"):
        if status in statuses:
            return status
    return ""


def _ready_times(skus: set[str]) -> dict:
    """A hora de prontidão de cada produto (``product_readiness``), ou nada se não deu para ler."""
    if not skus:
        return {}
    from shopman.shop.services import product_readiness

    try:
        return product_readiness.ready_times_for(sorted(skus))
    except Exception:
        # Sem a hora, a leitura não inventa atraso: o item só espera o lote.
        logger.warning("order_promise: prontidão indisponível", exc_info=True)
        return {}


def _products(skus: set[str]) -> dict[str, tuple[str, str]]:
    """``{sku: (nome, política de disponibilidade)}`` do catálogo."""
    from shopman.offerman.models import Product

    return {
        sku: (name, policy)
        for sku, name, policy in Product.objects.filter(sku__in=skus).values_list("sku", "name", "availability_policy")
    }


def read_for(orders, *, now: datetime | None = None) -> dict[str, OrderPromiseProjection]:
    """``{ref: promessa}`` dos pedidos que têm o que dizer. Uma leitura para o painel inteiro."""
    from shopman.stockman.models import Hold, HoldStatus, Quant

    claims = _order_claims(orders)
    if not claims:
        return {}
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    live_statuses = (HoldStatus.PENDING, HoldStatus.CONFIRMED)

    # 1. As reservas dos pedidos, em qualquer estado.
    holds = {hold.pk: hold for hold in Hold.objects.filter(pk__in={claim.pk for claim in claims}).select_related("quant")}

    def is_live(hold) -> bool:
        return hold.status in live_statuses and (hold.expires_at is None or hold.expires_at >= now)

    pending: list[_Claim] = []
    physical_quants: dict[int, Decimal] = {}
    pool_keys: set[tuple[str, date]] = set()
    lot_keys: set[tuple[str, date]] = set()
    for claim in claims:
        hold = holds.get(claim.pk)
        if hold is not None and hold.status == HoldStatus.FULFILLED:
            continue  # já baixada: o produto saiu do estoque para este pedido
        pending.append(claim)
        if hold is not None and claim.qty <= 0:
            claim.qty = hold.quantity  # entrada sem quantidade: vale a da própria reserva
        if hold is None or not is_live(hold):
            lot_keys.add((claim.sku, hold.target_date if hold is not None else today))
        elif hold.quant_id is None:
            pool_keys.add((hold.sku, hold.target_date))
        elif hold.quant.target_date is None:
            physical_quants[hold.quant_id] = hold.quant.quantity
        else:
            pool_keys.add((hold.sku, hold.quant.target_date))
    if not pending:
        return {}
    lot_keys |= pool_keys

    # 2. Todas as reservas vivas que disputam os mesmos saldos, e 3. os saldos de produção.
    uncovered: dict[int, Decimal] = {}
    pool_supply: dict[tuple[str, date], Decimal] = defaultdict(lambda: _ZERO)
    if physical_quants or pool_keys:
        pool_skus = {sku for sku, _day in pool_keys}
        pool_days = {day for _sku, day in pool_keys}
        contested = Q()
        if physical_quants:
            contested |= Q(quant_id__in=list(physical_quants))
        if pool_keys:
            contested |= Q(quant__sku__in=pool_skus, quant__target_date__in=pool_days)
            contested |= Q(quant__isnull=True, sku__in=pool_skus, target_date__in=pool_days)
        rows = list(
            Hold.objects.filter(status__in=live_statuses)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
            .filter(contested)
            .values("pk", "sku", "quantity", "target_date", "created_at", "metadata", "quant_id", "quant__target_date")
        )
        by_physical: dict[int, list[dict]] = defaultdict(list)
        by_pool: dict[tuple[str, date], list[dict]] = defaultdict(list)
        for row in rows:
            if row["quant_id"] is not None and row["quant__target_date"] is None:
                by_physical[row["quant_id"]].append(row)
                continue
            key = (row["sku"], row["quant__target_date"] or row["target_date"])
            if key in pool_keys:
                by_pool[key].append(row)
        for quant_id, quantity in physical_quants.items():
            uncovered.update(_cover(quantity, by_physical[quant_id]))
        if pool_keys:
            for sku, day, quantity in Quant.objects.filter(
                sku__in=pool_skus, target_date__in=pool_days,
            ).values_list("sku", "target_date", "_quantity"):
                pool_supply[(sku, day)] += quantity
            for key in pool_keys:
                uncovered.update(_cover(pool_supply[key], by_pool[key]))

    # 4. Os lotes dos dias em jogo: cancelado, fechado com menos, em andamento.
    lots: dict[tuple[str, date], list[dict]] = defaultdict(list)
    if lot_keys:
        from shopman.craftsman.models import WorkOrder

        for lot in WorkOrder.objects.filter(
            output_sku__in={sku for sku, _day in lot_keys}, target_date__in={day for _sku, day in lot_keys},
        ).values("ref", "output_sku", "target_date", "status", "quantity", "finished", "finished_at"):
            key = (lot["output_sku"], lot["target_date"])
            if key in lot_keys:
                lots[key].append(lot)

    # 5. A política de cada produto com demanda sem saldo: o feito na hora não espera lote.
    floating = {
        claim.sku for claim in pending
        if (hold := holds.get(claim.pk)) is not None and is_live(hold) and hold.quant_id is None
    }
    products = _products({claim.sku for claim in pending}) if floating else {}

    # Cada reserva pendente: o que falta dela e por quê.
    waiting: list[_Claim] = []
    for claim in pending:
        hold = holds.get(claim.pk)
        if hold is None or not is_live(hold):
            claim.day = hold.target_date if hold is not None else today
            claim.missing = claim.qty
            claim.since = hold.resolved_at if hold is not None else None
            claim.cause = (
                CAUSE_BATCH_CANCELLED
                if any(lot["status"] == "void" for lot in lots[(claim.sku, claim.day)])
                else CAUSE_HOLD_RELEASED
            )
            continue
        gap = min(uncovered.get(hold.pk, _ZERO), claim.qty)
        if hold.quant_id is not None and hold.quant.target_date is None:
            if gap > 0:
                claim.missing, claim.cause = gap, CAUSE_STOCK_SHORT
            continue
        anchored = hold.quant_id is not None
        claim.day = hold.quant.target_date if anchored else hold.target_date
        if not anchored and products.get(claim.sku, ("", ""))[1] == "demand_ok":
            continue  # feito na hora: a reserva sem saldo é o desenho, não uma falta
        key = (claim.sku, claim.day)
        if gap > 0:
            cause = _gap_cause(lots[key], claim.day, today, anchored=anchored)
            if cause:
                claim.missing, claim.cause = gap, cause
                short = [lot["finished_at"] for lot in lots[key] if _is_short(lot) and lot["finished_at"]]
                claim.since = max(short) if cause == CAUSE_BATCH_SHORT and short else None
            continue
        if claim.day <= today and (anchored or pool_supply[key] > 0):
            waiting.append(claim)  # reserva inteira num lote que ainda não ficou pronto

    # 6. A hora de prontidão, só para quem espera o lote de hoje.
    ready_times = _ready_times({claim.sku for claim in waiting})
    ready_at: dict[int, datetime] = {}
    for claim in waiting:
        ready = ready_times.get(claim.sku)
        if ready is not None and claim.day == today:
            ready_at[claim.pk] = timezone.make_aware(datetime.combine(today, ready))
        late = claim.day < today or (claim.pk in ready_at and now > ready_at[claim.pk])
        claim.cause = CAUSE_BATCH_LATE if late else CAUSE_BATCH_WAITING
        claim.since = ready_at.get(claim.pk) if late else None

    # Os nomes de quem tem o que dizer (quando a consulta da política não os trouxe).
    unnamed = {claim.sku for claim in pending if claim.cause} - set(products)
    if unnamed:
        products.update(_products(unnamed))

    # A soma do que cada pedido reservou de cada produto, com as já baixadas.
    reserved: dict[tuple[str, str], Decimal] = defaultdict(lambda: _ZERO)
    for claim in claims:
        reserved[(claim.order_ref, claim.sku)] += claim.qty
    by_item: dict[tuple[str, str], list[_Claim]] = defaultdict(list)
    for claim in pending:
        if claim.cause:
            by_item[(claim.order_ref, claim.sku)].append(claim)

    status_by_ref = {order.ref: order.status for order in orders}
    order_by_ref = {order.ref: order for order in orders}
    alternatives = _AlternativeFinder(today)
    items_by_order: dict[str, list[tuple[OrderPromiseItemProjection, datetime | None]]] = defaultdict(list)
    for (order_ref, sku), item_claims in by_item.items():
        lead = min(item_claims, key=lambda claim: _CAUSE_ORDER.index(claim.cause))
        moments = [claim.since for claim in item_claims if claim.since is not None]
        items_by_order[order_ref].append((
            _item(
                sku=sku,
                name=products.get(sku, ("", ""))[0] or sku,
                qty=reserved[(order_ref, sku)],
                missing=sum((claim.missing for claim in item_claims), _ZERO),
                cause=lead.cause,
                day=lead.day,
                lots=lots[(sku, lead.day)] if lead.day is not None and lead.cause not in _NO_BATCH_CAUSES else [],
                ready_at=ready_at.get(lead.pk),
                alternatives_for=lambda missing, order_ref=order_ref, sku=sku: alternatives.find(
                    order_by_ref[order_ref], sku, missing,
                ),
            ),
            min(moments) if moments else None,
        ))

    promises: dict[str, OrderPromiseProjection] = {}
    for order_ref, entries in items_by_order.items():
        items = tuple(sorted((item for item, _since in entries), key=lambda item: (not item.at_risk, item.name)))
        at_risk = any(item.at_risk for item in items)
        state = STATE_AT_RISK if at_risk else STATE_WAITING_BATCH
        moments = [since for item, since in entries if item.at_risk and since is not None]
        next_step, recommended_action = _order_guidance(items)
        promises[order_ref] = OrderPromiseProjection(
            state=state,
            label=_STATE_LABELS[state],
            items=items,
            blocks_start=(
                status_by_ref.get(order_ref) == Order.Status.ACCEPTED
                and any(item.cause in BATCH_NOT_OUT for item in items)
            ),
            since_iso=min(moments).isoformat() if moments else "",
            next_step=next_step,
            recommended_action=recommended_action,
        )
    return promises


# ── O próximo passo ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Offer:
    """O que a busca de alternativas achou. ``none_phrase``: a frase de quando ela achou nada."""

    options: tuple[OrderPromiseAlternativeProjection, ...] = ()
    none_phrase: str = ""


def _nothing_alike(target: date | None) -> str:
    """A busca rodou e não há o que oferecer: dito, para a lista vazia não parecer esquecimento."""
    if target is not None:
        return f"Nenhum produto parecido livre para {_day_label(target)}."
    return "Nenhum produto parecido disponível hoje."


class _AlternativeFinder:
    """O que a casa oferece no lugar de um item em risco, com memória dentro da leitura.

    Uma busca por (produto, quanto falta, canal, data): os pedidos que perderam
    o mesmo lote com a mesma quantidade dividem a resposta.
    """

    def __init__(self, today: date) -> None:
        self._today = today
        self._found: dict[tuple, _Offer] = {}

    def find(self, order, sku: str, missing: Decimal) -> _Offer:
        from shopman.shop.services.order_helpers import get_commitment_date

        commitment = get_commitment_date(order)
        # Só a encomenda de outro dia mede o lote da data; a de hoje, o que há agora.
        target = commitment if commitment is not None and commitment > self._today else None
        key = (sku, missing, order.channel_ref, target)
        if key not in self._found:
            found = self._search(sku, missing, order.channel_ref, target)
            self._found[key] = _Offer(
                options=found or (),
                # A busca que falhou não afirma que não há nada: a tela só cala.
                none_phrase="" if found is None else _nothing_alike(target),
            )
        return self._found[key]

    @staticmethod
    def _search(sku: str, missing: Decimal, channel_ref: str, target: date | None):
        from shopman.shop.services import substitutes

        try:
            found = substitutes.find(
                sku, qty=missing if missing > 0 else Decimal("1"), channel=channel_ref or None,
                limit=ALTERNATIVES_LIMIT, target_date=target,
            )
        except Exception:
            # Sem saber o que há para oferecer, a tela não sugere nem nega nada.
            logger.warning("order_promise: alternativas indisponíveis sku=%s", sku, exc_info=True)
            return None
        return tuple(
            OrderPromiseAlternativeProjection(
                sku=row["sku"],
                name=row["name"],
                available_display=_available_display(int(row.get("available_qty") or 0), target, requested=missing),
            )
            for row in found[:ALTERNATIVES_LIMIT]
        )


def _available_display(available: int, target: date | None, *, requested: Decimal = _ZERO) -> str:
    """ "12 livres para amanhã" (o lote da data) ou "8 disponíveis hoje".

    Na leitura de hoje, o produto sem teto (feito na hora, ou fora do ledger)
    volta de ``substitutes.find`` com a própria quantidade pedida, porque "cabe o
    que se pediu". Esse número não é contagem: a frase diz só "disponível hoje",
    em vez de afirmar uma quantidade que ninguém contou.
    """
    if target is not None:
        return f"{available} {'livre' if available == 1 else 'livres'} para {_day_label(target)}"
    if available <= 0 or available == int(requested):
        return "disponível hoje"
    return f"{available} {'disponível' if available == 1 else 'disponíveis'} hoje"


def _one_of(parts: list[str]) -> str:
    """ "A", "A ou B", "A, B ou C"."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} ou {parts[-1]}"


def _all_of(parts: list[str]) -> str:
    """ "A", "A e B", "A, B e C"."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} e {parts[-1]}"


def next_step_for(cause: str, *, alternatives=(), none_phrase: str = "") -> str:
    """O que a tela ainda precisa dizer sobre um item em risco, numa frase. ``""`` quando não há.

    O verbo do botão não se repete aqui ("Avisar o cliente" é a saída cheia), e
    as alternativas não entram na frase: a tela as lista sob "Sugestões:".
    """
    if cause == CAUSE_NO_BATCH:
        return STEP_PLAN
    if cause == CAUSE_PLAN_SHORT:
        return STEP_PLAN_MORE
    if cause not in _ALTERNATIVE_CAUSES or alternatives:
        return ""
    if cause == CAUSE_BATCH_SHORT:
        return STEP_SHORT
    return none_phrase


def _order_guidance(items) -> tuple[str, str]:
    """A frase do pedido inteiro e a saída recomendada, dos itens em risco.

    Quando todos os itens em risco têm a mesma frase, ela vale para o pedido.
    Senão, cada frase leva o nome do produto na frente ("Baguete: peça à
    Produção…"), primeiro o que protege o cliente e depois o que se pede à
    Produção. Item sem frase (o que tem sugestões, o lote atrasado) não entra.
    """
    risky = sorted((item for item in items if item.at_risk), key=lambda item: _NEXT_STEP_ORDER.index(item.cause))
    if not risky:
        return "", ""
    names_by_step: dict[str, list[str]] = {}
    for item in risky:
        if item.next_step:
            names_by_step.setdefault(item.next_step, []).append(item.name)
    if not names_by_step:
        next_step = ""
    elif len(names_by_step) == 1 and len(risky) == 1:
        next_step = risky[0].next_step
    elif len(names_by_step) == 1 and all(item.next_step for item in risky):
        next_step = next(iter(names_by_step))
    else:
        next_step = " ".join(f"{_all_of(names)}: {_after_colon(step)}" for step, names in names_by_step.items())
    recommended = (
        ACTION_OPEN_PRODUCTION if all(item.cause in PRODUCTION_CAUSES for item in risky) else ACTION_CONTACT_CUSTOMER
    )
    return next_step, recommended


def pos_suggestions(promise: OrderPromiseProjection) -> list[dict]:
    """As sugestões que seguem com o "Remarcar no PDV": o item que falta e o que oferecer no lugar.

    Um registro por item em risco com alternativa: ``{"sku", "qty", "offer"}``,
    onde ``qty`` é o que falta (decimal com ponto) e ``offer`` os SKUs
    sugeridos, na ordem da tela. É uma dica para o PDV abrir a troca já montada
    (#2765): quem grava relê a disponibilidade, a URL não reserva nada.
    """
    return [
        {
            "sku": item.sku,
            "qty": item.missing_qty.replace(",", "."),
            "offer": [option.sku for option in item.alternatives],
        }
        for item in promise.items
        if item.at_risk and item.alternatives
    ]


def production_day(promise: OrderPromiseProjection) -> str:
    """O dia (ISO) do plano que a Produção precisa abrir: o do primeiro item que ela ainda resolve."""
    return next(
        (item.batch_date for item in promise.items if item.at_risk and item.cause in PRODUCTION_CAUSES and item.batch_date),
        "",
    )


# ── Frases ───────────────────────────────────────────────────────────────────


def _day_label(day: date) -> str:
    from shopman.backstage.projections.order_attention import commitment_day_label

    return commitment_day_label(day)


def _item(
    *, sku: str, name: str, qty: Decimal, missing: Decimal, cause: str, day: date | None, lots: list[dict],
    ready_at: datetime | None, alternatives_for=None,
) -> OrderPromiseItemProjection:
    missing = min(max(missing, _ZERO), qty) if qty > 0 else max(missing, _ZERO)
    offer = alternatives_for(missing) if alternatives_for is not None and cause in _ALTERNATIVE_CAUSES else _Offer()
    alternatives = offer.options
    lacks = "Falta" if missing == 1 else "Faltam"
    if missing <= 0:
        reservation, label = RESERVATION_WHOLE, f"{_qty_text(qty)}x {name}"
    elif missing >= qty:
        reservation, label = RESERVATION_LOST, f"{lacks} {_qty_text(qty)}x {name}"
    else:
        reservation, label = RESERVATION_PARTIAL, f"{lacks} {_qty_text(missing)} de {_qty_text(qty)}x {name}"
    return OrderPromiseItemProjection(
        sku=sku,
        name=name,
        reservation=reservation,
        cause=cause,
        at_risk=cause != CAUSE_BATCH_WAITING,
        qty=_qty_text(qty),
        missing_qty=_qty_text(missing),
        label=label,
        detail=_detail(cause, day=day, lots=lots, ready_at=ready_at),
        batch_date=day.isoformat() if day is not None and cause not in _NO_BATCH_CAUSES else "",
        batch_status=_lot_status(lots),
        batch_ready_at_iso=ready_at.isoformat() if ready_at is not None else "",
        work_order_refs=tuple(sorted(lot["ref"] for lot in lots)),
        next_step=next_step_for(cause, alternatives=alternatives, none_phrase=offer.none_phrase),
        alternatives=alternatives,
    )


def _detail(cause: str, *, day: date | None, lots: list[dict], ready_at: datetime | None) -> str:
    """O porquê do item, numa frase, com a hora do lote quando a casa a conhece."""
    when = _day_label(day) if day is not None else ""
    status = _LOT_STATUS_PHRASE.get(_lot_status(lots), "")
    if cause == CAUSE_BATCH_WAITING:
        first = f"O lote de {when} {status}." if status else f"O lote de {when} ainda não ficou pronto."
        return f"{first} Fica pronto às {format_clock(ready_at)}." if ready_at is not None else first
    if cause == CAUSE_BATCH_LATE:
        if ready_at is not None:
            tail = f" e {status}" if status else " e ainda não ficou pronto"
            return f"O lote de {when} está atrasado: devia ficar pronto às {format_clock(ready_at)}{tail}."
        return f"O lote de {when} não ficou pronto."
    if cause == CAUSE_BATCH_CANCELLED:
        others = any(lot["status"] != "void" for lot in lots)
        if others:
            return f"Um lote de {when} foi cancelado, e o que ficou não cobre o pedido."
        return f"O lote de {when} foi cancelado."
    if cause == CAUSE_BATCH_SHORT:
        short = [lot for lot in lots if _is_short(lot)]
        finished = sum((lot["finished"] for lot in short), _ZERO)
        planned = sum((lot["quantity"] for lot in short), _ZERO)
        return f"O lote de {when} fechou com {_qty_text(finished)}, e o planejado era {_qty_text(planned)}."
    if cause == CAUSE_BATCH_CLOSED:
        return f"O lote de {when} já fechou e esta reserva ficou de fora."
    if cause == CAUSE_PLAN_SHORT:
        return f"A produção planejada para {when} não cobre o pedido."
    if cause == CAUSE_NO_BATCH:
        return f"Não há lote planejado para {when}."
    if cause == CAUSE_STOCK_SHORT:
        return "O estoque é menor que o reservado."
    if cause == CAUSE_HOLD_RELEASED:
        return "A reserva deste item foi solta."
    return ""


def risk_reason(promise: OrderPromiseProjection) -> str:
    """Os itens em risco numa frase só: o que falta e por quê, item a item."""
    return " ".join(f"{item.label}. {item.detail}" for item in promise.items if item.at_risk)


def batch_lines(promise: OrderPromiseProjection, *, causes=BATCH_NOT_OUT) -> str:
    """O lote de cada item que ainda não ficou pronto: o produto, o estado e a hora quando há."""
    return " ".join(f"{item.name}: {_after_colon(item.detail)}" for item in promise.items if item.cause in causes)


def _after_colon(sentence: str) -> str:
    """A frase do item depois de "Produto: ": continua a oração, em minúscula."""
    return sentence[:1].lower() + sentence[1:]


def batch_wait_reason(promise: OrderPromiseProjection) -> str:
    """Por que o preparo não começa: a regra e o lote de cada item."""
    return f"{BATCH_WAIT_BLOCK_REASON} {batch_lines(promise)}".strip()


def with_actions(promise: OrderPromiseProjection, actions) -> OrderPromiseProjection:
    """A promessa em risco com as saídas ao lado (quem monta sabe o usuário e a tela)."""
    return replace(promise, actions=tuple(actions))
