"""A Produção cobre as encomendas de cada dia? (WP-G10, "Agenda com cobertura").

Leitura pura. A lista de Encomendas do Gestor dizia, pedido a pedido, o que
cada cliente espera; ninguém somava o dia. O furo ("sábado: 42 prometidos, 38
planejados") só aparecia no próprio sábado, pedido a pedido, quando já não dava
para planejar mais um lote. Aqui a soma é feita POR DIA e POR PRODUTO, ao lado
do que a Produção planejou para aquela data.

## Os dois fatos

- **Prometido**: a soma das quantidades dos pedidos que a casa já ACEITOU
  (``accepted``, ``preparing``, ``ready``) com aquele combinado
  (``Order.data["delivery_date"]``). São os mesmos pedidos da lista de
  Encomendas (os de data futura), mais as encomendas de HOJE (``is_preorder``
  gravado no commit, ou ``kitchen_released_at``), inclusive as que já foram
  para a Cozinha. O pedido novo ainda mora em "Novos" e não é promessa; o
  cancelado e o encerrado saíram da conta; balcão e pedido de teste nunca
  entram. As quantidades são as que valem agora
  (``order_composition.effective_items``, com o ajuste por cima), e o combo é
  aberto nos componentes, como a reserva faz (``services/stock``).
- **Planejado**: a soma dos lotes do Craftsman para o produto NAQUELA data
  (``WorkOrder.output_sku`` e ``target_date``): o planejado e o em andamento
  contam pela quantidade do lote (``quantity``), o pronto pelo que rendeu
  (``finished``). Lote cancelado (``void``) não conta.

A encomenda de uma data só é coberta pelo lote daquela data, nunca pela sobra
de outro dia (dono, 18/11/2026): é a mesma regra da leitura
``projections/order_promise``.

## Quem não entra na conta de lote

- produto **feito na hora** (``availability_policy == "demand_ok"``: café,
  sanduíche) não espera lote nenhum;
- produto que a casa **não produz** (sem ficha ativa e sem lote na data, a
  revenda) sai do estoque.

Os dois aparecem na lista do dia, com o prometido, e dizem por que não há
planejado ao lado; nenhum deles pinta o dia como falta.

## Custo

Uma leitura para a agenda inteira, com um número FIXO de consultas, qualquer
que seja o número de pedidos, de dias ou de produtos (os pedidos; os ajustes;
os itens; os componentes dos combos; os produtos; os lotes; as fichas). Sem
encomenda aberta é uma consulta só. Nada aqui grava: planejar ou alterar lote
é da Produção, e a agenda só leva até lá.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.order_promise import _qty_text

#: Pedido que a casa aceitou e ainda vai sair: é o que está prometido.
PROMISED_STATUSES = ("accepted", "preparing", "ready")

#: O estado de um produto no dia.
PRODUCT_COVERED = "covered"
PRODUCT_SHORT = "short"
PRODUCT_NO_BATCH = "no_batch"
PRODUCT_MADE_TO_ORDER = "made_to_order"
PRODUCT_FROM_STOCK = "from_stock"

#: O estado do dia: o pior entre os produtos que dependem de lote.
DAY_SHORT = "short"
DAY_NO_BATCH = "no_batch"
DAY_COVERED = "covered"
DAY_NOT_BATCH_BASED = "not_batch_based"

_PRODUCT_LABELS = {
    PRODUCT_COVERED: "Lote cobre",
    PRODUCT_SHORT: "Lote não cobre",
    PRODUCT_NO_BATCH: "Sem lote",
    PRODUCT_MADE_TO_ORDER: "Feito na hora",
    PRODUCT_FROM_STOCK: "Do estoque",
}
_DAY_LABELS = {
    DAY_SHORT: "Produção não cobre",
    DAY_NO_BATCH: "Sem lote",
    DAY_COVERED: "Produção cobre",
    DAY_NOT_BATCH_BASED: "Não depende de lote",
}

HEADLINE_COVERED = "A produção cobre as encomendas."
HEADLINE_NOT_BATCH_BASED = "Nenhum item depende de lote."

#: O atalho do dia: o Planejamento da Produção aberto naquela data.
PRODUCTION_LINK_LABEL = "Abrir a Produção"

#: Na ordem em que a lista do dia mostra: primeiro quem pede alguém.
_PRODUCT_ORDER = (PRODUCT_SHORT, PRODUCT_NO_BATCH, PRODUCT_COVERED, PRODUCT_MADE_TO_ORDER, PRODUCT_FROM_STOCK)
#: Os produtos que entram na conta de lote do dia.
_BATCH_STATES = frozenset({PRODUCT_COVERED, PRODUCT_SHORT, PRODUCT_NO_BATCH})

_MADE_TO_ORDER_POLICY = "demand_ok"
_LOT_VOID = "void"
_LOT_FINISHED = "finished"
_ZERO = Decimal("0")


@dataclass(frozen=True)
class PreorderCoverageProductProjection:
    """Um produto prometido num dia, ao lado do que a Produção planejou para ele.

    ``state``: ``covered`` (os lotes da data cobrem) | ``short`` (há lote, e ele
    não cobre) | ``no_batch`` (nenhum lote na data) | ``made_to_order`` (feito
    na hora) | ``from_stock`` (a casa não produz, sai do estoque). Só os três
    primeiros entram na conta de lote; nos outros dois ``planned_qty``,
    ``missing_qty`` e ``surplus_qty`` vêm vazios, e a tela não os pinta como
    falta.

    As quantidades vêm como texto de tela ("42", "0,35") e ``*_display`` como
    a casa escreve ("42x", "0,35 kg"). ``missing_qty`` é o que falta planejar
    ("0" em quem está coberto) e ``surplus_qty`` o que os lotes têm a mais.
    ``label`` é a frase de quem pede alguém ("Faltam 4 Kuro Pan", "Sem lote
    para Ciabatta"), vazia nos demais; ``detail`` diz a conta ou o porquê.
    ``orders_count``: quantas encomendas do dia levam o produto.
    ``batch_count``: quantos lotes vivos (não cancelados) há na data.
    """

    sku: str
    name: str
    unit: str
    state: str
    state_label: str
    promised_qty: str
    promised_display: str
    planned_qty: str
    planned_display: str
    missing_qty: str
    surplus_qty: str
    label: str
    detail: str
    orders_count: int
    batch_count: int


@dataclass(frozen=True)
class PreorderCoverageDayProjection:
    """Um dia com encomenda: o prometido de cada produto ao lado do planejado.

    ``date`` (ISO) é o mesmo dia do ``commitment_date`` do cartão: é por ele
    que a tela casa o cabeçalho com o grupo da lista. ``day_label`` é o dia
    como o cartão o diz ("hoje", "amanhã", "sex, 20/11"); ``days_ahead``,
    quantos dias faltam (0 = hoje).

    ``state``: ``short`` (algum produto tem lote que não cobre) | ``no_batch``
    (nenhum falta, mas algum ainda não tem lote na data) | ``covered`` (os
    lotes cobrem tudo que depende de lote) | ``not_batch_based`` (nada no dia
    depende de lote). ``headline`` é a frase pronta do cabeçalho.

    ``production_url`` abre o Planejamento da Produção naquele dia; vazio
    quando a Produção não tem endereço configurado ou quem lê não a opera (aí
    o cabeçalho fica sem o atalho). ``production_label`` é o nome do atalho.
    """

    date: str
    day_label: str
    days_ahead: int
    state: str
    state_label: str
    headline: str
    orders_count: int
    products: tuple[PreorderCoverageProductProjection, ...]
    production_url: str = ""
    production_label: str = ""


@dataclass(frozen=True)
class PreorderCoverageProjection:
    """A agenda com cobertura: os dias com encomenda, de hoje em diante."""

    days: tuple[PreorderCoverageDayProjection, ...] = ()


# ── Leitura ──────────────────────────────────────────────────────────────────


def _promised_orders(today: date) -> list[tuple[Order, date]]:
    """Os pedidos aceitos com combinado de hoje em diante, cada um com o dia dele.

    De data futura, todo pedido aceito (a régua da lista de Encomendas,
    ``order_queue._is_future_preorder``). De hoje, só a encomenda: o pedido do
    dia comum também tem ``delivery_date`` e não é promessa de agenda.
    """
    from shopman.shop import lifecycle
    from shopman.shop.services.order_helpers import get_commitment_date, is_test_order
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    found: list[tuple[Order, date]] = []
    queryset = Order.objects.filter(status__in=PROMISED_STATUSES, data__has_key="delivery_date").order_by("created_at")
    for order in queryset:
        day = get_commitment_date(order)
        if day is None or day < today:
            continue
        if is_test_order(order) or is_pos_counter_order(order):
            continue
        data = order.data or {}
        if day == today and not (data.get("is_preorder") or data.get(lifecycle.KITCHEN_RELEASED_AT_KEY)):
            continue
        found.append((order, day))
    return found


def _bundle_components(skus: set[str]) -> dict[str, list[tuple[str, Decimal]]]:
    """``{combo: [(componente, quantidade por combo)]}`` dos SKUs que são combo."""
    from shopman.offerman.models import ProductComponent

    components: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    rows = ProductComponent.objects.filter(parent__sku__in=skus).values_list("parent__sku", "component__sku", "qty")
    for parent, component, qty in rows:
        components[parent].append((component, qty))
    return components


def _counts_as_product(item) -> bool:
    """A linha é mercadoria? A taxa de entrega e o que não é produção ficam de fora."""
    meta = item.meta or {}
    return not (meta.get("non_production") or meta.get("type") == "delivery_fee")


def build_preorder_coverage(*, user=None, now: datetime | None = None) -> PreorderCoverageProjection:
    """A cobertura de cada dia com encomenda, de hoje em diante. Uma leitura para a agenda."""
    from shopman.craftsman.models import Recipe, WorkOrder
    from shopman.offerman.models import Product

    from shopman.shop.services import order_composition

    now = now or timezone.now()
    today = timezone.localtime(now).date()

    # 1. Os pedidos prometidos; 2 e 3. os itens que valem agora (com o ajuste por cima).
    orders = _promised_orders(today)
    if not orders:
        return PreorderCoverageProjection()
    items_by_order = order_composition.effective_items_by_order_id([order.pk for order, _day in orders])

    # 4. Os combos abertos nos componentes, como a reserva faz.
    lines = [
        (order.pk, day, item)
        for order, day in orders
        for item in items_by_order.get(order.pk, ())
        if item.sku and _counts_as_product(item)
    ]
    components = _bundle_components({item.sku for _pk, _day, item in lines})

    promised: dict[tuple[date, str], Decimal] = defaultdict(lambda: _ZERO)
    orders_of: dict[tuple[date, str], set[int]] = defaultdict(set)
    for pk, day, item in lines:
        for sku, per_unit in components.get(item.sku) or [(item.sku, Decimal("1"))]:
            promised[(day, sku)] += item.qty * per_unit
            orders_of[(day, sku)].add(pk)
    orders_by_day: dict[date, set[int]] = defaultdict(set)
    for order, day in orders:
        orders_by_day[day].add(order.pk)

    skus = {sku for _day, sku in promised}
    days = sorted(orders_by_day)

    # 5. Os produtos: o nome, a unidade e a política (o feito na hora não espera lote).
    products = {
        sku: (name, unit, policy)
        for sku, name, unit, policy in Product.objects.filter(sku__in=skus).values_list(
            "sku", "name", "unit", "availability_policy",
        )
    }

    # 6. Os lotes de cada produto em cada dia; 7. quem a casa produz (ficha ativa).
    lots: dict[tuple[date, str], list[dict]] = defaultdict(list)
    for lot in WorkOrder.objects.filter(output_sku__in=skus, target_date__in=days).values(
        "output_sku", "target_date", "status", "quantity", "finished",
    ):
        lots[(lot["target_date"], lot["output_sku"])].append(lot)
    produced = set(Recipe.objects.filter(output_sku__in=skus, is_active=True).values_list("output_sku", flat=True))

    can_open_production = _operates_production(user)
    day_projections = []
    for day in days:
        rows = []
        for (row_day, sku), qty in promised.items():
            if row_day != day or qty <= 0:
                continue
            row = _product_row(
                sku=sku,
                product=products.get(sku),
                promised=qty,
                lots=lots.get((day, sku), []),
                produced=sku in produced,
                orders_count=len(orders_of[(day, sku)]),
            )
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda row: (_PRODUCT_ORDER.index(row.state), row.name, row.sku))
        day_projections.append(_day_projection(
            day, today=today, rows=tuple(rows), orders_count=len(orders_by_day[day]),
            production_url=_production_url(day) if can_open_production else "",
        ))
    return PreorderCoverageProjection(days=tuple(day_projections))


# ── O produto no dia ─────────────────────────────────────────────────────────


def _lot_supply(lot: dict) -> Decimal:
    """Quanto o lote põe na conta: o que rendeu, se já ficou pronto; senão, o planejado."""
    if lot["status"] == _LOT_FINISHED and lot["finished"] is not None:
        return lot["finished"]
    return lot["quantity"]


def _display(qty: Decimal, unit: str) -> str:
    """A quantidade como a casa escreve: "4x"; por peso ou volume, "0,35 kg"."""
    return f"{_qty_text(qty)}x" if _is_count(unit) else f"{_qty_text(qty)} {unit}"


def _is_count(unit: str) -> bool:
    return unit in ("", "un")


def _amount_of(qty_text: str, unit: str, name: str) -> str:
    """ "6 Baguete de tradição"; por peso, "0,35 kg de Queijo da Canastra"."""
    return f"{qty_text} {name}" if _is_count(unit) else f"{qty_text} {unit} de {name}"


def _product_row(
    *, sku: str, product: tuple[str, str, str] | None, promised: Decimal, lots: list[dict], produced: bool,
    orders_count: int,
) -> PreorderCoverageProductProjection | None:
    """O produto no dia. ``None`` para o SKU que o catálogo não conhece e a Produção não faz."""
    if product is None and not lots and not produced:
        return None
    name, unit, policy = product or (sku, "un", "")
    live = [lot for lot in lots if lot["status"] != _LOT_VOID]
    planned = sum((_lot_supply(lot) for lot in live), _ZERO)

    if policy == _MADE_TO_ORDER_POLICY:
        state, detail = PRODUCT_MADE_TO_ORDER, "Feito na hora: não depende de lote."
    elif not lots and not produced:
        state, detail = PRODUCT_FROM_STOCK, "Sai do estoque: a casa não produz este item."
    elif not live:
        state = PRODUCT_NO_BATCH
        detail = "O lote do dia foi cancelado." if lots else "Nenhum lote planejado para o dia."
    else:
        state = PRODUCT_COVERED if planned >= promised else PRODUCT_SHORT
        detail = f"As encomendas somam {_display(promised, unit)} e os lotes, {_display(planned, unit)}."

    in_batch_account = state in _BATCH_STATES
    missing = max(promised - planned, _ZERO) if in_batch_account else _ZERO
    surplus = max(planned - promised, _ZERO) if in_batch_account else _ZERO
    if state == PRODUCT_SHORT:
        label = f"{'Falta' if missing < 2 else 'Faltam'} {_amount_of(_qty_text(missing), unit, name)}"
    elif state == PRODUCT_NO_BATCH:
        label = f"Sem lote para {name}"
    else:
        label = ""
    return PreorderCoverageProductProjection(
        sku=sku,
        name=name,
        unit=unit,
        state=state,
        state_label=_PRODUCT_LABELS[state],
        promised_qty=_qty_text(promised),
        promised_display=_display(promised, unit),
        planned_qty=_qty_text(planned) if in_batch_account else "",
        planned_display=_display(planned, unit) if in_batch_account else "",
        missing_qty=_qty_text(missing) if in_batch_account else "",
        surplus_qty=_qty_text(surplus) if in_batch_account else "",
        label=label,
        detail=detail,
        orders_count=orders_count,
        batch_count=len(live),
    )


# ── O dia ────────────────────────────────────────────────────────────────────


def _join(parts: list[str]) -> str:
    """ "A", "A e B", "A, B e C"."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} e {parts[-1]}"


def _headline(rows: tuple[PreorderCoverageProductProjection, ...], state: str) -> str:
    """A frase do cabeçalho do dia: o que falta e o que não tem lote, com nome."""
    if state == DAY_COVERED:
        return HEADLINE_COVERED
    if state == DAY_NOT_BATCH_BASED:
        return HEADLINE_NOT_BATCH_BASED
    sentences = []
    short = [row for row in rows if row.state == PRODUCT_SHORT]
    if len(short) == 1:
        sentences.append(short[0].label)
    elif short:
        # Mais de um produto: um verbo só, "Faltam 6 Baguete e 2 Ciabatta".
        sentences.append("Faltam " + _join([_amount_of(row.missing_qty, row.unit, row.name) for row in short]))
    no_batch = [row.name for row in rows if row.state == PRODUCT_NO_BATCH]
    if no_batch:
        sentences.append(f"Sem lote para {_join(no_batch)}")
    return ". ".join(sentences) + "."


def _day_state(rows: tuple[PreorderCoverageProductProjection, ...]) -> str:
    states = {row.state for row in rows}
    if PRODUCT_SHORT in states:
        return DAY_SHORT
    if PRODUCT_NO_BATCH in states:
        return DAY_NO_BATCH
    return DAY_COVERED if PRODUCT_COVERED in states else DAY_NOT_BATCH_BASED


def _day_projection(
    day: date, *, today: date, rows: tuple[PreorderCoverageProductProjection, ...], orders_count: int,
    production_url: str,
) -> PreorderCoverageDayProjection:
    from shopman.backstage.projections.order_attention import commitment_day_label

    state = _day_state(rows)
    return PreorderCoverageDayProjection(
        date=day.isoformat(),
        day_label=commitment_day_label(day),
        days_ahead=(day - today).days,
        state=state,
        state_label=_DAY_LABELS[state],
        headline=_headline(rows, state),
        orders_count=orders_count,
        products=rows,
        production_url=production_url,
        production_label=PRODUCTION_LINK_LABEL if production_url else "",
    )


# ── O atalho ─────────────────────────────────────────────────────────────────


def _operates_production(user) -> bool:
    """Quem lê abre a Produção? A mesma pergunta que o app faz na porta (``hub._REGISTRY``)."""
    from shopman.backstage.permissions import can_operate_production

    return bool(user is not None and getattr(user, "is_authenticated", False) and can_operate_production(user))


def _production_url(day: date) -> str:
    """O Planejamento da Produção aberto em ``day`` (a data mora na URL do plano)."""
    from shopman.backstage.projections.hub import surface_link

    return surface_link("production", f"plan?date={day.isoformat()}")
