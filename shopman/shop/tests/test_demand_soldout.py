"""O dia que esgotou não conta como dia fraco.

Vender 20 pães e fechar a prateleira às 10h não significa que a procura era 20
— significa que só havia 20. Sem corrigir isso, o produto que acaba cedo toda
semana ensina à sugestão que aquele dia vende pouco, ela manda produzir pouco,
e a falta se perpetua sozinha.

A fórmula já sabia extrapolar (``DailyDemand.soldout_at``); faltava alguém
preencher o campo. Quem sabe a hora é o ledger de estoque.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Move, Position, Quant

from shopman.shop.adapters.demand import LedgerAwareDemandBackend
from shopman.shop.services.production import selling_window_for, suggest_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


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


@pytest.fixture
def shop_open_9_to_18(db):
    from shopman.shop.models import Shop

    shop = Shop.objects.create(name="Nelson")
    shop.opening_hours = {
        name: {"open": "09:00", "close": "18:00"}
        for name in (
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        )
    }
    shop.save()
    return shop


def _at(day: date, hour: int, minute: int = 0):
    tz = timezone.get_current_timezone()
    return timezone.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def _sold_out_day(day: date, *, quant: Quant, qty: int, at_hour: int, ref: str) -> None:
    """Um dia em que o produto chegou, vendeu tudo e acabou às ``at_hour``."""
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="completed", total_q=qty * 100
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=qty,
        unit_price_q=100, line_total_q=qty * 100,
    )
    Order.objects.filter(pk=order.pk).update(created_at=_at(day, at_hour))
    Move.objects.create(
        quant=quant, delta=Decimal(qty), kind=Move.Kind.MAKE,
        reason="fornada", timestamp=_at(day, 9),
    )
    Move.objects.create(
        quant=quant, delta=Decimal(-qty), kind=Move.Kind.SELL,
        reason="venda", timestamp=_at(day, at_hour),
    )


def _same_weekday_before(anchor: date, *, count: int) -> list[date]:
    today = timezone.localdate()
    out, day = [], anchor - timedelta(days=7)
    while len(out) < count:
        if day < today:
            out.append(day)
        day -= timedelta(days=7)
    return out


class TestSoldoutReachesTheFormula:
    def test_backend_fills_soldout_from_the_ledger(self, vitrine, shop_open_9_to_18):
        target = timezone.localdate() + timedelta(days=1)
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        days = _same_weekday_before(target, count=2)
        for index, day in enumerate(days):
            _sold_out_day(day, quant=quant, qty=20, at_hour=11, ref=f"ESGOTOU-{index}")

        rows = LedgerAwareDemandBackend().history("PAO", days=28, target_date=target)

        assert {row.date for row in rows} == set(days)
        for row in rows:
            assert row.sold == Decimal("20")
            assert row.soldout_at == time(11, 0)

    def test_soldout_day_raises_the_suggestion(
        self, recipe, vitrine, shop_open_9_to_18
    ):
        """Mesma venda observada, sugestão maior — porque a procura era maior."""
        target = timezone.localdate() + timedelta(days=1)
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        for index, day in enumerate(_same_weekday_before(target, count=2)):
            _sold_out_day(day, quant=quant, qty=20, at_hour=11, ref=f"ESGOTOU-{index}")

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        # Vendeu 20 em 2h de um expediente de 9h → taxa de 10/h. A extrapolação
        # é limitada ao dobro do observado, então a demanda estimada é 40, e a
        # margem de 20% leva a 48. Sem a correção, a conta partiria de 20 e
        # pararia em 24 — metade do pão necessário.
        assert line.basis["soldout_days"] == 2
        assert Decimal(line.basis["avg_demand"]) == Decimal("40")
        assert line.quantity == Decimal("48")

    def test_day_with_leftovers_is_not_extrapolated(
        self, recipe, vitrine, shop_open_9_to_18
    ):
        """Sobrou pão: o que vendeu É a procura, e nada é inflado."""
        target = timezone.localdate() + timedelta(days=1)
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        for index, day in enumerate(_same_weekday_before(target, count=2)):
            ref = f"SOBROU-{index}"
            order = Order.objects.create(
                ref=ref, channel_ref="web", status="completed", total_q=2000
            )
            OrderItem.objects.create(
                order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=20,
                unit_price_q=100, line_total_q=2000,
            )
            Order.objects.filter(pk=order.pk).update(created_at=_at(day, 11))
            Move.objects.create(
                quant=quant, delta=Decimal("30"), kind=Move.Kind.MAKE,
                reason="fornada", timestamp=_at(day, 9),
            )
            Move.objects.create(
                quant=quant, delta=Decimal("-20"), kind=Move.Kind.SELL,
                reason="venda", timestamp=_at(day, 11),
            )
            Move.objects.create(
                quant=quant, delta=Decimal("-10"), kind=Move.Kind.WASTE,
                reason=f"perda_vencido:{day}", timestamp=_at(day, 18),
            )

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        assert line.basis["soldout_days"] == 0
        assert Decimal(line.basis["avg_demand"]) == Decimal("20")


class TestSellingWindowHonesty:
    def test_window_comes_from_the_declared_hours(self, shop_open_9_to_18):
        assert selling_window_for(timezone.localdate()) == (time(9, 0), time(18, 0))

    def test_without_declared_hours_there_is_no_window(self, db):
        assert selling_window_for(timezone.localdate()) is None

    def test_without_window_the_formula_counts_what_it_saw(self, recipe, vitrine):
        """Sem horário configurado, dia esgotado conta o vendido — sem inventar.

        Extrapolar exigiria supor um expediente que ninguém declarou.
        """
        target = timezone.localdate() + timedelta(days=1)
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        for index, day in enumerate(_same_weekday_before(target, count=2)):
            _sold_out_day(day, quant=quant, qty=20, at_hour=11, ref=f"ESGOTOU-{index}")

        line = next(s for s in suggest_for(target) if s.recipe.pk == recipe.pk)

        assert line.basis["soldout_days"] == 2  # o fato é declarado…
        assert Decimal(line.basis["avg_demand"]) == Decimal("20")  # …mas não vira conta
