"""O seed precisa dar o que ver: dois anos com estrutura reconhecível.

Uma tela de "o que esperar" sobre 42 dias de dados não demonstra nada — não há
duas quartas de dezembro, nem um dia das mães, nem um feriado. E pior: as regras
de honestidade da casa (dimensão só aparece com dado carregado) esconderiam a
funcionalidade num banco semeado, fazendo parecer que ela não existe.

⚠️ **Dois testes, não oito.** Rodar o seed é caro, e uma fixture de escopo maior
teria de escrever fora da transação do teste — os dados sobreviveriam ao
rollback e contaminariam a suíte inteira (usuário duplicado, contagem alterada).
Um teste por pergunta seria mais bonito e mais errado.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.models import DayContext, HistoricalSale, HistoricalSaleItem
from shopman.backstage.projections.bi_explore import available_context_dimensions
from shopman.backstage.projections.bi_forecast import build_bi_forecast

pytestmark = pytest.mark.django_db


def _seed(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())


def test_seed_da_dois_anos_de_base_com_contexto_e_origem_declarada(monkeypatch):
    """A matéria-prima: venda longa, calendário, clima — e nada se passando por real."""
    _seed(monkeypatch)
    today = timezone.localdate()

    sales = HistoricalSale.objects.filter(source="seed")
    assert sales.count() > 3000
    assert (today - sales.order_by("occurred_at").first().occurred_at.date()).days > 700
    assert HistoricalSaleItem.objects.filter(sale__source="seed").exists()

    # Dado de demonstração não pode se passar por um export real do Yooga.
    assert not HistoricalSale.objects.filter(source="yooga").exists()

    # Sem calendário carregado, "tipo de dia" nem apareceria no seletor.
    assert DayContext.objects.filter(has_calendar=True, holiday_name="Natal").exists()
    assert DayContext.objects.filter(is_special_eve=True).exists()

    com_clima = DayContext.objects.filter(temp_max_c__isnull=False)
    assert com_clima.count() > 700
    assert (today - com_clima.order_by("date").first().date).days > 700

    assert {"day_kind", "temperature"} <= set(available_context_dimensions())


def test_a_estrutura_do_seed_chega_ate_a_projecao(monkeypatch):
    """De nada adianta o dado existir se a tela não conseguir enxergá-lo."""
    _seed(monkeypatch)
    today = timezone.localdate()

    saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    monday = today + timedelta(days=(0 - today.weekday()) % 7 or 7)
    sabado = build_bi_forecast(target=saturday).days[0]
    segunda = build_bi_forecast(target=monday).days[0]

    assert sabado.revenue_q is not None, sabado.missing_reason
    assert segunda.revenue_q is not None, segunda.missing_reason
    # O perfil por dia da semana do seed tem de sobreviver até o número.
    assert sabado.revenue_q.expected > segunda.revenue_q.expected

    # E o número vem acompanhado do que o sustenta.
    assert sabado.basis.sample_size >= 5
    assert sabado.revenue_q.low < sabado.revenue_q.expected < sabado.revenue_q.high
    assert sabado.basis.level_days >= 10
