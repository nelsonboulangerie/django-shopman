"""Quanto de troco a casa vai precisar — para abastecer antes, e não na fila.

Faltar troco no meio do movimento é um problema que só aparece na pior hora
possível, e resolver na hora é justamente o momento de risco. Se o gestor souber
na véspera que o sábado pede uns R$ 180 em troco, ele abastece no tempo dele e a
falta simplesmente não acontece.

**A decomposição, em uma linha:**

    troco do dia = (vendas em dinheiro previstas) × (troco médio por venda em dinheiro)

Os dois fatores têm confiança MUITO diferente, e a tela é obrigada a dizer isso:

- **Quantas vendas em dinheiro** vem do mesmo método de "o que esperar": os
  pedidos prováveis do dia, multiplicados pela fatia que costuma pagar em
  espécie nos dias parecidos. Essa fatia é uma proporção, então ela atravessa a
  troca de sistema sem se contaminar e pode usar os dois anos de histórico.
- **Quanto de troco sai por venda** só existe desde que o Shopman entrou. O
  histórico externo tem o total e a forma de pagamento, nunca o troco. São
  semanas de base, não anos — e por isso a faixa é larga, e diz por quê.

Três recusas, herdadas de "o que esperar" e cobradas por teste:

- **Base rasa não vira número.** Abaixo do mínimo de dias medidos, a resposta é
  "ainda não sabemos", nunca uma média frágil sem aviso.
- **Ausência de medição não é troco zero.** Venda em dinheiro em que ninguém
  registrou o valor recebido sai da conta em vez de entrar como zero. Contá-la
  como zero puxaria a média para baixo e faria a casa abastecer MENOS troco do
  que precisa, que é o erro caro.
- **Nenhum dia do histórico externo entra na razão troco/venda.** Ele não tem
  troco; usá-lo seria inventar medição.

⚠️ **A fronteira da denominação, escrita aqui para não ser "melhorada" depois.**
O sistema sabe que saíram R$ 3,50 de troco. Ele **não sabe quais moedas** —
ninguém registra peça a peça num balcão, e nenhum dado deste projeto permite
inferir isso. O que a distribuição dos valores permite dizer é *tendência*
("a maior parte sai em dinheiro miúdo") e um *piso de moeda por valor* (os
centavos de cada troco não fecham em nota). Contagem de peças — "40 moedas de
R$ 1" — é precisão que o dado não tem: não a produza aqui nem na superfície.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from shopman.backstage.services.day_similarity import (
    DEFAULT_WINDOW_DAYS,
    MINIMUM_SAMPLE,
    build_pool,
    similar_days,
)

# Duas reutilizações deliberadas, e não conveniência de import:
#
# - o quartil tem de querer dizer a mesma coisa nas duas telas, que aparecem
#   lado a lado; duas definições de faixa divergindo por arredondamento fariam o
#   gestor desconfiar das duas;
# - a definição de "venda em dinheiro" vem de quem é dono da série. Se ela
#   divergisse aqui, o numerador (troco medido) e o denominador (vendas em
#   dinheiro previstas) da razão estariam falando de conjuntos diferentes.
from .bi_forecast import (
    Expectation,
    _median,
    _percentile,
    build_bi_forecast,
)
from .bi_forecast import ForecastError as ForecastError  # horizonte inválido é a mesma borda
from .sales_series import daily_sales

# Até onde recuar atrás da medição de troco. Meio ano é folga generosa sobre as
# semanas que a casa tem; a régua que manda é o mínimo de dias medidos, não esta.
HABIT_WINDOW_DAYS = 180

# Um dia com três vendas em dinheiro não é uma observação do hábito do bairro, é
# ruído com data. A média do dia só conta com movimento de dinheiro de verdade.
MIN_CASH_ORDERS_PER_DAY = 5

# Abaixo disso não há hábito medido, e a resposta é "ainda não sabemos".
MIN_MEASURED_DAYS = MINIMUM_SAMPLE

# A partir daqui a base já sustenta a faixa interquartil (o miolo). Antes disso a
# faixa mostra os EXTREMOS medidos: com poucos dias, o miolo de uma amostra curta
# finge uma precisão que ela não tem, e para abastecer troco a faixa larga custa
# menos que a faixa estreita demais.
COMFORTABLE_DAYS = 28

# Quantas vendas de forma de pagamento conhecida um dia parecido precisa ter para
# emprestar a sua fatia de dinheiro. Dia com duas vendas conhecidas devolveria
# 0% ou 50% por acidente de arredondamento.
MIN_KNOWN_PAYMENTS_PER_DAY = 5

# Fronteira de "dinheiro miúdo": abaixo disso o troco sai de moeda e das notas
# menores. É um recorte de leitura, não uma afirmação sobre quais peças saíram.
SMALL_CHANGE_Q = 500


@dataclass(frozen=True)
class ChangeHabit:
    """Quanto de troco sai por venda em dinheiro — o hábito do bairro.

    ``band`` diz o que a faixa está mostrando, porque as duas leituras são
    honestas por motivos diferentes: ``interquartile`` é o miolo dos dias
    medidos; ``full_range`` é o menor e o maior dia, que é o que sobra quando a
    base ainda é de poucas semanas.
    """

    per_cash_order_q: Expectation
    band: str  # "interquartile" | "full_range"
    measured_days: int
    measured_orders: int
    unmeasured_orders: int
    window_from: str
    window_to: str


@dataclass(frozen=True)
class ChangeMix:
    """A tendência da denominação. Nunca uma contagem de peças.

    ``coin_value_percent`` é o único piso que o dado sustenta sozinho: os
    centavos de um troco não fecham em nota nenhuma, então essa parcela do valor
    sai obrigatoriamente em moeda. ``small_change_percent`` é a fatia das
    ocorrências de troco abaixo de R$ 5,00 — o que separa "preciso de miudeza"
    de "preciso de notas".
    """

    tendency: str  # "mostly_coins" | "mixed" | "mostly_notes"
    coin_value_percent: int
    small_change_percent: int
    sample_size: int


@dataclass(frozen=True)
class DayChangeForecast:
    date: str
    weekday: int
    weekday_label: str
    closed: bool
    closed_reason: str
    change_q: Expectation | None
    coin_floor_q: float | None
    cash_orders: Expectation | None
    cash_share_percent: int
    cash_share_days: int
    missing_reason: str


@dataclass(frozen=True)
class BIChangeReport:
    horizon: str
    target: str
    date_from: str
    date_to: str
    days: tuple[DayChangeForecast, ...]
    total_change_q: Expectation | None
    total_missing_days: tuple[str, ...]
    habit: ChangeHabit | None
    mix: ChangeMix | None
    missing_reason: str


def build_bi_change(*, target: date, horizon: str = "day") -> BIChangeReport:
    """Quanto de troco separar para um dia, uma semana ou um mês.

    Levanta ``ForecastError`` para horizonte desconhecido — é a mesma pergunta de
    "o que esperar", e a borda que valida é a mesma.
    """
    forecast = build_bi_forecast(target=target, horizon=horizon)
    habit, mix, habit_missing = _habit()

    today = timezone.localdate()
    until = today - timedelta(days=1)
    since = until - timedelta(days=DEFAULT_WINDOW_DAYS)
    series = daily_sales(since, until)
    # A janela encolhe até onde a casa tem dado, pelo mesmo motivo da projeção:
    # anunciar "noventa sábados sem venda" num sistema de quatro meses é verdade
    # sem significado.
    if series:
        since = max(since, min(series))
    pool = build_pool(since, until)

    days = tuple(_day(day, series, pool, habit, mix, habit_missing) for day in forecast.days)
    total, missing = _totals(days)

    return BIChangeReport(
        horizon=forecast.horizon,
        target=forecast.target,
        date_from=forecast.date_from,
        date_to=forecast.date_to,
        days=days,
        total_change_q=total,
        total_missing_days=missing,
        habit=habit,
        mix=mix,
        missing_reason=habit_missing,
    )


# ── Um dia ────────────────────────────────────────────────────────────────────


def _day(forecast, series, pool, habit, mix, habit_missing: str) -> DayChangeForecast:
    base = {
        "date": forecast.date,
        "weekday": forecast.weekday,
        "weekday_label": forecast.weekday_label,
    }

    if forecast.closed:
        # Casa fechada não é lacuna: é zero sabido, e zero de troco também.
        return DayChangeForecast(
            **base, closed=True, closed_reason=forecast.closed_reason,
            change_q=Expectation(0.0, 0.0, 0.0), coin_floor_q=0.0,
            cash_orders=Expectation(0.0, 0.0, 0.0),
            cash_share_percent=0, cash_share_days=0, missing_reason="",
        )

    day = date.fromisoformat(forecast.date)
    shares = _cash_shares(similar_days(day, pool=pool).days, series)
    share = _median(shares) if len(shares) >= MINIMUM_SAMPLE else None

    def absent(reason: str) -> DayChangeForecast:
        return DayChangeForecast(
            **base, closed=False, closed_reason="",
            change_q=None, coin_floor_q=None, cash_orders=None,
            cash_share_percent=round((share or 0) * 100), cash_share_days=len(shares),
            missing_reason=reason,
        )

    if forecast.orders is None:
        # A previsão de troco não tem resposta própria quando o número de pedidos
        # não existe: repetir o motivo da projeção mantém a mesma explicação nas
        # duas telas, em vez de inventar uma segunda versão da mesma ausência.
        return absent(forecast.missing_reason)
    if share is None:
        return absent("sem_mix_de_pagamento")
    if habit is None:
        return absent(habit_missing)

    cash_orders = _scaled(forecast.orders, share)
    change = Expectation(
        expected=cash_orders.expected * habit.per_cash_order_q.expected,
        low=cash_orders.low * habit.per_cash_order_q.low,
        high=cash_orders.high * habit.per_cash_order_q.high,
    )
    return DayChangeForecast(
        **base, closed=False, closed_reason="",
        change_q=change,
        coin_floor_q=change.expected * (mix.coin_value_percent / 100) if mix else None,
        cash_orders=cash_orders,
        cash_share_percent=round(share * 100),
        cash_share_days=len(shares),
        missing_reason="",
    )


def _cash_shares(days: tuple[date, ...], series: dict) -> list[float]:
    """Que fatia das vendas foi em dinheiro, em cada dia parecido.

    A fatia é medida sobre as vendas de forma de pagamento CONHECIDA, não sobre
    o total do dia. Um export que veio sem a coluna de pagamento não é um dia sem
    dinheiro: é um dia sem resposta, e ele apenas não vota.
    """
    shares = []
    for day in days:
        row = series.get(day)
        if row is None or row.payments_known < MIN_KNOWN_PAYMENTS_PER_DAY:
            continue
        shares.append(row.cash_orders / row.payments_known)
    return shares


def _scaled(expectation: Expectation, factor: float) -> Expectation:
    return Expectation(
        expected=expectation.expected * factor,
        low=expectation.low * factor,
        high=expectation.high * factor,
    )


# ── O hábito: medido, e só a partir de pedido nativo ──────────────────────────


def _habit() -> tuple[ChangeHabit | None, ChangeMix | None, str]:
    """Quanto de troco sai por venda em dinheiro, e como ele se distribui.

    Lê ``Order`` direto e nunca o histórico externo, porque só o pedido nativo
    carrega ``payment.change_q``. Não é uma preferência de fonte: o export não
    tem o dado, e completá-lo por estimativa transformaria uma ausência
    declarada num número inventado.
    """
    from shopman.backstage.bi.canonical import local_window
    from shopman.backstage.bi.sources import orderman

    until = timezone.localdate() - timedelta(days=1)
    since = until - timedelta(days=HABIT_WINDOW_DAYS)

    measured: dict[date, list[int]] = {}
    unmeasured = 0
    # O adaptador nativo direto, não a composição: aqui a escolha de fonte é a
    # pergunta, e passar pela conciliação só traria histórico para descartar.
    native, _cancelled = orderman.read_sales(local_window(since, until))
    for sale in native:
        if not sale.is_cash:
            continue
        if sale.change_q is None:
            # Venda em dinheiro sem o valor recebido registrado não é venda sem
            # troco: é venda sem medição. Entrasse como zero, a média cairia e a
            # casa abasteceria menos troco do que precisa — o erro que custa.
            unmeasured += 1
            continue
        measured.setdefault(sale.day, []).append(sale.change_q)

    per_day = [
        sum(changes) / len(changes)
        for changes in measured.values()
        if len(changes) >= MIN_CASH_ORDERS_PER_DAY
    ]
    orders_counted = sum(
        len(changes) for changes in measured.values() if len(changes) >= MIN_CASH_ORDERS_PER_DAY
    )
    if len(per_day) < MIN_MEASURED_DAYS:
        return None, None, "troco_sem_base"

    shallow = len(per_day) < COMFORTABLE_DAYS
    habit = ChangeHabit(
        per_cash_order_q=Expectation(
            expected=_median(per_day),
            low=min(per_day) if shallow else _percentile(per_day, 25),
            high=max(per_day) if shallow else _percentile(per_day, 75),
        ),
        band="full_range" if shallow else "interquartile",
        measured_days=len(per_day),
        measured_orders=orders_counted,
        unmeasured_orders=unmeasured,
        window_from=since.isoformat(),
        window_to=until.isoformat(),
    )
    return habit, _mix(measured), ""


def _mix(measured: dict[date, list[int]]) -> ChangeMix | None:
    """A tendência da denominação, a partir da distribuição dos VALORES.

    ⚠️ Nada aqui devolve peças. ``coin_value_percent`` é o resto em centavos, que
    é o único pedaço do troco que comprovadamente não fecha em nota;
    ``small_change_percent`` conta ocorrências abaixo de R$ 5,00. Quem quiser
    "quantas moedas de R$ 1" está pedindo um dado que o balcão nunca registrou.
    """
    changes = [value for day in measured.values() for value in day if value > 0]
    if not changes:
        return None

    total = sum(changes)
    coin_percent = round(100 * sum(value % 100 for value in changes) / total)
    small_percent = round(100 * sum(1 for value in changes if value < SMALL_CHANGE_Q) / len(changes))
    if small_percent >= 70:
        tendency = "mostly_coins"
    elif small_percent <= 30:
        tendency = "mostly_notes"
    else:
        tendency = "mixed"
    return ChangeMix(
        tendency=tendency,
        coin_value_percent=coin_percent,
        small_change_percent=small_percent,
        sample_size=len(changes),
    )


# ── Período: soma dos dias, e só quando todos respondem ───────────────────────


def _totals(days: tuple[DayChangeForecast, ...]):
    """Total do período, ou nada — a mesma regra da projeção.

    Um total de semana sem o sábado é o número mais perigoso da tela: parece
    completo e manda abastecer menos do que o dia que mais precisa.
    """
    missing = tuple(d.date for d in days if not d.closed and d.change_q is None)
    if missing or len(days) == 1:
        return None, missing

    answered = [d for d in days if d.change_q is not None]
    return (
        Expectation(
            expected=sum(d.change_q.expected for d in answered),
            low=sum(d.change_q.low for d in answered),
            high=sum(d.change_q.high for d in answered),
        ),
        (),
    )
