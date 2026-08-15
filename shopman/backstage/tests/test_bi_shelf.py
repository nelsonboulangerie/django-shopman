"""Sobra e falta no explorador — as duas caras da decisão da fornada.

A pergunta do dono: está sobrando ou faltando pão, e em que dias. Sobra vem da
contagem do fechamento (quem conta é o operador); falta vem do ledger (quando a
prateleira zerou de tanto vender).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.stockman.models import Move, Position, Quant

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore

pytestmark = pytest.mark.django_db


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def shop_9_to_18(db):
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


def _shelf_day(quant, day: date, *, received: int, sold: int, soldout_hour: int):
    Move.objects.create(
        quant=quant, delta=Decimal(received), kind=Move.Kind.MAKE,
        reason="fornada", timestamp=_at(day, 9),
    )
    Move.objects.create(
        quant=quant, delta=Decimal(-sold), kind=Move.Kind.SELL,
        reason="venda", timestamp=_at(day, soldout_hour),
    )


class TestShelfMetrics:
    def test_soldout_days_counts_only_days_that_ran_out(self, vitrine, shop_9_to_18):
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        _shelf_day(quant, today - timedelta(days=2), received=10, sold=10, soldout_hour=11)
        _shelf_day(quant, today - timedelta(days=1), received=10, sold=4, soldout_hour=11)

        report = build_bi_explore(
            metric="soldout_days", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert [(row.key, row.value) for row in report.rows] == [("PAO", 1.0)]

    def test_hours_without_stock_counts_until_closing(self, vitrine, shop_9_to_18):
        """Acabou às 11h numa loja que fecha às 18h: sete horas sem produto."""
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        _shelf_day(quant, today - timedelta(days=1), received=10, sold=10, soldout_hour=11)

        report = build_bi_explore(
            metric="hours_without_stock", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert [(row.key, row.value) for row in report.rows] == [("PAO", 7.0)]

    def test_selling_out_at_closing_time_costs_nothing(self, vitrine, shop_9_to_18):
        """Vendeu o último no fim do expediente: acertou a quantidade."""
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        _shelf_day(quant, today - timedelta(days=1), received=10, sold=10, soldout_hour=18)

        report = build_bi_explore(
            metric="hours_without_stock", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert [row.value for row in report.rows] == [0.0]

    def test_leftover_comes_from_the_closing_count(self, vitrine, shop_9_to_18):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        _shelf_day(quant, yesterday, received=30, sold=20, soldout_hour=11)
        DayClosing.objects.create(
            date=yesterday,
            closed_by=get_user_model().objects.create_user("marina"),
            data={"items": [{"sku": "PAO", "qty_remaining": 10}]},
        )

        report = build_bi_explore(
            metric="leftover", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert [(row.key, row.value) for row in report.rows] == [("PAO", 10.0)]

    def test_day_without_closing_is_absent_not_zero(self, vitrine, shop_9_to_18):
        """Sem fechamento não há contagem — e ausência não é sobra zero."""
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        _shelf_day(quant, today - timedelta(days=1), received=30, sold=20, soldout_hour=11)

        report = build_bi_explore(
            metric="leftover", by="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert report.rows == ()

    def test_shelf_metrics_cross_by_weekday(self, vitrine, shop_9_to_18):
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        day = today - timedelta(days=1)
        _shelf_day(quant, day, received=10, sold=10, soldout_hour=11)

        report = build_bi_explore(
            metric="soldout_days", by="weekday", by2="sku",
            date_from=today - timedelta(days=3), date_to=today,
        )

        assert [(row.key, row.key2, row.value) for row in report.rows] == [
            (str(day.weekday()), "PAO", 1.0)
        ]


class TestCyclicDimensions:
    def test_month_of_year_is_offered_for_revenue(self):
        report = build_bi_explore(metric="revenue", by="month_of_year")

        assert report.dimension_label == "Mês do ano"

    def test_cyclic_dimensions_come_out_in_natural_order(self, vitrine, shop_9_to_18):
        """Curva ordenada por valor deixa de ser curva."""
        today = timezone.localdate()
        quant = Quant.objects.create(sku="PAO", position=vitrine)
        for offset, sold in ((3, 10), (2, 4), (1, 7)):
            _shelf_day(
                quant, today - timedelta(days=offset),
                received=sold, sold=sold, soldout_hour=11,
            )

        report = build_bi_explore(
            metric="soldout_days", by="time",
            date_from=today - timedelta(days=4), date_to=today,
        )

        assert [row.key for row in report.rows] == sorted(row.key for row in report.rows)

    def test_grammar_still_rejects_what_it_does_not_know(self):
        with pytest.raises(ExploreError) as exc:
            build_bi_explore(metric="leftover", by="channel")

        assert "não vale" in str(exc.value)
