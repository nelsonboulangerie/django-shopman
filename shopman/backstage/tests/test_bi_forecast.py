"""O que esperar: o número, a faixa, e as três recusas.

A projeção erra por natureza; o que ela não pode fazer é errar em silêncio.
Estes testes cobram o comportamento nos limites, que é onde uma tela de previsão
ou é honesta ou vira promessa: amostra curta, dia sem venda, casa fechada,
patamar que mudou.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import DayContext
from shopman.backstage.projections.bi_forecast import (
    ForecastError,
    build_bi_forecast,
)

pytestmark = pytest.mark.django_db

TICKET_Q = 5000


def _sold(day: date, *, orders: int, prefix: str = "F") -> None:
    """``orders`` pedidos naquele dia, cada um de R$ 50,00.

    ``prefix`` deixa um teste somar pedidos a um dia que já tem histórico sem
    colidir com as refs já criadas.
    """
    tz = timezone.get_current_timezone()
    for index in range(orders):
        order = Order.objects.create(
            ref=f"{prefix}-{day.isoformat()}-{index}",
            channel_ref="web",
            status=Order.Status.COMPLETED,
            total_q=TICKET_Q,
        )
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.datetime(day.year, day.month, day.day, 10, tzinfo=tz)
        )


def _open(day: date, **fields) -> None:
    fields.setdefault("open_minutes", 540)
    DayContext.objects.update_or_create(date=day, defaults=fields)


def _history(*, days: int, per_day, weekday_boost: dict | None = None) -> None:
    """Movimento diário para trás, com perfil por dia da semana."""
    today = timezone.localdate()
    for offset in range(1, days + 1):
        day = today - timedelta(days=offset)
        base = per_day(day) if callable(per_day) else per_day
        base += (weekday_boost or {}).get(day.weekday(), 0)
        _open(day)
        _sold(day, orders=base)


@pytest.fixture
def wednesday() -> date:
    today = timezone.localdate()
    return today + timedelta(days=(2 - today.weekday()) % 7 or 7)


# ── O caminho feliz ───────────────────────────────────────────────────────────


def test_projeta_a_quarta_a_partir_das_quartas_parecidas(wednesday):
    # Quartas valem o dobro de um dia comum, de forma consistente.
    _history(days=120, per_day=10, weekday_boost={2: 10})

    report = build_bi_forecast(target=wednesday)

    day = report.days[0]
    assert day.revenue_q is not None
    # 20 pedidos numa quarta contra um movimento típico de ~10: a projeção tem
    # de chegar perto de 20 pedidos, não da média geral.
    assert 17 <= day.orders.expected <= 23
    assert day.basis.sample_size >= 5


def test_a_resposta_e_faixa_e_nao_ponto(wednesday):
    _history(days=120, per_day=lambda d: 10 + (d.day % 5))

    report = build_bi_forecast(target=wednesday)

    day = report.days[0]
    assert day.revenue_q.low < day.revenue_q.expected < day.revenue_q.high


def test_o_patamar_de_hoje_manda_no_numero(wednesday):
    """A casa dobrou de tamanho: a projeção acompanha, sem esperar um ano."""
    today = timezone.localdate()
    for offset in range(1, 121):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=20 if offset <= 40 else 10)

    report = build_bi_forecast(target=wednesday)

    # O passado longo vendia 10; o presente vende 20. A forma das quartas é
    # neutra aqui, então a projeção tem de morar perto do patamar de agora.
    assert report.days[0].orders.expected > 15


# ── As três recusas ───────────────────────────────────────────────────────────


def test_amostra_insuficiente_nao_vira_numero(wednesday):
    _history(days=21, per_day=10)

    report = build_bi_forecast(target=wednesday)

    day = report.days[0]
    assert day.revenue_q is None
    assert day.missing_reason == "amostra_insuficiente"


def test_sem_movimento_recente_nao_ha_projecao(wednesday):
    """Sem patamar de agora não há a que aplicar a forma do passado."""
    today = timezone.localdate()
    for offset in range(60, 180):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=10)

    report = build_bi_forecast(target=wednesday)

    assert report.days[0].revenue_q is None
    assert report.days[0].missing_reason == "sem_movimento_recente"


def test_patamar_que_mede_o_sistema_e_nao_a_casa_nao_projeta(wednesday):
    """Durante uma migração o presente registra uma fração do movimento.

    Multiplicar a forma do passado por esse patamar devolveria um número muitas
    vezes menor, com toda a aparência de estar certo.
    """
    today = timezone.localdate()
    for offset in range(1, 366):
        day = today - timedelta(days=offset)
        _open(day)
        # Últimos 30 dias com 3% do movimento: o sistema novo mal começou.
        _sold(day, orders=1 if offset <= 30 else 30)

    report = build_bi_forecast(target=wednesday)

    assert report.days[0].revenue_q is None
    assert report.days[0].missing_reason == "patamar_nao_representativo"


def test_queda_sazonal_de_verdade_continua_projetando(wednesday):
    """Janeiro real da casa fica em 31% do ano, e isso é procura, não lacuna."""
    today = timezone.localdate()
    for offset in range(1, 366):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=10 if offset <= 30 else 30)

    report = build_bi_forecast(target=wednesday)

    assert report.days[0].revenue_q is not None


def test_dia_parecido_sem_venda_e_descartado_e_declarado(wednesday):
    _history(days=120, per_day=10)
    # Duas quartas sem venda nenhuma registrada: não são quartas de zero real.
    mudas = [d for d in _wednesdays_back(120) if d.weekday() == 2][:2]
    Order.objects.filter(created_at__date__in=mudas).delete()

    report = build_bi_forecast(target=wednesday)

    assert report.days[0].basis.without_sales == 2
    # E não puxaram o número para baixo: continua no patamar dos outros dias.
    assert report.days[0].orders.expected >= 8


def _wednesdays_back(days: int) -> list[date]:
    today = timezone.localdate()
    return [today - timedelta(days=offset) for offset in range(1, days + 1)]


# ── Casa fechada: zero declarado, não ausência ────────────────────────────────


def test_dia_fechado_e_zero_sabido_nao_lacuna(wednesday, monkeypatch):
    _history(days=120, per_day=10)
    monkeypatch.setattr(
        "shopman.shop.services.business_calendar.is_open_on", lambda day, **kw: False
    )

    report = build_bi_forecast(target=wednesday)

    day = report.days[0]
    assert day.closed
    assert day.revenue_q.expected == 0.0
    assert day.missing_reason == ""


# ── Período: soma dos dias, e só quando todos respondem ───────────────────────


def test_semana_soma_os_dias(wednesday):
    _history(days=200, per_day=10, weekday_boost={5: 15})

    report = build_bi_forecast(target=wednesday, horizon="week")

    assert len(report.days) == 7
    assert report.total_orders is not None
    assert report.total_orders.expected == pytest.approx(
        sum(d.orders.expected for d in report.days), rel=1e-6
    )
    assert report.total_missing_days == ()


def test_semana_sem_um_dia_nao_tem_total(wednesday):
    """Uma semana sem o sábado é um número que ninguém deve usar."""
    today = timezone.localdate()
    for offset in range(1, 201):
        day = today - timedelta(days=offset)
        if day.weekday() == 5:
            continue  # nenhum sábado no histórico
        _open(day)
        _sold(day, orders=10)

    report = build_bi_forecast(target=wednesday, horizon="week")

    assert report.total_orders is None
    assert len(report.total_missing_days) == 1


def test_mes_cobre_o_mes_inteiro(wednesday):
    _history(days=200, per_day=10)

    report = build_bi_forecast(target=wednesday, horizon="month")

    assert report.days[0].date.endswith("-01")
    assert len(report.days) in (28, 29, 30, 31)


def test_horizonte_desconhecido_diz_quais_existem(wednesday):
    with pytest.raises(ForecastError, match="day, week, month"):
        build_bi_forecast(target=wednesday, horizon="trimestre")


# ── Ramos de clima: a fundação da resposta condicional ────────────────────────


def test_ramos_separam_frio_de_calor(wednesday):
    """Sem previsão do tempo: mostra os dois lados e deixa o padeiro escolher."""
    today = timezone.localdate()
    for offset in range(1, 201):
        day = today - timedelta(days=offset)
        quente = day.isocalendar().week % 2 == 0
        _open(day, temp_max_c=Decimal("31.0") if quente else Decimal("15.0"))
        _sold(day, orders=16 if quente else 8)

    report = build_bi_forecast(target=wednesday)

    branches = {b.key: b for b in report.days[0].branches}
    assert {"cold", "warm"} <= set(branches)
    assert branches["warm"].orders.expected > branches["cold"].orders.expected
    assert branches["cold"].sample_size >= 5


def test_sem_clima_carregado_nao_ha_ramos(wednesday):
    _history(days=200, per_day=10)

    report = build_bi_forecast(target=wednesday)

    assert report.days[0].branches == ()


def test_ramo_com_amostra_curta_nao_aparece(wednesday):
    """Um ramo de três dias é coincidência com legenda, não resposta."""
    today = timezone.localdate()
    for offset in range(1, 201):
        day = today - timedelta(days=offset)
        # Só duas quartas quentes em toda a janela.
        quente = day.weekday() == 2 and offset in (7, 14)
        _open(day, temp_max_c=Decimal("33.0") if quente else Decimal("15.0"))
        _sold(day, orders=10)

    report = build_bi_forecast(target=wednesday)

    assert all(b.key != "warm" for b in report.days[0].branches)


# ── Data comercial: a resposta é observação, não projeção ─────────────────────


def _commercial(day: date, name: str) -> None:
    DayContext.objects.update_or_create(
        date=day,
        defaults={"open_minutes": 540, "has_calendar": True, "commercial_name": name},
    )


def test_data_comercial_mostra_o_que_o_dia_fez_antes(wednesday):
    """Duas ocorrências não preveem, mas dizem o que aconteceu — e isso vale."""
    today = timezone.localdate()
    _history(days=400, per_day=10)
    _commercial(wednesday, "Dia dos Namorados")
    # Duas ocorrências passadas da MESMA data, ambas com o dobro do movimento.
    passadas = [today - timedelta(days=90), today - timedelta(days=360)]
    for day in passadas:
        _commercial(day, "Dia dos Namorados")
        _sold(day, orders=10, prefix="EXTRA")  # dobra o dia (já tinha 10)

    occasion = build_bi_forecast(target=wednesday).days[0].occasion

    assert occasion is not None
    assert occasion.name == "Dia dos Namorados"
    assert len(occasion.years) == 2
    assert all(y.ratio > 1.5 for y in occasion.years)
    assert occasion.expected_revenue_q > 0


def test_a_vespera_e_a_mesma_ocasiao_vista_do_dia_que_vende(wednesday):
    """A casa fecha no domingo do dia das mães: o dinheiro está no sábado."""
    today = timezone.localdate()
    _history(days=400, per_day=10)
    _eve(wednesday, "Dia das Mães")
    passadas = [today - timedelta(days=90), today - timedelta(days=360)]
    for day in passadas:
        _eve(day, "Dia das Mães")
        _sold(day, orders=10, prefix="EXTRA")

    occasion = build_bi_forecast(target=wednesday).days[0].occasion

    assert occasion is not None
    assert occasion.name == "Dia das Mães"
    assert occasion.is_eve
    assert len(occasion.years) == 2


def test_vespera_nao_se_mistura_com_o_dia_em_si(wednesday):
    """As duas medem a mesma data, em posições que vendem diferente."""
    today = timezone.localdate()
    _history(days=400, per_day=10)
    _eve(wednesday, "Dia das Mães")
    _eve(today - timedelta(days=90), "Dia das Mães")
    _eve(today - timedelta(days=360), "Dia das Mães")
    # O dia em si, duas vezes: não pode entrar na amostra da véspera.
    _commercial(today - timedelta(days=89), "Dia das Mães")
    _commercial(today - timedelta(days=359), "Dia das Mães")

    occasion = build_bi_forecast(target=wednesday).days[0].occasion

    assert occasion.is_eve
    assert len(occasion.years) == 2


def _eve(day: date, name: str) -> None:
    DayContext.objects.update_or_create(
        date=day,
        defaults={
            "open_minutes": 540, "has_calendar": True,
            "is_special_eve": True, "eve_of": name,
        },
    )


def test_dia_comum_nao_tem_bloco_de_ocasiao(wednesday):
    _history(days=200, per_day=10)

    assert build_bi_forecast(target=wednesday).days[0].occasion is None


def test_data_comercial_sem_ocorrencia_passada_nao_vira_bloco_vazio(wednesday):
    """Sem fato, sem bloco — nada de 'nenhuma ocorrência anterior' na tela."""
    _history(days=200, per_day=10)
    _commercial(wednesday, "Data Nova")

    assert build_bi_forecast(target=wednesday).days[0].occasion is None


# ── O mesmo dia não pode valer dois números em duas telas ─────────────────────


def test_serie_diaria_bate_com_o_painel_de_vendas():
    """Painel e projeção leem o mesmo passado — ou o B.I. inteiro perde crédito."""
    from shopman.backstage.projections.bi_sales import build_bi_sales
    from shopman.backstage.projections.sales_series import daily_sales

    today = timezone.localdate()
    since, until = today - timedelta(days=30), today - timedelta(days=1)
    for offset in range(1, 31):
        day = today - timedelta(days=offset)
        _open(day)
        _sold(day, orders=offset % 7 + 1)

    painel = {
        d.date: (d.revenue_q, d.orders)
        for d in build_bi_sales(date_from=since, date_to=until).days
        if d.orders
    }
    projecao = {
        day.isoformat(): (row.revenue_q, row.orders)
        for day, row in daily_sales(since, until).items()
    }

    assert projecao == painel
