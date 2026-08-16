"""Dias parecidos: o que entra na amostra, o que sai, e o que é declarado.

A tela de "o que esperar" é aritmética em cima desta lista, então um erro aqui
não aparece como erro: aparece como um número plausível e errado. Por isso os
testes cobram, além do resultado, a **prestação de contas** — o que foi
afrouxado e o que nunca esteve disponível são coisas diferentes, e confundi-las
mentiria de duas formas distintas.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.backstage.models import DayContext
from shopman.backstage.services.day_similarity import (
    similar_days,
    temperature_band,
    untrustworthy_days,
)

pytestmark = pytest.mark.django_db


def _context(day: date, **fields) -> DayContext:
    """Um dia carimbado como aberto, salvo se o teste disser o contrário."""
    fields.setdefault("open_minutes", 540)
    return DayContext.objects.create(date=day, **fields)


def _weekly(*, count: int, weekday: int = 2) -> list[date]:
    """As ``count`` últimas ocorrências de ``weekday`` antes de hoje.

    Sai da mais recente para a mais antiga, então ``[-1]`` é o início natural da
    janela do teste.
    """
    days = []
    day = timezone.localdate() - timedelta(days=1)
    while len(days) < count:
        if day.weekday() == weekday:
            days.append(day)
        day -= timedelta(days=1)
    return days


@pytest.fixture
def wednesday() -> date:
    """Uma quarta-feira futura — o alvo típico da pergunta."""
    today = timezone.localdate()
    ahead = (2 - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


# ── O critério base: dia da semana ────────────────────────────────────────────


def test_so_traz_o_mesmo_dia_da_semana(wednesday):
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day)
    # Uma terça e uma quinta, ambas abertas: não podem entrar na amostra.
    for day in (quartas[0] - timedelta(days=1), quartas[0] - timedelta(days=6)):
        _context(day)

    result = similar_days(wednesday, since=quartas[-1])

    assert result.sample_size == 6
    assert {d.weekday() for d in result.days} == {2}
    assert result.enough


def test_hoje_nunca_entra_porque_ainda_nao_terminou():
    today = timezone.localdate()
    _context(today)
    mesmos = _weekly(count=5, weekday=today.weekday())
    for day in mesmos:
        _context(day)

    result = similar_days(today + timedelta(days=7), since=mesmos[-1])

    assert today not in result.days
    assert result.window_to == today - timedelta(days=1)
    assert result.sample_size == 5


def test_janela_padrao_alcanca_os_dois_anos_de_historico(wednesday):
    """A base longa da casa são 2 anos; o padrão não pode ficar aquém dela."""
    result = similar_days(wednesday)

    assert (result.window_to - result.window_from).days >= 729


# ── Exclusões: não são "menos parecidos", são inválidos ───────────────────────


def test_dia_fechado_fica_fora_mesmo_afrouxando_tudo(wednesday):
    quartas = _weekly(count=6)
    fechada = quartas[0]
    _context(fechada, open_minutes=0, closed_reason="feriado")
    for day in quartas[1:]:
        _context(day)

    result = similar_days(wednesday, since=quartas[-1])

    assert fechada not in result.days
    assert result.excluded_closed == 1
    assert result.sample_size == 5


def test_dia_atrapalhado_fica_fora(wednesday, monkeypatch):
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day)
    atrapalhada = quartas[0]
    monkeypatch.setattr(
        "shopman.backstage.services.episodes.disrupted_days",
        lambda **kwargs: frozenset({atrapalhada}),
    )

    result = similar_days(wednesday, since=quartas[-1])

    assert atrapalhada not in result.days
    assert result.excluded_disrupted == 1


def test_so_conta_como_excluido_o_dia_que_teria_se_parecido(wednesday):
    """Domingo fechado não é quarta perdida — nunca foi candidato a esta amostra."""
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day)
    domingo = quartas[-1]
    while domingo <= quartas[0]:
        if domingo.weekday() == 6:
            _context(domingo, open_minutes=0, closed_reason="sem expediente")
        domingo += timedelta(days=1)

    result = similar_days(wednesday, since=quartas[-1])

    assert result.sample_size == 6
    assert result.excluded_closed == 0


def test_dia_sem_carimbo_cai_no_calendario_em_vez_de_sumir(wednesday):
    """Dia anterior à medição não pode desaparecer da amostra em silêncio."""
    quartas = _weekly(count=6)
    for day in quartas:
        DayContext.objects.create(date=day)  # sem open_minutes: não sabemos

    result = similar_days(wednesday, since=quartas[-1])

    # Sem loja configurada o calendário degrada para aberto — o dia entra.
    assert result.sample_size == 6
    assert result.excluded_closed == 0


# ── A escada de afrouxamento ──────────────────────────────────────────────────


def test_afrouxa_temperatura_quando_a_amostra_estrita_e_pequena(wednesday):
    _context(wednesday, temp_max_c=Decimal("31.0"))
    quartas = _weekly(count=8)
    # Só duas quartas na faixa do alvo; as outras seis, frias.
    for day in quartas[:2]:
        _context(day, temp_max_c=Decimal("32.0"))
    for day in quartas[2:]:
        _context(day, temp_max_c=Decimal("18.0"))

    result = similar_days(wednesday, since=quartas[-1])

    assert result.sample_size == 8
    assert "temperature" in result.relaxed
    assert "temperature" not in result.applied
    assert "weekday" in result.applied


def test_nao_afrouxa_quando_a_amostra_estrita_ja_basta(wednesday):
    _context(wednesday, temp_max_c=Decimal("31.0"))
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day, temp_max_c=Decimal("32.0"))

    result = similar_days(wednesday, since=quartas[-1])

    assert result.relaxed == ()
    assert "temperature" in result.applied
    assert result.sample_size == 6


def test_afrouxamento_para_no_primeiro_nivel_suficiente(wednesday):
    """Afrouxar demais joga fora semelhança que a amostra sustentava."""
    _context(wednesday, temp_max_c=Decimal("31.0"), holiday_name="Feriado", has_calendar=True)
    quartas = _weekly(count=10)
    for day in quartas[:6]:
        _context(day, temp_max_c=Decimal("18.0"), holiday_name="Feriado", has_calendar=True)
    for day in quartas[6:]:
        _context(day, temp_max_c=Decimal("18.0"), has_calendar=True)

    result = similar_days(wednesday, since=quartas[-1])

    # Bastou soltar a temperatura: o tipo de dia continua valendo.
    assert result.relaxed == ("temperature",)
    assert "day_kind" in result.applied
    assert result.sample_size == 6


def test_amostra_insuficiente_e_ausencia_e_nao_numero(wednesday):
    quartas = _weekly(count=3)
    for day in quartas:
        _context(day)

    result = similar_days(wednesday, since=quartas[-1])

    assert result.sample_size == 3
    assert not result.enough


# ── Afrouxado ≠ indisponível ──────────────────────────────────────────────────


def test_alvo_sem_temperatura_declara_indisponivel_nao_afrouxado(wednesday):
    """Um dia futuro não tem temperatura medida — isso não é afrouxar."""
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day, temp_max_c=Decimal("22.0"))

    result = similar_days(wednesday, since=quartas[-1])

    assert "temperature" in result.unavailable
    assert "temperature" not in result.relaxed
    assert "temperature" not in result.applied


def test_sem_calendario_carregado_tipo_de_dia_e_indisponivel(wednesday):
    _context(wednesday)
    quartas = _weekly(count=6)
    for day in quartas:
        _context(day)

    result = similar_days(wednesday, since=quartas[-1])

    assert "day_kind" in result.unavailable
    assert "day_kind" not in result.relaxed


def test_tipo_de_dia_separa_vespera_de_dia_comum(wednesday):
    _context(wednesday, is_special_eve=True, has_calendar=True)
    quartas = _weekly(count=12)
    for day in quartas[:6]:
        _context(day, is_special_eve=True, has_calendar=True)
    for day in quartas[6:]:
        _context(day, has_calendar=True)

    result = similar_days(wednesday, since=quartas[-1])

    assert result.sample_size == 6
    assert "day_kind" in result.applied
    assert result.relaxed == ()


# ── A régua da faixa de temperatura ───────────────────────────────────────────


def test_faixa_de_temperatura_agrupa_de_cinco_em_cinco():
    assert temperature_band(Decimal("31.0")) == temperature_band(Decimal("34.9"))
    assert temperature_band(Decimal("31.0")) != temperature_band(Decimal("35.0"))


def test_sem_medicao_nao_ha_faixa():
    assert temperature_band(None) == ""


# ── O caso degenerado: dias que não ensinam nada ──────────────────────────────


def test_untrustworthy_days_junta_fechado_e_atrapalhado(monkeypatch):
    today = timezone.localdate()
    since, until = today - timedelta(days=6), today - timedelta(days=1)
    fechado = since + timedelta(days=1)
    atrapalhado = since + timedelta(days=2)
    for offset in range(6):
        day = since + timedelta(days=offset)
        _context(day, open_minutes=0 if day == fechado else 540)
    monkeypatch.setattr(
        "shopman.backstage.services.episodes.disrupted_days",
        lambda **kwargs: frozenset({atrapalhado}),
    )

    days = untrustworthy_days(since=since, until=until)

    assert fechado in days
    assert atrapalhado in days
    assert since not in days
