"""B.I. — perfis de consumo do balcão (docs/plans/BI-CONSUMPTION-PROFILES.md).

Quem são os clientes de balcão, em três perfis presumidos pela cesta:

- **A — só pra levar** (o modo ``takeaway``)
- **B — consumo local + pra levar** (``dine_in_takeaway``)
- **C — só consumo local** (``dine_in``)

Entrega (delivery/iFood) fica FORA da pergunta — é 100% "pra levar" por
definição — mas entra na conciliação: A + B + C + sem etiqueta + entrega tem
de somar o faturamento do período pela leitura atual do ``bi_sales``. Não
bateu = errado = não serve.

**O perfil é presumido, e a tela diz isso.** Cada SKU tem uma vocação
(consome aqui / leva / híbrido — catálogo editável no Admin) e o híbrido não
decide sozinho. Por isso o relatório entrega TRÊS leituras da mesma cesta —
piso (híbrido = leva), vigente (híbrido transparente, a regra do explorador) e
teto (híbrido = consome aqui) — e o % de pedidos que muda de perfil entre
piso e teto. O número honesto é a faixa.

Tudo aqui é derivado da coleta única de cestas (``services.consumption``):
nenhuma flag calculada em template, nenhuma segunda regra. Faixas de hora são
por ocasião (``services.hour_bands``); a hora é a do REGISTRO da venda.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from shopman.backstage.services import consumption as rule
from shopman.backstage.services.hour_bands import HOUR_BANDS, OUTSIDE, band_by_key, band_for

from .bi_production import _normalize_window, _previous_window
from .bi_sales import _local_datetime_window

# ── Perfis ───────────────────────────────────────────────────────────────────

PROFILE_A = "A"
PROFILE_B = "B"
PROFILE_C = "C"
PROFILE_UNCLASSIFIED = "unclassified"
PROFILES: tuple[str, ...] = (PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_UNCLASSIFIED)

PROFILE_LABELS: dict[str, str] = {
    PROFILE_A: "A · Só pra levar",
    PROFILE_B: "B · Consumo local + pra levar",
    PROFILE_C: "C · Só consumo local",
    PROFILE_UNCLASSIFIED: "Sem etiqueta",
}

# O modo que a regra devolve → o perfil da pergunta. Entrega não está aqui:
# não é perfil de balcão, é o balde que a conciliação exige.
MODE_TO_PROFILE: dict[str, str] = {
    rule.TAKEAWAY: PROFILE_A,
    rule.DINE_IN_TAKEAWAY: PROFILE_B,
    rule.DINE_IN: PROFILE_C,
    rule.UNCLASSIFIED: PROFILE_UNCLASSIFIED,
}

# Assentos para o RevPASH — informado pelo dono (18/08/2026: "24 assentos").
# ⚠️ Deliberadamente NÃO lê o cadastro do salão (`SeatingSpot`, capacidade
# oficial 22): aquele número foi calibrado para dizer "a casa bateu no teto"
# (o sofá que aperta não conta lá, de propósito). Aqui a pergunta é outra —
# quantos assentos há para render — e o dono respondeu 24. A tela mostra o
# denominador e a fonte.
REVPASH_SEATS = 24
REVPASH_SEATS_SOURCE = "informado pelo dono (18/08/2026)"


# ── Contrato ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BIProfileReading:
    key: str  # floor | current | ceiling
    label: str


@dataclass(frozen=True)
class BIProfileBand:
    key: str
    label: str
    title: str  # "Almoço · 11–14h"
    start: int
    end: int
    hours: int


@dataclass(frozen=True)
class BIProfileRow:
    reading: str
    profile: str
    label: str
    orders: int
    orders_share: float  # % dos pedidos de balcão do recorte
    revenue_q: int
    revenue_share: float  # % da receita de balcão do recorte
    average_ticket_q: int
    units_per_order: str  # unidades (soma de qty) por pedido
    distinct_per_order: str  # produtos distintos por pedido
    orders_by_band: tuple[int, ...]  # alinhado a `bands` (a última é "fora do expediente")
    revenue_by_band_q: tuple[int, ...]


@dataclass(frozen=True)
class BIProfileRange:
    profile: str
    label: str
    min_orders: int
    max_orders: int
    min_share: float
    max_share: float
    min_revenue_q: int
    max_revenue_q: int


@dataclass(frozen=True)
class BIProfileSensitivity:
    orders_changed: int  # pedidos que mudam de perfil entre piso e teto
    share_changed: float
    ranges: tuple[BIProfileRange, ...]


@dataclass(frozen=True)
class BIProfileCategoryRow:
    category: str
    revenue_q: int  # soma das linhas (balcão)
    share: float  # % da receita por linhas
    ready_beverage_q: int  # quanto disso é bebida pronta industrializada


@dataclass(frozen=True)
class BIStrikeCell:
    weekday: int  # 0 = segunda; -1 = todos
    band: str  # chave da faixa; "" = todas
    orders: int
    with_beverage: int
    rate: float  # % de pedidos com ≥1 bebida


@dataclass(frozen=True)
class BIProfileBeverage:
    orders_with_beverage: int
    strike_rate: float  # % pedidos de balcão com ≥1 bebida (preparada ou pronta)
    prepared_rate: float  # % com ≥1 bebida preparada (café/chá)
    ready_revenue_q: int  # receita de bebida pronta industrializada (linhas)
    ready_share: float  # % da receita de balcão
    local_orders: int  # pedidos com item de consumo local (âncora)
    per_local_order: str  # bebidas por pedido, nesses pedidos ("segunda rodada")
    # "Só veio tomar um café": cesta em que TODAS as linhas são bebida. Medido,
    # não estimado — é a única pergunta de consumo local que a cesta responde
    # sem proxy.
    beverage_only_orders: int
    beverage_only_share: float  # % dos pedidos de balcão do recorte
    beverage_only_ticket_q: int
    beverage_only_by_band: tuple[int, ...]  # alinhado a `bands`
    by_weekday_band: tuple[BIStrikeCell, ...]
    by_weekday: tuple[BIStrikeCell, ...]
    by_band: tuple[BIStrikeCell, ...]


@dataclass(frozen=True)
class BIRevpashRow:
    band: str
    title: str
    hours: int
    revenue_local_q: int  # receita dos pedidos com item local, na faixa
    days: int  # dias com venda no recorte
    seats: int
    revpash_q: int  # centavos por assento-hora


@dataclass(frozen=True)
class BIProfileEstimate:
    """A leitura em graus: P(alguém sentou) por cesta = maior peso da cesta.

    Esperança sob os pesos vigentes — não é medida. A faixa piso–teto continua
    ao lado como a honestidade de fundo; isto é onde o gestor acha que o
    número está, com os pesos que ele declarou (e que o passo 2 vai medir).
    """

    seated_orders: float  # Σ P(sentou) — "pedidos em que alguém comeu aqui"
    seated_share: float  # % dos pedidos de balcão COM peso
    seated_revenue_q: int  # Σ P(sentou) × total
    seated_revenue_share: float
    takeaway_orders: float  # Σ (1 − P) — "só vieram buscar"
    takeaway_share: float
    weighted_orders: int  # pedidos com ao menos uma linha com peso
    unweighted_orders: int  # pedidos sem peso nenhum — fora da conta, declarados
    seated_by_band: tuple[float, ...]  # alinhado a `bands`
    orders_by_band: tuple[int, ...]  # pedidos com peso por faixa (o denominador)


@dataclass(frozen=True)
class BIProfilesPrevious:
    date_from: str
    date_to: str
    counter_orders: int
    counter_revenue_q: int
    rows: tuple[BIProfileRow, ...]  # só a leitura vigente
    estimate: BIProfileEstimate


@dataclass(frozen=True)
class BIConsumptionProfilesReport:
    date_from: str
    date_to: str
    weekday: int | None  # filtro (0 = segunda); None = todos
    hour_band: str  # filtro (chave da faixa); "" = todas
    readings: tuple[BIProfileReading, ...]
    bands: tuple[BIProfileBand, ...]
    profiles: tuple[BIProfileRow, ...]  # 3 leituras × 4 perfis
    counter_orders: int
    counter_revenue_q: int
    delivery_orders: int
    delivery_revenue_q: int
    revenue_total_q: int  # balcão + entrega = faturamento do recorte (conciliação)
    coverage: float  # % de pedidos de balcão com ao menos uma linha etiquetada
    days_with_sales: int
    estimate: BIProfileEstimate
    sensitivity: BIProfileSensitivity
    categories: tuple[BIProfileCategoryRow, ...]
    category_lines_revenue_q: int  # soma das linhas de balcão
    category_header_gap_q: int  # faturamento de balcão − linhas (desconto/acréscimo de venda)
    beverage: BIProfileBeverage
    revpash: tuple[BIRevpashRow, ...]
    seats: int
    seats_source: str
    previous: BIProfilesPrevious


# ── Construção ───────────────────────────────────────────────────────────────


def build_bi_consumption_profiles(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    weekday: int | None = None,
    hour_band: str = "",
) -> BIConsumptionProfilesReport:
    date_from, date_to = _normalize_window(date_from, date_to)
    if weekday is not None and not 0 <= weekday <= 6:
        weekday = None
    if hour_band and band_by_key(hour_band) is None:
        hour_band = ""

    period = _fused(date_from, date_to)
    scope = _apply_filters(period, weekday, hour_band)
    counter = [b for b in scope if not b.is_delivery]
    delivery = [b for b in scope if b.is_delivery]

    bands = _bands()
    profile_rows = tuple(
        row
        for variant in rule.READING_VARIANTS
        for row in _profile_rows(counter, variant)
    )

    counter_revenue = sum(b.total_q for b in counter)
    delivery_revenue = sum(b.total_q for b in delivery)

    prev_from, prev_to = _previous_window(date_from, date_to)
    prev_counter = [
        b for b in _apply_filters(_fused(prev_from, prev_to), weekday, hour_band)
        if not b.is_delivery
    ]

    # RevPASH e a matriz de bebida usam o recorte de dia da semana, mas TODAS
    # as faixas: são eles o próprio recorte por faixa.
    by_weekday_only = [
        b for b in _apply_filters(period, weekday, "") if not b.is_delivery
    ]
    days_with_sales = len({b.local.date() for b in by_weekday_only})

    return BIConsumptionProfilesReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        weekday=weekday,
        hour_band=hour_band,
        readings=tuple(
            BIProfileReading(key=v, label=rule.READING_VARIANT_LABELS[v])
            for v in rule.READING_VARIANTS
        ),
        bands=bands,
        profiles=profile_rows,
        counter_orders=len(counter),
        counter_revenue_q=counter_revenue,
        delivery_orders=len(delivery),
        delivery_revenue_q=delivery_revenue,
        revenue_total_q=counter_revenue + delivery_revenue,
        coverage=_share(sum(1 for b in counter if any(line.reading for line in b.lines)), len(counter)),
        days_with_sales=days_with_sales,
        estimate=_estimate(counter),
        sensitivity=_sensitivity(counter, profile_rows),
        categories=_categories(counter),
        category_lines_revenue_q=sum(line.line_total_q for b in counter for line in b.lines),
        category_header_gap_q=counter_revenue - sum(line.line_total_q for b in counter for line in b.lines),
        beverage=_beverage(counter, [b for b in period if not b.is_delivery]),
        revpash=_revpash(by_weekday_only, days_with_sales),
        seats=REVPASH_SEATS,
        seats_source=REVPASH_SEATS_SOURCE,
        previous=BIProfilesPrevious(
            date_from=prev_from.isoformat(),
            date_to=prev_to.isoformat(),
            counter_orders=len(prev_counter),
            counter_revenue_q=sum(b.total_q for b in prev_counter),
            rows=tuple(_profile_rows(prev_counter, rule.READING_CURRENT)),
            estimate=_estimate(prev_counter),
        ),
    )


def _fused(date_from: date, date_to: date) -> list[rule.Basket]:
    native, historical = rule.collect_baskets(_local_datetime_window(date_from, date_to))
    return rule.fuse_baskets(native, historical)


def _apply_filters(baskets, weekday: int | None, hour_band: str) -> list[rule.Basket]:
    out = baskets
    if weekday is not None:
        out = [b for b in out if b.local.weekday() == weekday]
    if hour_band:
        out = [b for b in out if band_for(b.local.hour).key == hour_band]
    return list(out)


def _bands() -> tuple[BIProfileBand, ...]:
    return tuple(
        BIProfileBand(
            key=band.key, label=band.label, title=band.title,
            start=band.start, end=band.end, hours=band.hours,
        )
        for band in (*HOUR_BANDS, OUTSIDE)
    )


def _band_index(hour: int) -> int:
    band = band_for(hour)
    if band is OUTSIDE:
        return len(HOUR_BANDS)
    return HOUR_BANDS.index(band)


def _profile_rows(counter, variant: str) -> list[BIProfileRow]:
    slots = len(HOUR_BANDS) + 1
    orders: dict[str, int] = defaultdict(int)
    revenue: dict[str, int] = defaultdict(int)
    units: dict[str, Decimal] = defaultdict(Decimal)
    distinct: dict[str, int] = defaultdict(int)
    by_band: dict[str, list[int]] = defaultdict(lambda: [0] * slots)
    revenue_by_band: dict[str, list[int]] = defaultdict(lambda: [0] * slots)

    for basket in counter:
        profile = MODE_TO_PROFILE[basket.mode(variant)]
        orders[profile] += 1
        revenue[profile] += basket.total_q
        units[profile] += sum((line.qty for line in basket.lines), Decimal(0))
        distinct[profile] += len({line.key for line in basket.lines})
        index = _band_index(basket.local.hour)
        by_band[profile][index] += 1
        revenue_by_band[profile][index] += basket.total_q

    total_orders = len(counter)
    total_revenue = sum(revenue.values())
    rows = []
    for profile in PROFILES:
        n = orders[profile]
        rows.append(BIProfileRow(
            reading=variant,
            profile=profile,
            label=PROFILE_LABELS[profile],
            orders=n,
            orders_share=_share(n, total_orders),
            revenue_q=revenue[profile],
            revenue_share=_share(revenue[profile], total_revenue),
            average_ticket_q=revenue[profile] // n if n else 0,
            units_per_order=_ratio(units[profile], n),
            distinct_per_order=_ratio(distinct[profile], n),
            orders_by_band=tuple(by_band[profile]),
            revenue_by_band_q=tuple(revenue_by_band[profile]),
        ))
    return rows


def _estimate(counter) -> BIProfileEstimate:
    slots = len(HOUR_BANDS) + 1
    seated = 0.0
    seated_revenue = 0.0
    weighted = 0
    unweighted = 0
    revenue_weighted = 0
    seated_by_band = [0.0] * slots
    orders_by_band = [0] * slots
    for basket in counter:
        p = basket.eat_in_probability()
        if p is None:
            unweighted += 1
            continue
        weighted += 1
        revenue_weighted += basket.total_q
        seated += p
        seated_revenue += p * basket.total_q
        index = _band_index(basket.local.hour)
        seated_by_band[index] += p
        orders_by_band[index] += 1
    return BIProfileEstimate(
        seated_orders=round(seated, 1),
        seated_share=_share(seated, weighted),
        seated_revenue_q=int(round(seated_revenue)),
        seated_revenue_share=_share(seated_revenue, revenue_weighted),
        takeaway_orders=round(weighted - seated, 1),
        takeaway_share=_share(weighted - seated, weighted),
        weighted_orders=weighted,
        unweighted_orders=unweighted,
        seated_by_band=tuple(round(v, 2) for v in seated_by_band),
        orders_by_band=tuple(orders_by_band),
    )


def _sensitivity(counter, profile_rows) -> BIProfileSensitivity:
    changed = sum(
        1 for b in counter
        if b.mode(rule.READING_FLOOR) != b.mode(rule.READING_CEILING)
    )
    ranges = []
    for profile in PROFILES:
        rows = [r for r in profile_rows if r.profile == profile]
        ranges.append(BIProfileRange(
            profile=profile,
            label=PROFILE_LABELS[profile],
            min_orders=min(r.orders for r in rows),
            max_orders=max(r.orders for r in rows),
            min_share=min(r.orders_share for r in rows),
            max_share=max(r.orders_share for r in rows),
            min_revenue_q=min(r.revenue_q for r in rows),
            max_revenue_q=max(r.revenue_q for r in rows),
        ))
    return BIProfileSensitivity(
        orders_changed=changed,
        share_changed=_share(changed, len(counter)),
        ranges=tuple(ranges),
    )


UNCATEGORIZED = "(sem categoria)"


def _categories(counter) -> tuple[BIProfileCategoryRow, ...]:
    revenue: dict[str, int] = defaultdict(int)
    ready: dict[str, int] = defaultdict(int)
    for basket in counter:
        for line in basket.lines:
            category = line.category or UNCATEGORIZED
            revenue[category] += line.line_total_q
            if line.beverage == rule.BEVERAGE_READY:
                ready[category] += line.line_total_q
    total = sum(revenue.values())
    return tuple(
        BIProfileCategoryRow(
            category=category,
            revenue_q=revenue[category],
            share=_share(revenue[category], total),
            ready_beverage_q=ready[category],
        )
        for category in sorted(revenue, key=lambda c: -revenue[c])
    )


def _beverage(counter, period_counter) -> BIProfileBeverage:
    def has_beverage(basket) -> bool:
        return any(line.beverage for line in basket.lines)

    with_beverage = sum(1 for b in counter if has_beverage(b))
    with_prepared = sum(
        1 for b in counter if any(line.beverage == rule.BEVERAGE_PREPARED for line in b.lines)
    )
    ready_revenue = sum(
        line.line_total_q for b in counter for line in b.lines if line.beverage == rule.BEVERAGE_READY
    )
    counter_revenue = sum(b.total_q for b in counter)

    only = [b for b in counter if b.lines and all(line.beverage for line in b.lines)]
    only_by_band = [0] * (len(HOUR_BANDS) + 1)
    for basket in only:
        only_by_band[_band_index(basket.local.hour)] += 1

    # "Segunda rodada": entre quem consumiu algo aqui (tem âncora — e a âncora
    # é a mesma em todas as leituras), quantas bebidas por pedido.
    local = [b for b in counter if any(line.reading == rule.ANCHOR for line in b.lines)]
    beverages_in_local = sum(
        (line.qty for b in local for line in b.lines if line.beverage), Decimal(0)
    )

    # A matriz dia da semana × faixa sai do PERÍODO inteiro (é o próprio recorte).
    cells: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for basket in period_counter:
        key = (basket.local.weekday(), _band_index(basket.local.hour))
        cells[key][0] += 1
        if has_beverage(basket):
            cells[key][1] += 1

    def cell(weekday: int, band_index: int | None) -> BIStrikeCell:
        orders = 0
        hits = 0
        for (wd, bi), (n, h) in cells.items():
            if weekday != -1 and wd != weekday:
                continue
            if band_index is not None and bi != band_index:
                continue
            orders += n
            hits += h
        band_key = "" if band_index is None else (*HOUR_BANDS, OUTSIDE)[band_index].key
        return BIStrikeCell(
            weekday=weekday, band=band_key, orders=orders, with_beverage=hits,
            rate=_share(hits, orders),
        )

    band_indexes = range(len(HOUR_BANDS))  # a matriz omite "fora do expediente"
    return BIProfileBeverage(
        orders_with_beverage=with_beverage,
        strike_rate=_share(with_beverage, len(counter)),
        prepared_rate=_share(with_prepared, len(counter)),
        ready_revenue_q=ready_revenue,
        ready_share=_share(ready_revenue, counter_revenue),
        local_orders=len(local),
        per_local_order=_ratio(beverages_in_local, len(local)),
        beverage_only_orders=len(only),
        beverage_only_share=_share(len(only), len(counter)),
        beverage_only_ticket_q=sum(b.total_q for b in only) // len(only) if only else 0,
        beverage_only_by_band=tuple(only_by_band),
        by_weekday_band=tuple(cell(wd, bi) for wd in range(7) for bi in band_indexes),
        by_weekday=tuple(cell(wd, None) for wd in range(7)),
        by_band=tuple(cell(-1, bi) for bi in band_indexes),
    )


def _revpash(counter, days: int) -> tuple[BIRevpashRow, ...]:
    """Receita dos pedidos com item local ÷ (assentos × horas da faixa × dias).

    Só as faixas do expediente: fora dele não há assento-hora a render.
    """
    revenue_local = [0] * len(HOUR_BANDS)
    for basket in counter:
        if not any(line.reading == rule.ANCHOR for line in basket.lines):
            continue
        index = _band_index(basket.local.hour)
        if index < len(HOUR_BANDS):
            revenue_local[index] += basket.total_q
    rows = []
    for index, band in enumerate(HOUR_BANDS):
        seat_hours = REVPASH_SEATS * band.hours * days
        rows.append(BIRevpashRow(
            band=band.key,
            title=band.title,
            hours=band.hours,
            revenue_local_q=revenue_local[index],
            days=days,
            seats=REVPASH_SEATS,
            revpash_q=revenue_local[index] // seat_hours if seat_hours else 0,
        ))
    return tuple(rows)


def _share(part: int | float, whole: int | float) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def _ratio(total, count: int) -> str:
    if not count:
        return "0"
    value = Decimal(total) / Decimal(count)
    return str(value.quantize(Decimal("0.1")))
