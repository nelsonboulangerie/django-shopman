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


def _first_day_of_next_month() -> date:
    today = timezone.localdate()
    return (today.replace(day=1) + timedelta(days=32)).replace(day=1)


def _seasons(months_by_season: dict, **extra) -> None:
    from shopman.shop.models import Shop

    shop = Shop.load() or Shop.objects.create(name="Nelson")
    shop.defaults = {
        **(shop.defaults or {}),
        "production": {"suggestion": {"seasons": months_by_season, **extra}},
    }
    shop.save()


class TestSeasonStartUsesThePreviousSeason:
    """Começo de estação: a janela inteira ainda é da estação que acabou.

    A data planejada é o dia 1 do mês que vem e a estação corrente é só esse
    mês, então nenhum dia da janela (que termina ontem) é da estação corrente.
    Sem a troca, o filtro por meses deixava a ficha sem amostra e a sugestão
    sumia; com ela, a conta usa a estação anterior e diz isso.
    """

    def test_new_season_without_history_falls_back_to_previous(self, recipe):
        target = _first_day_of_next_month()
        others = [m for m in range(1, 13) if m != target.month]
        _seasons({"hot": [target.month], "mild": others})
        for index, day in enumerate(_same_weekday_days_before(target, count=3)):
            _sold_on(day, qty=20, ref=f"ANTERIOR-{index}")

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        assert line.basis["sample_size"] == 3
        assert Decimal(line.basis["avg_demand"]) == Decimal("20")
        assert line.basis["season_fallback"] is True
        assert line.basis["season"] == "mild"
        assert line.basis["current_season"] == "hot"
        assert line.basis["current_season_samples"] == 0

    def test_fallback_disabled_keeps_old_behavior(self, recipe):
        """``season_min_samples = 0`` desliga a troca: a ficha some, como antes."""
        target = _first_day_of_next_month()
        others = [m for m in range(1, 13) if m != target.month]
        _seasons({"hot": [target.month], "mild": others}, season_min_samples=0)
        for index, day in enumerate(_same_weekday_days_before(target, count=3)):
            _sold_on(day, qty=20, ref=f"DESLIGADO-{index}")

        assert [s for s in suggest_for(target) if s.recipe.pk == recipe.pk] == []

    def test_enough_current_season_history_keeps_current(self, recipe):
        """Com amostra suficiente da estação corrente, nada muda."""
        target = _first_day_of_next_month()
        far = (target.month + 5) % 12 + 1  # mês longe da janela e da data
        _seasons({"hot": [m for m in range(1, 13) if m != far], "cold": [far]})
        for index, day in enumerate(_same_weekday_days_before(target, count=3)):
            _sold_on(day, qty=12, ref=f"CORRENTE-{index}")

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        assert line.basis["sample_size"] == 3
        assert "season_fallback" not in line.basis


class TestThinSeasonMerge:
    """A regra da troca, ficha a ficha, com a fórmula do Core trocada por uma falsa.

    Os casos que dependem de QUANTOS dias da janela caem em cada estação não
    são reproduzíveis com datas reais (a janela anda com o calendário), então
    a fórmula falsa devolve a amostra conforme os meses pedidos.
    """

    @pytest.fixture
    def two_recipes(self, recipe):
        broa = Recipe.objects.create(
            ref="broa", name="Broa", output_sku="BROA", batch_size=Decimal("10")
        )
        return recipe, broa

    def _fake_formula(self, samples_by_season):
        from shopman.craftsman.services.queries import Suggestion

        calls = []

        def fake(target_date, output_skus=None, *, season_months=None, **_kwargs):
            calls.append((tuple(output_skus or ()), tuple(season_months or ())))
            key = "current" if season_months == [10, 11, 12, 1, 2, 3] else "previous"
            out = []
            for recipe in Recipe.objects.filter(is_active=True).order_by("name"):
                if output_skus and recipe.output_sku not in output_skus:
                    continue
                size = samples_by_season[key].get(recipe.output_sku, 0)
                if size:
                    out.append(
                        Suggestion(recipe=recipe, quantity=Decimal(size), basis={"sample_size": size})
                    )
            return out

        return fake, calls

    def _run(self, monkeypatch, samples_by_season, *, min_samples=3):
        import shopman.craftsman

        _seasons(
            {"hot": [10, 11, 12, 1, 2, 3], "mild": [4, 5, 9], "cold": [6, 7, 8]},
            season_min_samples=min_samples,
        )
        fake, calls = self._fake_formula(samples_by_season)
        monkeypatch.setattr(shopman.craftsman, "suggest", fake)
        return suggest_for(date(2026, 10, 5)), calls

    def test_thin_recipe_swaps_rich_recipe_stays(self, monkeypatch, two_recipes):
        lines, calls = self._run(
            monkeypatch,
            {"current": {"PAO": 4, "BROA": 1}, "previous": {"PAO": 4, "BROA": 4}},
        )
        by_sku = {line.recipe.output_sku: line for line in lines}

        assert "season_fallback" not in by_sku["PAO"].basis
        assert by_sku["BROA"].basis["season_fallback"] is True
        assert by_sku["BROA"].basis["season"] == "mild"
        assert by_sku["BROA"].basis["current_season_samples"] == 1
        # Só a ficha rala volta à fórmula, e com os meses da estação anterior.
        assert calls[1] == (("BROA",), (4, 5, 9))
        # A ordem é a das fichas (por nome), como a fórmula devolve.
        assert [line.recipe.output_sku for line in lines] == ["BROA", "PAO"]

    def test_previous_season_with_less_history_does_not_replace(self, monkeypatch, two_recipes):
        lines, _calls = self._run(
            monkeypatch,
            {"current": {"PAO": 2, "BROA": 4}, "previous": {"PAO": 1}},
        )
        by_sku = {line.recipe.output_sku: line for line in lines}

        assert by_sku["PAO"].basis["sample_size"] == 2
        assert "season_fallback" not in by_sku["PAO"].basis

    def test_everything_sufficient_skips_second_pass(self, monkeypatch, two_recipes):
        lines, calls = self._run(
            monkeypatch,
            {"current": {"PAO": 3, "BROA": 3}, "previous": {}},
        )
        assert len(calls) == 1
        assert all("season_fallback" not in line.basis for line in lines)
