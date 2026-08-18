"""Reconstrução do dia na prateleira a partir do ledger.

A pergunta de negócio por trás: a que horas o produto chegou para venda e a
que horas acabou. O ledger de ``Move`` é a única fonte que carrega o instante
de cada entrada e saída, então é dele que a resposta sai.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.services.queries import StockQueries

pytestmark = pytest.mark.django_db


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def warehouse(db):
    return Position.objects.create(ref="deposito", name="Depósito", is_saleable=False)


def _at(day: date, hour: int, minute: int = 0):
    tz = timezone.get_current_timezone()
    return timezone.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def _move(quant: Quant, *, delta: str, when, kind: str | None = None) -> None:
    """Movimento com instante declarado (o ledger é append-only).

    Entrada default é produção; saída default é venda — que é o caso comum da
    prateleira. Perda e ajuste são declarados explicitamente onde importam.
    """
    amount = Decimal(delta)
    if kind is None:
        kind = Move.Kind.MAKE if amount > 0 else Move.Kind.SELL
    Move.objects.create(
        quant=quant, delta=amount, kind=kind, reason="teste", timestamp=when,
    )


@pytest.fixture
def quant(vitrine):
    return Quant.objects.create(sku="PAO", position=vitrine)


class TestShelfDay:
    def test_arrival_and_soldout_times_come_from_the_ledger(self, quant):
        day = timezone.localdate()
        _move(quant, delta="10", when=_at(day, 6, 30))   # saiu do forno
        _move(quant, delta="-4", when=_at(day, 8))
        _move(quant, delta="-6", when=_at(day, 10, 15))  # acabou

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.first_in_at == _at(day, 6, 30)
        assert shelf.soldout_at == _at(day, 10, 15)
        assert shelf.received == Decimal("10")
        assert shelf.sold == Decimal("10")

    def test_restock_undoes_the_soldout(self, quant):
        """Zerou às 10h e recebeu fornada às 11h: não esgotou o dia."""
        day = timezone.localdate()
        _move(quant, delta="5", when=_at(day, 6))
        _move(quant, delta="-5", when=_at(day, 10))      # zera...
        _move(quant, delta="8", when=_at(day, 11))       # ...mas repõe
        _move(quant, delta="-3", when=_at(day, 12))

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.soldout_at is None
        assert shelf.first_in_at == _at(day, 6)

    def test_restock_then_soldout_again_reports_the_last_one(self, quant):
        """O que interessa é a hora a partir da qual ficou sem produto."""
        day = timezone.localdate()
        _move(quant, delta="5", when=_at(day, 6))
        _move(quant, delta="-5", when=_at(day, 10))
        _move(quant, delta="4", when=_at(day, 11))
        _move(quant, delta="-4", when=_at(day, 15, 30))

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.soldout_at == _at(day, 15, 30)

    def test_day_that_ends_with_stock_never_sold_out(self, quant):
        day = timezone.localdate()
        _move(quant, delta="20", when=_at(day, 6))
        _move(quant, delta="-3", when=_at(day, 9))

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.soldout_at is None
        assert shelf.had_stock is True

    def test_discard_zeroes_the_shelf_without_being_a_soldout(self, quant):
        """Sobrou e foi descartado: a prateleira zera, mas isso é o OPOSTO de falta.

        Sem a distinção, o descarte do fechamento marcaria esgotamento todo dia
        e a sugestão passaria a extrapolar demanda que ninguém procurou.
        """
        day = timezone.localdate()
        _move(quant, delta="30", when=_at(day, 6))
        _move(quant, delta="-20", when=_at(day, 11))
        _move(quant, delta="-10", when=_at(day, 18), kind=Move.Kind.WASTE)

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.soldout_at is None
        assert shelf.sold == Decimal("20")
        assert shelf.discarded == Decimal("10")
        assert shelf.closing == Decimal("0")

    def test_day_without_any_stock_is_not_a_soldout(self, quant):
        """Produto que nunca existiu no dia não 'esgotou' — não teve o que vender."""
        day = timezone.localdate()

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.soldout_at is None
        assert shelf.first_in_at is None
        assert shelf.had_stock is False


class TestOpeningBalanceAndScope:
    def test_opening_balance_carries_from_before_the_window(self, quant):
        """Sobra de ontem conta como saldo de abertura de hoje."""
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        _move(quant, delta="10", when=_at(yesterday, 6))
        _move(quant, delta="-4", when=_at(yesterday, 9))
        _move(quant, delta="-6", when=_at(today, 8))  # consome a sobra

        shelf = StockQueries.shelf_history(["PAO"], since=today, until=today)["PAO"][today]

        assert shelf.opening == Decimal("6")
        assert shelf.soldout_at == _at(today, 8)

    def test_balance_rolls_across_days_in_the_window(self, quant):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        _move(quant, delta="10", when=_at(yesterday, 6))
        _move(quant, delta="-2", when=_at(yesterday, 9))

        days = StockQueries.shelf_history(["PAO"], since=yesterday, until=today)["PAO"]

        assert days[yesterday].opening == Decimal("0")
        assert days[today].opening == Decimal("8")

    def test_non_saleable_position_is_out_of_scope(self, warehouse, quant):
        """Depósito não é prateleira: a pergunta é o que o cliente encontrava."""
        day = timezone.localdate()
        stock = Quant.objects.create(sku="PAO", position=warehouse)
        _move(stock, delta="50", when=_at(day, 5))
        _move(quant, delta="3", when=_at(day, 6))
        _move(quant, delta="-3", when=_at(day, 7))

        shelf = StockQueries.shelf_history(["PAO"], since=day, until=day)["PAO"][day]

        assert shelf.received == Decimal("3")
        assert shelf.soldout_at == _at(day, 7)

    def test_planned_quant_is_out_of_scope(self, vitrine):
        """Saldo planejado é promessa, não prateleira."""
        day = timezone.localdate()
        planejado = Quant.objects.create(
            sku="PAO", position=vitrine, target_date=day + timedelta(days=1)
        )
        _move(planejado, delta="30", when=_at(day, 5))

        history = StockQueries.shelf_history(["PAO"], since=day, until=day)

        assert history == {}

    def test_many_skus_in_one_pass(self, vitrine):
        day = timezone.localdate()
        pao = Quant.objects.create(sku="PAO", position=vitrine)
        croissant = Quant.objects.create(sku="CROISSANT", position=vitrine)
        _move(pao, delta="5", when=_at(day, 6))
        _move(pao, delta="-5", when=_at(day, 9))
        _move(croissant, delta="5", when=_at(day, 6))

        history = StockQueries.shelf_history(["PAO", "CROISSANT"], since=day, until=day)

        assert history["PAO"][day].soldout_at == _at(day, 9)
        assert history["CROISSANT"][day].soldout_at is None
