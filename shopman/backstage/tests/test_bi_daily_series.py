"""A série diária materializada bate com o cálculo ao vivo — e sabe quando não cobre (P3).

O contrato: presença é cobertura, ausência é "ninguém calculou". Igualdade
número a número entre a tabela e a conciliação ao vivo; janela com um dia a
descoberto cai para o vivo em vez de inventar zero; a importação e o worker
recomputam; e o guard da fusão fica persistido para os alarmes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.bi.canonical import CONFLICT_MIN_HISTORICAL
from shopman.backstage.bi.daily_series import earliest_sale_day, materialized, refresh, refresh_all
from shopman.backstage.models import DailySalesFact, HistoricalSale
from shopman.backstage.projections.sales_series import daily_sales
from shopman.backstage.tests.support import historical_batch, install_bi_vocabularies


def _day(days_ago: int):
    return timezone.localdate() - timedelta(days=days_ago)


def _at(days_ago: int, hour: int = 10):
    local = timezone.localtime(timezone.now()).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local - timedelta(days=days_ago)


def _native(days_ago: int, *, total_q: int = 1000, method: str = "pix", cash_received_q: int | None = None):
    payment = {"method": method}
    if cash_received_q is not None:
        payment["cash_received_q"] = cash_received_q
    order = Order.objects.create(
        ref=f"N-{days_ago}-{Order.objects.count()}", channel_ref="pdv", status=Order.Status.COMPLETED,
        total_q=total_q, data={"payment": payment},
    )
    Order.objects.filter(pk=order.pk).update(created_at=_at(days_ago))


def _historical(days_ago: int, *, total_q: int = 700, payment: str = "Dinheiro"):
    HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=HistoricalSale.objects.count() + 1,
        occurred_at=_at(days_ago), total_q=total_q, payment=payment,
    )


@pytest.fixture
def history(db):
    install_bi_vocabularies()
    for offset in range(1, 15):
        if offset % 7 == 0:
            continue  # um dia sem venda por semana: ausência, não zero
        _historical(offset, payment="Dinheiro" if offset % 2 else "PIX")
        _historical(offset, payment="Cartão")
    _native(2, method="cash")
    _native(2, method="pix")
    _native(2, method="mixed", cash_received_q=300)
    for _ in range(CONFLICT_MIN_HISTORICAL + 1):
        _historical(2, payment="PIX")  # o dia nativo apaga tudo isso, e declara


@pytest.mark.django_db
def test_materialized_equals_live_day_by_day(history):
    since, until = _day(14), _day(0)
    live = daily_sales(since, until)  # tabela vazia: calcula ao vivo
    assert DailySalesFact.objects.count() == 0

    written = refresh(since, until)
    assert written == 15  # todos os dias da janela, com ou sem venda
    from_table = materialized(since, until)
    assert from_table is not None
    assert from_table == live
    assert daily_sales(since, until) == live  # o leitor passou a usar a tabela

    row = DailySalesFact.objects.get(date=_day(2))
    assert (row.source, row.orders, row.cash_orders, row.payments_known) == ("shopman", 3, 2, 3)
    # O guard, persistido: as duas do laço + as que só existem para serem apagadas.
    assert row.historical_dropped == CONFLICT_MIN_HISTORICAL + 3
    assert DailySalesFact.objects.get(date=_day(7)).orders == 0  # coberto, sem venda


@pytest.mark.django_db
def test_partial_coverage_falls_back_to_live_instead_of_inventing_zero(history):
    refresh(_day(10), _day(3))
    assert materialized(_day(10), _day(3)) is not None
    assert materialized(_day(14), _day(0)) is None  # falta cobertura nas pontas
    live = daily_sales(_day(14), _day(0))
    assert _day(1) in live and _day(13) in live  # o vivo cobre o que a tabela não cobre


@pytest.mark.django_db
def test_refresh_all_starts_at_the_first_sale_and_forgets_stale_rows(history):
    DailySalesFact.objects.create(date=_day(400), source="yooga", orders=99)  # lixo de outra era
    assert earliest_sale_day() == _day(13)  # o dia 14 caiu no 'sem venda' do fixture
    written = refresh_all()
    assert written == 14
    assert not DailySalesFact.objects.filter(date=_day(400)).exists()
    assert DailySalesFact.objects.order_by("date").first().date == _day(13)


@pytest.mark.django_db
def test_command_recomputes_recent_days_by_default(history, capsys):
    call_command("refresh_bi_daily_series")
    assert DailySalesFact.objects.count() == 3
    assert set(DailySalesFact.objects.values_list("date", flat=True)) == {_day(0), _day(1), _day(2)}
    assert "3 dias" in capsys.readouterr().out
    call_command("refresh_bi_daily_series", "--all")
    assert DailySalesFact.objects.count() == 14


@pytest.mark.django_db
def test_maintenance_worker_runs_the_refresh():
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    assert "refresh_bi_daily_series" in MAINTENANCE_COMMANDS
