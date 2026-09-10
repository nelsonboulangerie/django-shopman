"""B.I. de caixa — leitura analítica (ADR-021, BI-PLAN §5/F4), sobre o livro.

Lê o livro do ``cashman`` pela camada canônica (``bi/sources/cashman.py``):
a quebra de cada turno fechado (``count`` + correções), sangrias e suprimentos
(``cash_out``/``cash_in``), e o comportamento de gaveta que motivou o log de
eventos — aberturas sem venda, destraves por gerente e pedidos de troco, por
operador e por hora do dia (WP-8 do CASHMAN-PLAN). O mix de meios vem do
fechamento do dia (``DayClosing.data.cash_shift_summary.payment_method_totals``,
consumo registrado em docs/reference/data-schemas.md). Dias da janela sem
fechamento entram em ``closings_missing``: o buraco é declarado, nunca
silenciado.

⚠️ Isto é APURAÇÃO, não faturamento: quebra por operador é o que o fechamento
cego existe para produzir. O endpoint exige ``cashman.audit_shift`` além de
``backstage.view_bi`` (decisão do dono, 19/08/2026) — quem opera não vê.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BICashDay:
    date: str
    shifts: int
    difference_q: int
    sangria_q: int
    suprimento_q: int


@dataclass(frozen=True)
class BICashOperatorRow:
    """O que cada pessoa fez, lido do LIVRO — onde cada linha tem dono.

    ``difference_q`` só é preenchido nos turnos em que essa pessoa lançou
    SOZINHA: a quebra nasce da contagem, é um número por turno, e com várias
    mãos na mesma gaveta não há conta que a divida. ``shifts`` conta esses
    turnos de dono provado, não todos em que a pessoa passou — por isso as
    duas colunas são coerentes entre si, e por isso zero em ``shifts`` com
    aberturas de gaveta acima de zero é leitura normal, não defeito.
    """

    operator: str
    shifts: int
    difference_q: int
    # Do livro: contagens no período. Zero é zero, não "não sei".
    drawer_openings: int
    drawer_unlocks: int
    change_requests: int
    # Acertos de conta recebidos em dinheiro por este operador (``account_settled``).
    account_settled_q: int = 0


@dataclass(frozen=True)
class BICashAccountRow:
    customer_name: str
    balance_q: int


@dataclass(frozen=True)
class BICashAccounts:
    """Conta do cliente na janela: o que virou dívida, o que foi acertado, o que está em aberto hoje.

    ``sales_q`` e ``settled_q`` vêm do Payman (intents ``account`` autorizados /
    capturados na janela, qualquer método de acerto); ``settled_cash_q`` é a parte
    que entrou na gaveta (``account_settled`` no livro). ``open_q`` é o saldo
    devedor total HOJE (derivado, não da janela), com os maiores devedores.
    """

    sales_q: int = 0
    settled_q: int = 0
    settled_cash_q: int = 0
    open_q: int = 0
    open_customers: int = 0
    top_open: tuple[BICashAccountRow, ...] = ()  # maiores saldos em aberto hoje


@dataclass(frozen=True)
class BICashDrawerRow:
    """O comportamento de gaveta de UMA pessoa — para reconhecer padrão, não só contar.

    A trava é dura: com a gaveta aberta o balcão não anda, e quem libera é
    fechá-la. Por isso ``blocks`` (quantas vezes a pessoa esbarrou na trava) e
    ``open_seconds`` (quanto tempo a gaveta ficou aberta somada) são a medida
    honesta do hábito — antes o PIN cortava essa medição no meio.

    O resto é o que denuncia:

    - ``overrides`` — destraves de emergência. Deveria ser quase zero.
    - ``unlock_attempts`` — quantas vezes ALGUÉM abriu a tela de PIN, inclusive
      desistindo. A saída é escondida (Esc), então procurá-la é sinal.
    - ``sensor_blind`` — vezes que o sensor sumiu numa estação medida. Cabo
      solto acontece; cabo solto toda tarde, não.
    - ``left_open`` — gaveta esquecida aberta sem ninguém vender.
    - ``dismissals`` — esbarrou na trava e DESISTIU da venda em vez de fechar a
      gaveta. Uma é rotina (o cliente foi embora); repetida no mesmo turno é o
      hábito de trabalhar com a gaveta aberta.
    - ``longest_open_seconds`` — o pior episódio, que a média esconde.
    """

    operator: str
    blocks: int
    open_seconds: int
    longest_open_seconds: int
    overrides: int
    unlock_attempts: int
    sensor_blind: int
    left_open: int
    dismissals: int = 0


@dataclass(frozen=True)
class BICashDrawerAnomaly:
    """Um padrão que pede explicação. Não é acusação: é onde olhar.

    Nasce da frase do dono: *se não pudermos evitar a fraude, pelo menos temos
    que reconhecê-la*. Cada linha aponta um turno e diz o que não fecha.
    """

    code: str
    operator: str
    shift_key: int
    detail: str


@dataclass(frozen=True)
class BICashHourRow:
    """Uma hora do dia com atividade de gaveta. Só horas com algo aparecem."""

    hour: int
    drawer_openings: int
    drawer_unlocks: int
    blocks: int = 0
    open_seconds: int = 0


@dataclass(frozen=True)
class BICashMethodRow:
    method: str
    amount_q: int


@dataclass(frozen=True)
class BICashPrevious:
    """O período de mesmo tamanho imediatamente anterior (F7 — comparação)."""

    date_from: str
    date_to: str
    shifts_total: int
    difference_total_q: int
    difference_by_day: tuple[int, ...]  # alinhado posicionalmente com `days`


@dataclass(frozen=True)
class BICashReport:
    date_from: str
    date_to: str
    days: tuple[BICashDay, ...]
    by_operator: tuple[BICashOperatorRow, ...]
    payment_methods: tuple[BICashMethodRow, ...]
    shifts_total: int
    difference_total_q: int
    closings_missing: int
    previous: BICashPrevious
    drawer_by_hour: tuple[BICashHourRow, ...]
    accounts: BICashAccounts = BICashAccounts()
    drawer_by_operator: tuple[BICashDrawerRow, ...] = ()
    drawer_anomalies: tuple[BICashDrawerAnomaly, ...] = ()


def build_bi_cash(
    *, date_from: date | None = None, date_to: date | None = None
) -> BICashReport:
    from shopman.cashman.models import Entry

    from shopman.backstage.bi.canonical import iter_days, local_window
    from shopman.backstage.bi.sources import cashman
    from shopman.backstage.models import DayClosing

    from .bi_production import _normalize_window

    date_from, date_to = _normalize_window(date_from, date_to)
    Kind = Entry.Kind

    day_shifts: dict[date, int] = defaultdict(int)
    day_difference: dict[date, int] = defaultdict(int)
    operator_shifts: dict[str, int] = defaultdict(int)
    operator_difference: dict[str, int] = defaultdict(int)
    shifts = cashman.read_closed_shifts(date_from, date_to)
    for shift in shifts:
        day = shift.closed_at.date()
        difference_q = shift.difference_q or 0
        day_shifts[day] += 1
        day_difference[day] += difference_q
        # A quebra só ganha dono quando o livro prova que uma pessoa lançou
        # sozinha naquele turno. Turno com várias mãos entra no total do dia e
        # da gaveta, e em ninguém — ratear inventaria um culpado.
        sozinho = shift.sole_operator_key
        if sozinho:
            operator_shifts[sozinho] += 1
            operator_difference[sozinho] += difference_q

    # Uma passada pelo livro: sangria/suprimento por dia, e o comportamento de
    # gaveta por operador E por hora — "quem" e "quando" são as duas perguntas
    # do gerente. Operador que só tem evento (turno ainda aberto) também entra
    # na tabela: a abertura de gaveta não espera o fechamento para contar.
    day_movements: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    operator_events: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hour_events: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    counted = (Kind.DRAWER_OPEN, Kind.DRAWER_UNLOCK, Kind.CHANGE_REQUESTED)
    operator_account_settled: dict[str, int] = defaultdict(int)
    forensics = _DrawerForensics()
    for event in cashman.read_events(local_window(date_from, date_to)):
        forensics.observe(event)
        if event.kind in (Kind.CASH_OUT, Kind.CASH_IN):
            day_movements[event.day][event.kind] += abs(event.amount_q)  # o sinal já é o tipo
        elif event.kind == Kind.ACCOUNT_SETTLED:
            operator_account_settled[event.operator_key] += event.amount_q
        elif event.kind in counted:
            operator_events[event.operator_key][event.kind] += 1
            if event.kind != Kind.CHANGE_REQUESTED:
                hour_events[event.at.hour][event.kind] += 1

    days = tuple(
        BICashDay(
            date=day.isoformat(),
            shifts=day_shifts.get(day, 0),
            difference_q=day_difference.get(day, 0),
            sangria_q=day_movements[day][Kind.CASH_OUT],
            suprimento_q=day_movements[day][Kind.CASH_IN],
        )
        for day in iter_days(date_from, date_to)
    )

    method_totals: dict[str, int] = defaultdict(int)
    closed_dates = set()
    for closing in DayClosing.objects.filter(date__range=(date_from, date_to)):
        closed_dates.add(closing.date)
        data = closing.data if isinstance(closing.data, dict) else {}
        totals = (data.get("cash_shift_summary") or {}).get("payment_method_totals") or {}
        for method, amount in totals.items():
            if method.endswith("_count") or not isinstance(amount, int):
                continue
            method_totals[method] += amount

    operators = sorted(set(operator_shifts) | set(operator_events) | set(operator_account_settled))
    window_days = (date_to - date_from).days + 1

    return BICashReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=days,
        by_operator=tuple(
            BICashOperatorRow(
                operator=operator,
                shifts=operator_shifts.get(operator, 0),
                difference_q=operator_difference.get(operator, 0),
                drawer_openings=operator_events[operator][Kind.DRAWER_OPEN],
                drawer_unlocks=operator_events[operator][Kind.DRAWER_UNLOCK],
                change_requests=operator_events[operator][Kind.CHANGE_REQUESTED],
                account_settled_q=operator_account_settled.get(operator, 0),
            )
            for operator in operators
        ),
        payment_methods=tuple(
            BICashMethodRow(method=method, amount_q=method_totals[method])
            for method in sorted(method_totals, key=lambda m: -method_totals[m])
        ),
        shifts_total=len(shifts),
        difference_total_q=sum(day_difference.values()),
        closings_missing=window_days - len(closed_dates),
        previous=_cash_previous(date_from, date_to),
        drawer_by_hour=tuple(
            BICashHourRow(
                hour=hour,
                drawer_openings=hour_events[hour][Kind.DRAWER_OPEN],
                drawer_unlocks=hour_events[hour][Kind.DRAWER_UNLOCK],
                blocks=forensics.hour_blocks[hour],
                open_seconds=forensics.hour_open_ms[hour] // 1000,
            )
            for hour in sorted(set(hour_events) | set(forensics.hour_blocks))
        ),
        drawer_by_operator=forensics.by_operator(),
        drawer_anomalies=forensics.anomalies(),
        accounts=_cash_accounts(date_from, date_to, settled_cash_q=sum(operator_account_settled.values())),
    )


def _cash_accounts(date_from: date, date_to: date, *, settled_cash_q: int) -> BICashAccounts:
    """Conta do cliente: dívida nova e acerto na janela (Payman), saldo em aberto hoje (derivado)."""
    from django.db.models import Sum
    from shopman.payman.models import PaymentIntent

    from shopman.backstage.bi.canonical import local_window
    from shopman.shop.services import house_account

    window = local_window(date_from, date_to)
    account = PaymentIntent.objects.filter(method=PaymentIntent.Method.ACCOUNT)
    sales_q = int(account.filter(authorized_at__range=window).aggregate(t=Sum("amount_q"))["t"] or 0)
    settled_q = int(
        account.filter(captured_at__range=window, status__in=["captured", "refunded"]).aggregate(t=Sum("amount_q"))["t"] or 0
    )
    balances = house_account.balances()
    return BICashAccounts(
        sales_q=sales_q,
        settled_q=settled_q,
        settled_cash_q=settled_cash_q,
        open_q=sum(row.balance_q for row in balances),
        open_customers=len(balances),
        top_open=tuple(BICashAccountRow(customer_name=row.customer_name, balance_q=row.balance_q) for row in balances[:5]),
    )


def _cash_previous(date_from: date, date_to: date) -> BICashPrevious:
    from shopman.backstage.bi.canonical import iter_days
    from shopman.backstage.bi.sources import cashman

    from .bi_production import _previous_window

    prev_from, prev_to = _previous_window(date_from, date_to)
    day_difference: dict[date, int] = defaultdict(int)
    shifts = cashman.read_closed_shifts(prev_from, prev_to)
    for shift in shifts:
        day_difference[shift.closed_at.date()] += shift.difference_q or 0

    return BICashPrevious(
        date_from=prev_from.isoformat(),
        date_to=prev_to.isoformat(),
        shifts_total=len(shifts),
        difference_total_q=sum(day_difference.values()),
        difference_by_day=tuple(day_difference.get(day, 0) for day in iter_days(prev_from, prev_to)),
    )


class _DrawerForensics:
    """Lê o livro uma vez e responde: quem abre a gaveta, por quanto tempo, e o que não fecha.

    ⚠️ **Isto existe porque a fraude nem sempre dá para impedir.** O agente do
    balcão roda NA máquina do caixa: quem tem a máquina tem o canal. Dá para
    derrubar o agente, puxar o cabo da gaveta, ou — com trabalho — fazer a
    loopback responder ``open: false`` para sempre. Nenhuma trava do PDV alcança
    isso, e prometer o contrário seria mentira.

    O que **é** garantível é o reconhecimento depois, e é para isso que esta
    classe existe: cada uma dessas manobras deixa uma assinatura no livro, e a
    assinatura é justamente a AUSÊNCIA do que deveria estar lá. Um turno com
    sangrias e nenhum bloqueio é possível (o operador pode ser cuidadoso), mas um
    balcão inteiro sem UM episódio de gaveta aberta, com o sensor armado, não é
    hábito — é sensor que não está falando.
    """

    #: Um turno com movimento de dinheiro e ZERO bloqueio é o padrão que denuncia
    #: o sensor silenciado. Abaixo disto é ruído estatístico de um balcão calmo.
    MIN_CASH_EVENTS_FOR_SILENCE = 5
    #: Destraves de emergência num turno. Emperrar acontece; emperrar toda hora
    #: é outra coisa.
    MAX_OVERRIDES_PER_SHIFT = 2
    #: Tentativas de abrir a tela de PIN num turno. A saída é escondida: quem a
    #: procura repetidamente está procurando alguma coisa.
    MAX_ATTEMPTS_PER_SHIFT = 3
    #: Desistências num turno. Cliente que vai embora acontece; acontecer o dia
    #: inteiro é outra coisa — é fechar a gaveta que está sobrando.
    MAX_DISMISSALS_PER_SHIFT = 3

    def __init__(self) -> None:
        self.blocks: dict[str, int] = defaultdict(int)
        self.open_ms: dict[str, int] = defaultdict(int)
        self.longest_ms: dict[str, int] = defaultdict(int)
        self.overrides: dict[str, int] = defaultdict(int)
        self.attempts: dict[str, int] = defaultdict(int)
        self.blind: dict[str, int] = defaultdict(int)
        self.left_open: dict[str, int] = defaultdict(int)
        self.dismissals: dict[str, int] = defaultdict(int)
        self.hour_blocks: dict[int, int] = defaultdict(int)
        self.hour_open_ms: dict[int, int] = defaultdict(int)
        # Por (turno, pessoa). ⚠️ A chave inclui a PESSOA de propósito: várias
        # mãos trabalham na mesma gaveta, e uma anomalia que aponta "o turno"
        # acusa quem abriu o caixa em vez de quem fez. Isso seria pior que não
        # apontar nada — o padrão é sobre comportamento de gente.
        self._blocks_by: dict[tuple[int, str], int] = defaultdict(int)
        self._cash_by: dict[tuple[int, str], int] = defaultdict(int)
        self._overrides_by: dict[tuple[int, str], int] = defaultdict(int)
        self._attempts_by: dict[tuple[int, str], int] = defaultdict(int)
        self._blind_by: dict[tuple[int, str], int] = defaultdict(int)
        self._dismissals_by: dict[tuple[int, str], int] = defaultdict(int)
        self._seen: set[tuple[int, str]] = set()

    def observe(self, event) -> None:
        from shopman.cashman.models import Entry

        who = event.operator_key
        chave = (event.shift_key, who)
        self._seen.add(chave)
        payload = event.payload or {}

        # "Mexeu na gaveta" para efeito de silêncio suspeito: dinheiro entrando
        # ou saindo em espécie, mais as aberturas sem venda. Pix e cartão não
        # contam — não abrem gaveta nenhuma.
        if event.kind in (Entry.Kind.CASH_IN, Entry.Kind.CASH_OUT, Entry.Kind.DRAWER_OPEN, Entry.Kind.REFUND):
            self._cash_by[chave] += 1

        if event.kind == Entry.Kind.DRAWER_UNLOCK:
            self.overrides[who] += 1
            self._overrides_by[chave] += 1
            return

        if event.kind != Entry.Kind.NOTE:
            return

        evento = payload.get("event")
        if evento == "drawer_blocked":
            duracao = int(payload.get("duration_ms") or 0)
            self.blocks[who] += 1
            self.open_ms[who] += duracao
            self.longest_ms[who] = max(self.longest_ms[who], duracao)
            self.hour_blocks[event.at.hour] += 1
            self.hour_open_ms[event.at.hour] += duracao
            self._blocks_by[chave] += 1
            if payload.get("outcome") == "dismissed":
                self.dismissals[who] += 1
                self._dismissals_by[chave] += 1
        elif evento == "drawer_unlock_attempt":
            self.attempts[who] += 1
            self._attempts_by[chave] += 1
        elif evento == "drawer_sensor_blind":
            self.blind[who] += 1
            self._blind_by[chave] += 1
        elif evento == "drawer_left_open":
            self.left_open[who] += 1

    def by_operator(self) -> tuple[BICashDrawerRow, ...]:
        pessoas = (
            set(self.blocks) | set(self.overrides) | set(self.attempts)
            | set(self.blind) | set(self.left_open) | set(self.dismissals)
        )
        return tuple(
            BICashDrawerRow(
                operator=who,
                blocks=self.blocks[who],
                open_seconds=self.open_ms[who] // 1000,
                longest_open_seconds=self.longest_ms[who] // 1000,
                overrides=self.overrides[who],
                unlock_attempts=self.attempts[who],
                sensor_blind=self.blind[who],
                left_open=self.left_open[who],
                dismissals=self.dismissals[who],
            )
            for who in sorted(pessoas)
        )

    def anomalies(self) -> tuple[BICashDrawerAnomaly, ...]:
        achados: list[BICashDrawerAnomaly] = []
        for shift_key, operador in sorted(self._seen):
            chave = (shift_key, operador)
            caixa = self._cash_by[chave]
            bloqueios = self._blocks_by[chave]
            if caixa >= self.MIN_CASH_EVENTS_FOR_SILENCE and bloqueios == 0:
                achados.append(BICashDrawerAnomaly(
                    code="drawer_never_blocked",
                    operator=operador,
                    shift_key=shift_key,
                    detail=(
                        f"{caixa} movimentos de dinheiro e NENHUM bloqueio por gaveta aberta. "
                        "Ou a gaveta fechou instantaneamente todas as vezes, ou o sensor não "
                        "estava falando com o PDV."
                    ),
                ))
            if self._overrides_by[chave] > self.MAX_OVERRIDES_PER_SHIFT:
                achados.append(BICashDrawerAnomaly(
                    code="too_many_overrides",
                    operator=operador,
                    shift_key=shift_key,
                    detail=(
                        f"{self._overrides_by[chave]} destraves de emergência no mesmo turno. "
                        "A emergência é a gaveta emperrada; emperrar tantas vezes é conserto, não exceção."
                    ),
                ))
            if self._attempts_by[chave] > self.MAX_ATTEMPTS_PER_SHIFT:
                achados.append(BICashDrawerAnomaly(
                    code="hunting_for_the_exit",
                    operator=operador,
                    shift_key=shift_key,
                    detail=(
                        f"A tela de PIN da trava foi aberta {self._attempts_by[chave]}× neste turno. "
                        "A saída é escondida de propósito: procurá-la repetidamente é procurar alguma coisa."
                    ),
                ))
            if self._dismissals_by[chave] > self.MAX_DISMISSALS_PER_SHIFT:
                achados.append(BICashDrawerAnomaly(
                    code="gave_up_repeatedly",
                    operator=operador,
                    shift_key=shift_key,
                    detail=(
                        f"Esbarrou na trava e desistiu da venda {self._dismissals_by[chave]}× neste turno, "
                        "em vez de fechar a gaveta. Fechar leva um segundo; desistir tantas vezes é "
                        "trabalhar com a gaveta aberta de propósito."
                    ),
                ))
            if self._blind_by[chave]:
                achados.append(BICashDrawerAnomaly(
                    code="sensor_went_blind",
                    operator=operador,
                    shift_key=shift_key,
                    detail=(
                        f"O sensor da gaveta parou de responder {self._blind_by[chave]}× neste turno, "
                        "numa estação que TINHA medição. Cabo solto acontece uma vez; toda tarde é outra coisa."
                    ),
                ))
        return tuple(achados)
