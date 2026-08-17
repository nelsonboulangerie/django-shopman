"""Previsão de troco: o número, a faixa, e o que ela se recusa a dizer.

A tela existe para que faltar troco no meio da fila deixe de acontecer. O jeito
de ela falhar é o oposto do óbvio: não é errar o número, é afirmar um número
quando a base não sustenta afirmação nenhuma. Estes testes cobram exatamente as
bordas onde isso aconteceria.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import DayContext, HistoricalSale
from shopman.backstage.projections.bi_change import ForecastError, build_bi_change

pytestmark = pytest.mark.django_db

TICKET_Q = 5000


def _open(day: date, **fields) -> None:
    fields.setdefault("open_minutes", 540)
    DayContext.objects.update_or_create(date=day, defaults=fields)


def _sold(day: date, *, orders: int, cash: int = 0, change=None, prefix: str = "C") -> None:
    """``orders`` vendas no dia, das quais ``cash`` em dinheiro.

    ``change`` é o troco em centavos (pode ser uma função do índice, para variar
    dentro do dia). ``None`` grava a venda em dinheiro SEM valor recebido: é a
    venda que o operador finalizou sem digitar o que o cliente entregou.
    """
    tz = timezone.get_current_timezone()
    rows = []
    for index in range(orders):
        payment = {"method": "pix", "collection": "terminal", "amount_q": TICKET_Q}
        if index < cash:
            payment.update({"method": "cash", "cash_received_q": TICKET_Q})
            change_q = change(index) if callable(change) else change
            if change_q is not None:
                payment["tendered_q"] = TICKET_Q + change_q
                payment["change_q"] = change_q
        rows.append(
            Order(
                ref=f"{prefix}-{day.isoformat()}-{index}",
                channel_ref="pdv",
                status=Order.Status.COMPLETED,
                total_q=TICKET_Q,
                data={"payment": payment},
            )
        )
    Order.objects.bulk_create(rows)
    Order.objects.filter(ref__startswith=f"{prefix}-{day.isoformat()}-").update(
        created_at=timezone.datetime(day.year, day.month, day.day, 10, tzinfo=tz)
    )


def _history(*, days: int, orders: int = 12, cash: int = 6, change=350) -> None:
    today = timezone.localdate()
    for offset in range(1, days + 1):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=orders, cash=cash, change=change)


def _external(*, days: int, orders: int = 12, cash_share: float = 0.5) -> None:
    """Dois anos de export externo: tem total e forma de pagamento, nunca troco."""
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    rows = []
    external_id = 1
    for offset in range(1, days + 1):
        day = today - timedelta(days=offset)
        _open(day)
        for index in range(orders):
            rows.append(
                HistoricalSale(
                    source="yooga",
                    external_id=external_id,
                    occurred_at=timezone.datetime(day.year, day.month, day.day, 10, tzinfo=tz),
                    total_q=TICKET_Q,
                    payment="DINHEIRO" if index < orders * cash_share else "PIX",
                )
            )
            external_id += 1
    HistoricalSale.objects.bulk_create(rows, batch_size=1000)


@pytest.fixture
def wednesday() -> date:
    today = timezone.localdate()
    return today + timedelta(days=(2 - today.weekday()) % 7 or 7)


# ── O caminho feliz: valor E faixa ────────────────────────────────────────────


def test_base_suficiente_devolve_valor_e_faixa(wednesday):
    # Troco variando de dia para dia: sem variação não há faixa a mostrar.
    today = timezone.localdate()
    for offset in range(1, 121):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=12, cash=6, change=200 + (offset % 5) * 150)

    day = build_bi_change(target=wednesday).days[0]

    assert day.change_q is not None
    assert day.change_q.low < day.change_q.expected < day.change_q.high
    # Metade das vendas em dinheiro, ~12 pedidos por dia: ~6 vendas em dinheiro
    # a algo entre R$ 2 e R$ 8 de troco.
    assert day.cash_orders.expected == pytest.approx(6, abs=2)
    assert 1000 <= day.change_q.expected <= 6000
    assert day.missing_reason == ""


def test_a_fatia_de_dinheiro_vem_dos_dias_parecidos(wednesday):
    """O primeiro fator PODE usar o histórico externo: forma de pagamento ele tem.

    As duas fontes divergem de propósito. O sistema novo mede semanas em que
    todo mundo pagou em dinheiro; os dois anos anteriores dizem que metade
    paga. Se a fatia saísse só das semanas medidas, ela viria 100% e o dia
    pediria o dobro do troco que precisa.
    """
    _external(days=200, orders=20, cash_share=0.5)
    # Medição de troco só nas últimas semanas, como na vida real.
    for offset in range(1, 41):
        day = timezone.localdate() - timedelta(days=offset)
        _sold(day, orders=20, cash=20, change=lambda i: 150 + i * 40)

    day = build_bi_change(target=wednesday).days[0]

    assert day.cash_share_percent == pytest.approx(50, abs=6)
    assert day.cash_share_days >= 20  # bem além das semanas do sistema novo


# ── Base rasa: "ainda não sabemos", nunca um número ───────────────────────────


def test_base_rasa_nao_vira_numero(wednesday):
    """Movimento de sobra, medição de troco de menos: a resposta é a ausência."""
    _history(days=120, orders=12, cash=0)
    # Só três dias com troco medido — abaixo do mínimo.
    for offset in (1, 2, 3):
        _sold(
            timezone.localdate() - timedelta(days=offset),
            orders=8, cash=8, change=350, prefix="M",
        )

    report = build_bi_change(target=wednesday)

    assert report.habit is None
    assert report.mix is None
    assert report.missing_reason == "troco_sem_base"
    assert report.days[0].change_q is None
    assert report.days[0].missing_reason == "troco_sem_base"


def test_dia_com_poucas_vendas_em_dinheiro_nao_vira_observacao(wednesday):
    """Um dia com duas vendas em dinheiro é ruído com data, não hábito."""
    _history(days=120, orders=12, cash=2, change=350)

    assert build_bi_change(target=wednesday).habit is None


def test_nenhum_dia_do_historico_externo_entra_na_razao_troco_venda(wednesday):
    """Dois anos de export não substituem semanas de medição.

    O histórico tem total e forma de pagamento; troco ele NÃO tem. Se algum dia
    externo vazasse para o cálculo da razão, esta base de três dias nativos
    passaria a responder — e o número seria inventado.
    """
    _external(days=400, orders=20, cash_share=0.5)
    for offset in (1, 2, 3):
        _sold(
            timezone.localdate() - timedelta(days=offset),
            orders=20, cash=20, change=350, prefix="M",
        )

    report = build_bi_change(target=wednesday)

    assert report.habit is None
    assert report.missing_reason == "troco_sem_base"


def test_venda_em_dinheiro_sem_valor_recebido_nao_conta_como_troco_zero(wednesday):
    """Ausência de medição não é troco zero — contá-la assim manda abastecer menos."""
    today = timezone.localdate()
    for offset in range(1, 121):
        day = today - timedelta(days=offset)
        _open(day)
        # Seis vendas em dinheiro medidas a R$ 4,00 de troco, e mais seis sem
        # nenhum registro do valor recebido.
        _sold(day, orders=18, cash=6, change=400)
        _sold(day, orders=6, cash=6, change=None, prefix="N")

    report = build_bi_change(target=wednesday)

    assert report.habit.per_cash_order_q.expected == pytest.approx(400, abs=1)
    assert report.habit.unmeasured_orders > 0


# ── Faixa larga enquanto a base é curta, e ela diz por quê ────────────────────


def test_base_curta_mostra_os_extremos_e_declara(wednesday):
    _external(days=200, orders=20, cash_share=0.5)
    for offset in range(1, 15):  # duas semanas de medição
        _sold(
            timezone.localdate() - timedelta(days=offset),
            orders=20, cash=10, change=lambda i: 100 + i * 100,
        )

    habit = build_bi_change(target=wednesday).habit

    assert habit.band == "full_range"
    assert habit.measured_days < 28


def test_base_confortavel_usa_o_miolo(wednesday):
    _history(days=120, orders=12, cash=6, change=lambda i: 100 + i * 100)

    habit = build_bi_change(target=wednesday).habit

    assert habit.band == "interquartile"
    assert habit.measured_days >= 28


# ── Denominação: tendência, jamais contagem de peças ──────────────────────────


def test_composicao_e_tendencia_e_nunca_contagem_de_pecas(wednesday):
    """Trocos miúdos: a tela pode dizer 'a maior parte em moeda' e nada além."""
    _history(days=120, orders=12, cash=6, change=lambda i: 25 + i * 60)

    report = build_bi_change(target=wednesday)

    assert report.mix.tendency == "mostly_coins"
    assert 0 <= report.mix.coin_value_percent <= 100
    assert report.mix.small_change_percent >= 70
    # A fronteira, travada: o contrato da composição fala de VALOR e de
    # ocorrências, e não tem onde uma contagem de peças caberia. Ninguém
    # registra moeda a moeda num balcão, então um campo desses só poderia ser
    # inventado — e a tela passaria a afirmar "40 moedas de R$ 1".
    assert {f.name for f in fields(report.mix)} == {
        "tendency", "coin_value_percent", "small_change_percent", "sample_size",
    }


def test_troco_grande_nao_vira_tendencia_de_moeda(wednesday):
    _history(days=120, orders=12, cash=6, change=lambda i: 1500 + i * 500)

    mix = build_bi_change(target=wednesday).mix

    assert mix.tendency == "mostly_notes"
    assert mix.small_change_percent <= 30


def test_o_piso_de_moeda_sai_do_valor_previsto(wednesday):
    """Os centavos de cada troco não fecham em nota: esse pedaço é moeda."""
    _history(days=120, orders=12, cash=6, change=lambda i: 250 + i * 100)

    day = build_bi_change(target=wednesday).days[0]

    assert 0 < day.coin_floor_q < day.change_q.expected


# ── Casa fechada e período ────────────────────────────────────────────────────


def test_dia_fechado_nao_precisa_de_troco(wednesday, monkeypatch):
    _history(days=120)
    monkeypatch.setattr(
        "shopman.shop.services.business_calendar.is_open_on", lambda day, **kw: False
    )

    day = build_bi_change(target=wednesday).days[0]

    assert day.closed
    assert day.change_q.expected == 0.0
    assert day.missing_reason == ""


def test_semana_soma_os_dias(wednesday):
    _history(days=200, orders=12, cash=6, change=lambda i: 100 + i * 100)

    report = build_bi_change(target=wednesday, horizon="week")

    assert len(report.days) == 7
    assert report.total_change_q is not None
    assert report.total_change_q.expected == pytest.approx(
        sum(d.change_q.expected for d in report.days), rel=1e-6
    )


def test_semana_sem_um_dia_nao_tem_total(wednesday):
    """Um total de semana sem o sábado manda abastecer menos do que o dia pede."""
    today = timezone.localdate()
    for offset in range(1, 201):
        day = today - timedelta(days=offset)
        if day.weekday() == 5:
            continue
        _open(day)
        _sold(day, orders=12, cash=6, change=lambda i: 100 + i * 100)

    report = build_bi_change(target=wednesday, horizon="week")

    assert report.total_change_q is None
    assert len(report.total_missing_days) == 1


def test_horizonte_desconhecido_diz_quais_existem(wednesday):
    with pytest.raises(ForecastError, match="day, week, month"):
        build_bi_change(target=wednesday, horizon="trimestre")


# ── A projeção e a previsão de troco leem o mesmo passado ─────────────────────


def test_sem_projecao_de_pedidos_o_troco_repete_o_motivo(wednesday):
    """Duas telas, uma explicação: a ausência da projeção é a ausência do troco."""
    _history(days=21, orders=12, cash=6, change=350)

    day = build_bi_change(target=wednesday).days[0]

    assert day.change_q is None
    assert day.missing_reason == "amostra_insuficiente"
