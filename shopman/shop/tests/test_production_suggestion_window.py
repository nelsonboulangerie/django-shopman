"""A janela de histórico que a sugestão de produção enxerga.

Duas perguntas, ambas sobre QUAIS dias entram na amostra:

1. O recorte por dia-da-semana segue o dia PLANEJADO, não o dia em que o
   cálculo roda. Planejar sábado numa sexta tem de olhar sábados — e o comando
   roda para amanhã por default, então o caso normal é justamente esse.
2. Dia sem expediente não é dia fraco: sai da amostra em vez de entrar como
   zero e puxar a média da semana inteira para baixo.

Os testes de backend existentes trocam ``history`` por um mock, então nunca
exercitaram o filtro de verdade. Estes criam pedidos reais e olham o resultado.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.orderman.models import Order, OrderItem

from shopman.shop.services.production import closed_days_within, suggest_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    from shopman.offerman.models import Product

    Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=100, is_sellable=True
    )
    pao = Recipe.objects.create(
        ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("10")
    )
    RecipeItem.objects.create(recipe=pao, input_sku="FARINHA", quantity="5", unit="kg")
    return pao


def _sold_on(day: date, *, qty: int, ref: str) -> None:
    """Um pedido concluído de PAO no dia ``day``."""
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="completed", total_q=qty * 100
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=qty,
        unit_price_q=100, line_total_q=qty * 100,
    )
    stamp = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.min.time().replace(hour=10))
    )
    Order.objects.filter(pk=order.pk).update(created_at=stamp)


def _same_weekday_days_before(anchor: date, *, count: int) -> list[date]:
    """As ``count`` datas anteriores a hoje com o mesmo dia-da-semana de ``anchor``."""
    today = timezone.localdate()
    out, day = [], anchor - timedelta(days=7)
    while len(out) < count:
        if day < today:
            out.append(day)
        day -= timedelta(days=7)
    return out


class TestSuggestionSamplesThePlannedWeekday:
    def test_planning_tomorrow_samples_tomorrows_weekday(self, recipe):
        """A amostra é do dia planejado, não do dia em que se planeja.

        Sem isso, planejar o sábado na sexta lê o histórico das sextas — e
        sábado de padaria não é sexta.
        """
        tomorrow = timezone.localdate() + timedelta(days=1)
        today = timezone.localdate()

        # Dia planejado (amanhã): venda forte.
        for index, day in enumerate(_same_weekday_days_before(tomorrow, count=3)):
            _sold_on(day, qty=30, ref=f"FORTE-{index}")
        # Dia em que o cálculo roda (hoje): venda fraca. Não pode contaminar.
        for index, day in enumerate(_same_weekday_days_before(today, count=3)):
            _sold_on(day, qty=4, ref=f"FRACO-{index}")

        line = next(s for s in suggest_for(tomorrow) if s.recipe.pk == recipe.pk)

        assert line.basis["sample_size"] == 3
        assert Decimal(line.basis["avg_demand"]) == Decimal("30")
        # 30 * 1.20 de margem = 36
        assert line.quantity == Decimal("36")

    def test_planning_today_still_samples_today(self, recipe):
        """O caso trivial continua certo: planejar hoje lê o histórico de hoje."""
        today = timezone.localdate()
        for index, day in enumerate(_same_weekday_days_before(today, count=2)):
            _sold_on(day, qty=10, ref=f"HOJE-{index}")

        line = next(s for s in suggest_for(today) if s.recipe.pk == recipe.pk)

        assert line.basis["sample_size"] == 2
        assert Decimal(line.basis["avg_demand"]) == Decimal("10")


class TestClosedDaysLeaveTheSample:
    def test_closed_day_is_not_counted_as_a_weak_day(self, recipe):
        """Loja fechada sai da amostra em vez de entrar como dia fraco."""
        from shopman.shop.models import Shop

        today = timezone.localdate()
        target = today + timedelta(days=1)
        sample = _same_weekday_days_before(target, count=3)
        for index, day in enumerate(sample):
            _sold_on(day, qty=20, ref=f"ABERTO-{index}")

        # O dia mais recente da amostra vira feriado declarado.
        closed_day = sample[0]
        shop = Shop.objects.create(name="Nelson")
        shop.opening_hours = {
            name: {"open": "09:00", "close": "18:00"}
            for name in (
                "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday",
            )
        }
        shop.defaults = {
            "closed_dates": [{"date": closed_day.isoformat(), "label": "Feriado"}]
        }
        shop.save()

        assert closed_day in closed_days_within(days=28)

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        # O dia fechado tinha venda registrada; ainda assim sai da amostra —
        # o que resta são os outros dois dias do mesmo dia-da-semana.
        assert line.basis["sample_size"] == 2
        assert line.basis["excluded_days"] >= 1

    def test_no_calendar_configured_excludes_nothing(self, recipe):
        """Sem agenda, a sugestão prefere amostra a mais do que amostra fantasma."""
        assert closed_days_within(days=28) == frozenset()
