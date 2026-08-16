"""O que esperar — projeção a partir dos dias parecidos.

Não há modelo aqui, e é de propósito. A resposta é aritmética sobre uma lista de
dias que o gestor pode conferir um a um: se ele discordar do número, vê de onde
ele veio e ganha a discussão. Um modelo seria mais preciso na média e
indefensável no dia em que errasse.

**O método, em uma frase:** a forma vem do histórico, o nível vem do presente.

Comparar com a quarta de agosto do ano passado supõe que a casa é a mesma — ela
não é: trocou de sistema, trocou o cardápio, e cresceu ou encolheu. Então o
passado não empresta o valor em reais; empresta a **proporção**. Cada dia
parecido é medido contra o movimento típico da época dele ("aquela quarta valeu
0,82 de um dia normal daquele mês"), e a mediana dessas proporções é aplicada ao
movimento típico de agora. A troca de sistema sai da conta sozinha, porque
numerador e denominador vêm sempre do mesmo tempo.

Três recusas explícitas, todas com teste:

- **Ausência não é zero.** Dia parecido sem venda registrada sai da amostra, e o
  número de descartados é declarado. Contá-lo como zero puxaria a projeção para
  baixo, e ninguém saberia por quê.
- **Amostra pequena não vira número pequeno.** Abaixo do mínimo, a resposta é
  "não sabemos", nunca um número frágil sem aviso.
- **Faixa, não ponto.** Um número só finge uma precisão que não existe. A
  resposta traz onde caiu metade dos dias parecidos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from shopman.backstage.services.day_similarity import (
    DEFAULT_WINDOW_DAYS,
    MINIMUM_SAMPLE,
    build_pool,
    similar_days,
)

from .sales_series import daily_sales

logger = logging.getLogger(__name__)

# Quantos dias formam o "movimento típico" de uma época. Quatro semanas cobrem
# o ciclo semanal inteiro sem diluir uma mudança recente de patamar.
LEVEL_WINDOW_DAYS = 28

# Abaixo disso o movimento típico é ruído, e dividir por ruído inventa proporção.
MIN_LEVEL_DAYS = 10

# Cada ramo de clima precisa se sustentar sozinho: um ramo com três dias não é
# uma resposta condicional, é uma coincidência com legenda.
MIN_BRANCH_SAMPLE = MINIMUM_SAMPLE

# Quão abaixo do ano o patamar recente pode estar antes de deixar de significar
# "a casa vendeu menos" e passar a significar "o sistema não tem as vendas".
#
# A régua é frouxa de propósito. Na Nelson, janeiro real fica em 31% da média do
# ano — queda sazonal verdadeira, que a projeção deve seguir. Já um sistema que
# registra 12% do movimento não está medindo uma queda: está medindo a si mesmo,
# durante uma migração. Multiplicar a forma do passado por esse patamar
# devolveria um número oito vezes menor, com toda a aparência de estar certo.
MIN_LEVEL_SHARE_OF_YEAR = 0.15

HORIZONS = ("day", "week", "month")

WEEKDAY_LABELS = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


class ForecastError(ValueError):
    """Pergunta fora do que a tela sabe responder."""


@dataclass(frozen=True)
class Expectation:
    """O provável, e a faixa onde caiu metade dos dias parecidos."""

    expected: float
    low: float
    high: float


@dataclass(frozen=True)
class ForecastBranch:
    """Um ramo condicional: 'se fizer calor', 'se chover'."""

    key: str
    label: str
    sample_size: int
    revenue_q: Expectation
    orders: Expectation


@dataclass(frozen=True)
class ForecastBasis:
    """A prestação de contas. Sem ela o número vira promessa."""

    sample_size: int
    applied: tuple[str, ...]
    relaxed: tuple[str, ...]
    unavailable: tuple[str, ...]
    window_from: str
    window_to: str
    excluded_closed: int
    excluded_disrupted: int
    without_sales: int
    without_level: int
    level_revenue_q: int
    level_days: int


@dataclass(frozen=True)
class OccasionYear:
    """Uma ocorrência passada da mesma data comercial."""

    date: str
    revenue_q: int
    ratio: float  # quantas vezes o movimento típico daquela época


@dataclass(frozen=True)
class ForecastOccasion:
    """O que ESTA data fez nos anos anteriores.

    Data comercial tem poucas ocorrências por construção: dois anos de histórico
    dão dois dias das mães. Projetar a partir de dois dias seria frágil, e a
    régua da amostra mínima corretamente se recusa a fazê-lo.

    Mas há uma resposta honesta disponível, e é outra pergunta: em vez de
    "quanto vai vender", **"o que este dia fez antes"** — cada ocorrência
    passada medida contra o movimento típico da época dela. Duas observações
    não sustentam uma previsão, mas sustentam um fato: "nas duas vezes
    anteriores, vendeu 1,8× e 2,1× um dia normal". O gestor tira a conclusão,
    com o número de ocorrências à vista.
    """

    name: str
    is_eve: bool  # a véspera é a mesma ocasião, vista do dia em que se vende
    years: tuple[OccasionYear, ...]
    expected_revenue_q: float  # mediana das razões × patamar de agora


@dataclass(frozen=True)
class DayForecast:
    date: str
    weekday: int
    weekday_label: str
    closed: bool
    closed_reason: str
    revenue_q: Expectation | None
    orders: Expectation | None
    branches: tuple[ForecastBranch, ...]
    occasion: ForecastOccasion | None
    basis: ForecastBasis | None
    missing_reason: str


@dataclass(frozen=True)
class BIForecastReport:
    horizon: str
    target: str
    date_from: str
    date_to: str
    days: tuple[DayForecast, ...]
    total_revenue_q: Expectation | None
    total_orders: Expectation | None
    total_missing_days: tuple[str, ...]


def build_bi_forecast(*, target: date, horizon: str = "day") -> BIForecastReport:
    """O que esperar de um dia, de uma semana ou de um mês.

    Semana e mês não são perguntas próprias: são a soma dos dias, cada um com a
    sua amostra. Uma semana que contém um feriado não é uma semana comum, e
    projetar "a semana" como bloco esconderia exatamente isso.
    """
    if horizon not in HORIZONS:
        raise ForecastError(
            f"Horizonte desconhecido: {horizon!r}. Existem: {', '.join(HORIZONS)}."
        )

    days = _horizon_days(target, horizon)
    today = timezone.localdate()
    until = today - timedelta(days=1)
    since = until - timedelta(days=DEFAULT_WINDOW_DAYS)

    # Uma leitura só para todo o relatório: a série precisa recuar mais que a
    # janela de semelhança, porque o dia parecido mais antigo também tem de ter
    # um "movimento típico" atrás dele.
    series = daily_sales(since - timedelta(days=LEVEL_WINDOW_DAYS), until)

    # A janela encolhe até onde a casa tem dado. Sem isto, a prestação de contas
    # anunciaria "90 quartas sem venda registrada" num sistema que existe há
    # quatro meses — número verdadeiro e sem significado nenhum, que faria a
    # amostra parecer cheia de buracos quando ela só é jovem.
    if series:
        since = max(since, min(series) + timedelta(days=LEVEL_WINDOW_DAYS))
    pool = build_pool(since, until)
    current = _level(today, series)
    # Duas ausências diferentes de patamar, e a tela precisa dizer qual é: não
    # há movimento recente nenhum, ou há movimento que não representa a casa.
    reason = "sem_movimento_recente"
    if current[0] is not None and not _level_is_representative(current[0], today, series):
        current, reason = (None, None, 0), "patamar_nao_representativo"

    forecasts = tuple(_forecast_day(day, series, pool, current, reason) for day in days)
    total_revenue, total_orders, missing = _totals(forecasts)

    return BIForecastReport(
        horizon=horizon,
        target=target.isoformat(),
        date_from=days[0].isoformat(),
        date_to=days[-1].isoformat(),
        days=forecasts,
        total_revenue_q=total_revenue,
        total_orders=total_orders,
        total_missing_days=missing,
    )


# ── Um dia ────────────────────────────────────────────────────────────────────


def _forecast_day(day: date, series: dict, pool, current, no_level_reason: str) -> DayForecast:
    base = {
        "date": day.isoformat(),
        "weekday": day.weekday(),
        "weekday_label": WEEKDAY_LABELS[day.weekday()],
    }

    closed, reason = _will_be_closed(day)
    if closed:
        # Não é ausência: sabemos que a casa não abre. Zero declarado.
        return DayForecast(
            **base, closed=True, closed_reason=reason,
            revenue_q=Expectation(0.0, 0.0, 0.0), orders=Expectation(0.0, 0.0, 0.0),
            branches=(), occasion=None, basis=None, missing_reason="",
        )

    similar = similar_days(day, pool=pool)
    revenue_level, orders_level, level_days = current
    shapes = _shapes(similar.days, series)
    # A data comercial responde mesmo quando a amostra comum não responde: ela
    # tem pergunta própria, e a resposta é observação, não projeção.
    occasion = _occasion(day, series, pool, revenue_level)

    # Duas ausências de naturezas diferentes, contadas em separado: o dia sem
    # venda registrada (não sabemos o que aconteceu) e o dia com venda mas sem
    # movimento típico atrás dele (sabemos o que vendeu, não contra o quê
    # comparar). Somá-las esconderia qual das duas está limitando a amostra.
    with_sales = sum(1 for d in similar.days if d in series)
    basis = ForecastBasis(
        sample_size=len(shapes),
        applied=similar.applied,
        relaxed=similar.relaxed,
        unavailable=similar.unavailable,
        window_from=similar.window_from.isoformat(),
        window_to=similar.window_to.isoformat(),
        excluded_closed=similar.excluded_closed,
        excluded_disrupted=similar.excluded_disrupted,
        without_sales=len(similar.days) - with_sales,
        without_level=with_sales - len(shapes),
        level_revenue_q=int(revenue_level or 0),
        level_days=level_days,
    )

    if revenue_level is None:
        return DayForecast(
            **base, closed=False, closed_reason="",
            revenue_q=None, orders=None, branches=(), occasion=occasion, basis=basis,
            missing_reason=no_level_reason,
        )
    if len(shapes) < MINIMUM_SAMPLE:
        return DayForecast(
            **base, closed=False, closed_reason="",
            revenue_q=None, orders=None, branches=(), occasion=occasion, basis=basis,
            missing_reason="amostra_insuficiente",
        )

    return DayForecast(
        **base, closed=False, closed_reason="",
        revenue_q=_expectation([s[1] for s in shapes], revenue_level),
        orders=_expectation([s[2] for s in shapes], orders_level),
        branches=_branches(shapes, revenue_level, orders_level),
        occasion=occasion,
        basis=basis,
        missing_reason="",
    )


def _occasion(day: date, series: dict, pool, revenue_level) -> ForecastOccasion | None:
    """O que esta ocasião fez nos anos anteriores.

    **A véspera conta como a mesma ocasião**, e é a que mais importa: numa casa
    fechada no domingo, o dia das mães acontece no sábado. Comparar essa véspera
    com "vésperas de data especial" em geral misturaria o sábado do dia das mães
    com o de um feriado qualquer, que é justamente o que se quer separar.

    Só existe quando há pelo menos uma ocorrência passada com venda. Nada de
    "nenhuma ocorrência anterior" como bloco vazio: sem fato, sem bloco.
    """
    from shopman.backstage.models import DayContext

    context = pool.contexts.get(day) or DayContext.objects.filter(date=day).first()
    name = (context.occasion_name if context else "").strip()
    is_eve = bool(context and context.occasion_is_eve)
    if not name or not revenue_level:
        return None

    years = []
    for past, past_context in sorted(pool.contexts.items()):
        # Véspera compara com véspera, e o dia com o dia: os dois medem a mesma
        # data, mas em posições que vendem de formas diferentes.
        if past_context.occasion_is_eve != is_eve:
            continue
        if past_context.occasion_name.strip().lower() != name.lower():
            continue
        observed = series.get(past)
        if observed is None:
            continue
        past_level, _, _ = _level(past, series)
        if not past_level:
            continue
        years.append(
            OccasionYear(
                date=past.isoformat(),
                revenue_q=observed.revenue_q,
                ratio=observed.revenue_q / past_level,
            )
        )
    if not years:
        return None
    return ForecastOccasion(
        name=name,
        is_eve=is_eve,
        years=tuple(years),
        expected_revenue_q=_median([y.ratio for y in years]) * revenue_level,
    )


def _shapes(days: tuple[date, ...], series: dict) -> list[tuple[date, float, float]]:
    """(dia, proporção de faturamento, proporção de pedidos) por dia parecido.

    Dia sem venda registrada e dia sem movimento típico atrás dele saem daqui —
    e a diferença entre "não vendeu" e "não dá para normalizar" é contada
    separadamente no ``basis``, porque são ausências de naturezas diferentes.
    """
    shapes = []
    for day in days:
        observed = series.get(day)
        if observed is None:
            continue
        revenue_level, orders_level, _ = _level(day, series)
        if not revenue_level or not orders_level:
            continue
        shapes.append(
            (day, observed.revenue_q / revenue_level, observed.orders / orders_level)
        )
    return shapes


def _level(day: date, series: dict) -> tuple[float | None, float | None, int]:
    """O movimento típico da época de ``day``: a mediana das 4 semanas anteriores.

    Exclui o próprio dia — normalizar um dia por uma média que o contém
    aproximaria toda proporção de 1 e apagaria justamente o que se quer medir.
    """
    observed = [
        series[d]
        for d in (day - timedelta(days=k) for k in range(1, LEVEL_WINDOW_DAYS + 1))
        if d in series
    ]
    if len(observed) < MIN_LEVEL_DAYS:
        return None, None, len(observed)
    return (
        _median([o.revenue_q for o in observed]),
        _median([o.orders for o in observed]),
        len(observed),
    )


def _level_is_representative(recent: float, today: date, series: dict) -> bool:
    """O patamar recente mede a casa, ou mede o sistema?

    Durante uma migração as duas fontes descrevem o mesmo negócio, mas a nova
    ainda carrega uma fração das vendas. A regra "dia nativo vence" — certa,
    porque evita contar a mesma venda duas vezes — faz um dia com quatro pedidos
    de teste apagar o mesmo dia com cento e trinta vendas registradas. O patamar
    desaba, e toda projeção sai proporcionalmente baixa **parecendo correta**.

    Aqui isso vira ausência declarada, como manda a régua da amostra: número
    frágil sem aviso é pior que ausência com motivo.
    """
    year = [
        row.revenue_q
        for day, row in series.items()
        if today - timedelta(days=365) <= day < today
    ]
    if len(year) < LEVEL_WINDOW_DAYS:
        return True  # base curta demais para julgar; não inventa suspeita
    return recent >= _median(year) * MIN_LEVEL_SHARE_OF_YEAR


def _expectation(shapes: list[float], level: float) -> Expectation:
    return Expectation(
        expected=_median(shapes) * level,
        low=_percentile(shapes, 25) * level,
        high=_percentile(shapes, 75) * level,
    )


# ── Ramos condicionais de clima (a fundação; previsão só destaca um deles) ─────


def _branches(shapes, revenue_level, orders_level) -> tuple[ForecastBranch, ...]:
    """Como o dia se comporta no frio e no calor, com e sem chuva.

    O corte de temperatura é a mediana dos próprios dias parecidos, não um
    número fixo: "frio" em Londrina não é "frio" em outro lugar, e o corte
    relativo se explica sozinho na tela.
    """
    from shopman.backstage.models import DayContext

    contexts = {
        row.date: row
        for row in DayContext.objects.filter(date__in=[s[0] for s in shapes])
    }
    branches: list[ForecastBranch] = []

    measured = [s for s in shapes if _has_temp(contexts.get(s[0]))]
    cut = _split_point([float(contexts[s[0]].temp_max_c) for s in measured])
    if cut is not None:
        branches.extend(
            _pair(
                ("cold", f"Se fizer menos de {cut:.0f} °C",
                 [s for s in measured if float(contexts[s[0]].temp_max_c) < cut]),
                ("warm", f"Se fizer {cut:.0f} °C ou mais",
                 [s for s in measured if float(contexts[s[0]].temp_max_c) >= cut]),
                revenue_level, orders_level,
            )
        )

    rained = [s for s in shapes if _has_rain(contexts.get(s[0]))]
    if rained:
        branches.extend(
            _pair(
                ("rain", "Se chover", [s for s in rained if contexts[s[0]].rain_mm > 0]),
                ("dry", "Se não chover", [s for s in rained if contexts[s[0]].rain_mm == 0]),
                revenue_level, orders_level,
            )
        )

    return tuple(branches)


def _split_point(values: list[float]) -> float | None:
    """O corte que divide a amostra em dois lados de verdade.

    A mediana pura não serve: num clima que alterna entre 15 °C e 31 °C, ela cai
    **sobre** um dos dois valores, o lado de baixo fica vazio e o de cima vira a
    amostra inteira com o rótulo "se fizer calor". O corte tem de ser um dos
    limites entre valores distintos, escolhido pelo que melhor equilibra os
    lados — e não existe corte quando todos os dias tiveram a mesma
    temperatura, que é o caso em que "e se?" não é pergunta.
    """
    distinct = sorted(set(values))
    if len(distinct) < 2:
        return None
    half = len(values) / 2
    return min(
        distinct[1:], key=lambda v: abs(sum(1 for x in values if x < v) - half)
    )


def _pair(left, right, revenue_level, orders_level) -> list[ForecastBranch]:
    """Ramo condicional só existe aos pares.

    Um lado sozinho não é resposta condicional: se todos os dias parecidos
    caíram no "se fizer calor", esse ramo é a projeção inteira com um rótulo
    enganoso pendurado. Ou os dois lados se sustentam, ou a pergunta "e se?" não
    tem resposta e a tela não a faz.
    """
    if any(len(side) < MIN_BRANCH_SAMPLE for _, _, side in (left, right)):
        return []
    return [
        _branch(key, label, side, revenue_level, orders_level)
        for key, label, side in (left, right)
    ]


def _branch(key, label, side, revenue_level, orders_level) -> ForecastBranch:
    return ForecastBranch(
        key=key,
        label=label,
        sample_size=len(side),
        revenue_q=_expectation([s[1] for s in side], revenue_level),
        orders=_expectation([s[2] for s in side], orders_level),
    )


def _has_temp(context) -> bool:
    return context is not None and context.temp_max_c is not None


def _has_rain(context) -> bool:
    return context is not None and context.rain_mm is not None


# ── Período: soma dos dias, e só quando todos respondem ───────────────────────


def _totals(forecasts: tuple[DayForecast, ...]):
    """Total do período, ou nada.

    Somar só os dias que responderam daria um total plausível e errado: uma
    semana sem o sábado é um número que ninguém deveria usar para planejar. Ou
    todos os dias abertos têm base, ou o total não sai — e os que faltaram são
    nomeados.
    """
    missing = tuple(f.date for f in forecasts if not f.closed and f.revenue_q is None)
    if missing or len(forecasts) == 1:
        return None, None, missing

    answered = [f for f in forecasts if f.revenue_q is not None]
    # Somar os quartis dos dias dá uma faixa mais larga que o quartil da soma —
    # os dias não erram todos para o mesmo lado no mesmo dia. É conservador de
    # propósito: para planejar, faixa larga demais custa menos que faixa estreita
    # demais, e a tela diz que é a soma dos extremos.
    return (
        Expectation(
            expected=sum(f.revenue_q.expected for f in answered),
            low=sum(f.revenue_q.low for f in answered),
            high=sum(f.revenue_q.high for f in answered),
        ),
        Expectation(
            expected=sum(f.orders.expected for f in answered),
            low=sum(f.orders.low for f in answered),
            high=sum(f.orders.high for f in answered),
        ),
        (),
    )


def _horizon_days(target: date, horizon: str) -> list[date]:
    if horizon == "day":
        return [target]
    if horizon == "week":
        start = target - timedelta(days=target.weekday())
        return [start + timedelta(days=offset) for offset in range(7)]
    start = target.replace(day=1)
    days = []
    day = start
    while day.month == start.month:
        days.append(day)
        day += timedelta(days=1)
    return days


def _will_be_closed(day: date) -> tuple[bool, str]:
    """A casa abre neste dia? Para o futuro, quem sabe é o calendário."""
    from shopman.shop.services.business_calendar import (
        _closed_dates,
        _load_shop,
        closed_date_for,
        is_open_on,
    )

    try:
        shop = _load_shop(None)
        if shop:
            closed, label, _ = closed_date_for(day, _closed_dates(shop))
            if closed:
                return True, label or "sem expediente"
        return (False, "") if is_open_on(day) else (True, "sem expediente regular")
    except Exception:
        # Calendário ilegível não vira "fechado": afirmar que a casa não abre
        # zeraria a projeção do dia com uma certeza que não temos.
        logger.debug("calendário indisponível para %s", day, exc_info=True)
        return False, ""


# ── Estatística mínima, sem dependência nova ──────────────────────────────────


def _median(values) -> float:
    return _percentile(values, 50)


def _percentile(values, pct: int) -> float:
    """Percentil por interpolação linear. Lista vazia é erro de quem chamou."""
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
