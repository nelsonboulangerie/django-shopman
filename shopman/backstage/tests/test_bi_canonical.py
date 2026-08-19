"""A camada canônica: uma venda é uma venda, e a conciliação tem UM dono (P2).

Cobre a regra "o dia nativo vence" declarada em vez de muda (``source_conflicts``),
a origem lida do campo (seed nunca vira yooga), o de-para de produto
confirmado atravessando as linhas até o ranking e o explorador, a forma de
pagamento do histórico traduzida pelo vocabulário (desconhecida = declarada),
e o cancelado nativo contado à parte.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.bi.canonical import (
    CONFLICT_MAX_NATIVE,
    CONFLICT_MIN_HISTORICAL,
    read_sales,
)
from shopman.backstage.models import (
    AliasStatus,
    HistoricalSale,
    HistoricalSaleItem,
    ProductAlias,
)
from shopman.backstage.projections.bi_explore import build_bi_explore
from shopman.backstage.projections.bi_sales import build_bi_sales
from shopman.backstage.tests.support import historical_batch, install_bi_vocabularies


def _at(days_ago: int, hour: int = 10):
    local = timezone.localtime(timezone.now()).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local - timedelta(days=days_ago)


def _native(days_ago: int, *, total_q: int = 1000, status=Order.Status.COMPLETED, ref: str | None = None,
            payment: dict | None = None, items=()):
    order = Order.objects.create(
        ref=ref or f"N-{days_ago}-{Order.objects.count()}", channel_ref="pdv", status=status,
        total_q=total_q, data={"payment": payment or {"method": "pix"}},
    )
    Order.objects.filter(pk=order.pk).update(created_at=_at(days_ago))
    for sku, name, qty in items:
        OrderItem.objects.create(order=order, line_id=f"{sku}-{qty}", sku=sku, name=name,
                                 qty=Decimal(qty), unit_price_q=100, line_total_q=100 * qty)
    return order


def _historical(days_ago: int, *, source: str = "yooga", total_q: int = 700, payment: str = "Dinheiro",
                items=(), external_id: int | None = None):
    sale = HistoricalSale.objects.create(
        batch=historical_batch(source), source=source,
        external_id=external_id or (HistoricalSale.objects.count() + 1),
        occurred_at=_at(days_ago), total_q=total_q, payment=payment,
    )
    for seq, (sku, name, category, qty) in enumerate(items, start=1):
        HistoricalSaleItem.objects.create(
            sale=sale, seq=seq, product_name=name, sku=sku, category=category,
            qty=Decimal(qty), unit_price_q=100, line_total_q=100 * qty,
        )
    return sale


# ── Conciliação ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_native_day_wins_and_the_loss_is_declared_when_it_matters():
    # Dia 3: um pedido de teste apaga muito histórico → aviso.
    _native(3)
    for n in range(CONFLICT_MIN_HISTORICAL + 1):
        _historical(3, external_id=1000 + n)
    # Dia 5: só histórico → entra, com a origem do campo.
    _historical(5, source="seed", external_id=5000)
    # Dia 7: nativo com volume e pouco histórico descartado → sem aviso.
    for _ in range(CONFLICT_MAX_NATIVE):
        _native(7)
    _historical(7, external_id=7000)

    window = read_sales(_at(8).date(), _at(0).date())

    days = {sale.day: sale.source for sale in window.sales}
    assert days[_at(3).date()] == "shopman"
    assert days[_at(5).date()] == "seed"
    assert window.historical_days == {_at(5).date(): "seed"}
    assert window.sources == ("shopman", "seed")
    assert [(c.day, c.native_orders, c.historical_dropped, c.source) for c in window.source_conflicts] == [
        (_at(3).date(), 1, CONFLICT_MIN_HISTORICAL + 1, "yooga"),
    ]


@pytest.mark.django_db
def test_cancelled_native_is_counted_apart_and_never_a_sale():
    _native(1)
    _native(1, status=Order.Status.CANCELLED)
    window = read_sales(_at(2).date(), _at(0).date())
    assert len(window.sales) == 1
    assert window.cancelled_native == 1
    assert build_bi_sales(date_from=_at(2).date(), date_to=_at(0).date()).cancelled_total == 1


@pytest.mark.django_db
def test_sales_report_carries_sources_and_conflicts():
    _native(3)
    for n in range(CONFLICT_MIN_HISTORICAL + 1):
        _historical(3, external_id=1000 + n)
    _historical(5, external_id=5000)
    report = build_bi_sales(date_from=_at(6).date(), date_to=_at(0).date())
    assert report.sources == ("shopman", "yooga")
    assert [c.date for c in report.source_conflicts] == [_at(3).date().isoformat()]
    assert report.source_conflicts[0].historical_dropped == CONFLICT_MIN_HISTORICAL + 1


# ── Origem do campo, nunca literal ──────────────────────────────────────────


@pytest.mark.django_db
def test_seeded_history_is_labelled_seed_in_every_reader():
    _historical(2, source="seed", items=(("MD", "Madeleine", "Confeitaria", 2),))
    report = build_bi_explore(metric="qty_sold", by="source", date_from=_at(3).date(), date_to=_at(0).date())
    assert {row.key for row in report.rows} == {"seed"}


# ── De-para de produto atravessa as linhas ──────────────────────────────────


@pytest.mark.django_db
def test_confirmed_product_alias_joins_history_and_native_in_the_ranking():
    croissant = Product.objects.create(sku="CROISSANT", name="Croissant")
    _native(1, items=(("CROISSANT", "Croissant", 2),))
    _historical(4, items=(("CT", "Croissant Trad.", "Pães Finos", 3),))
    alias = ProductAlias.objects.create(source="yooga", external_sku="CT", external_name="Croissant Trad.",
                                        product=croissant)  # proposto: ainda não traduz

    before = build_bi_sales(date_from=_at(5).date(), date_to=_at(0).date())
    assert {row.sku for row in before.top_skus} == {"CROISSANT", "CT"}

    alias.status = AliasStatus.CONFIRMED
    alias.save()
    after = build_bi_sales(date_from=_at(5).date(), date_to=_at(0).date())
    assert [(row.sku, row.qty) for row in after.top_skus] == [("CROISSANT", "5")]

    explore = build_bi_explore(metric="qty_sold", by="sku", date_from=_at(5).date(), date_to=_at(0).date())
    assert {row.key: row.value for row in explore.rows} == {"CROISSANT": 5.0}


@pytest.mark.django_db
def test_line_without_sku_keeps_its_name_as_key():
    _historical(2, items=(("", "Produto Extinto", "Mercearia", 1),))
    window = read_sales(_at(3).date(), _at(0).date())
    (line,) = window.lines()
    assert line.product_key == "nome:Produto Extinto"


# ── Forma de pagamento do histórico ─────────────────────────────────────────


@pytest.mark.django_db
def test_historical_payment_is_translated_by_the_confirmed_vocabulary_or_declared_unknown():
    _historical(2, payment="PIX, DINHEIRO", external_id=1)
    _historical(2, payment="Fiado do seu Zé", external_id=2)
    _historical(2, payment="", external_id=3)

    without = {sale.ref: sale for sale in read_sales(_at(3).date(), _at(0).date()).sales}
    assert without["yooga:1"].payment_known is False  # sem vocabulário, nada é reconhecido
    assert without["yooga:1"].is_cash is False

    install_bi_vocabularies()
    with_vocab = {sale.ref: sale for sale in read_sales(_at(3).date(), _at(0).date()).sales}
    mixed = with_vocab["yooga:1"]
    assert mixed.payments[0].method == "pix"  # a primeira forma que casa dá o balde
    assert mixed.is_cash is True  # …mas houve dinheiro em alguma parcela
    assert mixed.payment_known is True
    unknown = with_vocab["yooga:2"]
    assert unknown.payments[0].method == "raw:fiado do seu zé"
    assert unknown.payments[0].label == "Fiado do seu Zé"
    assert unknown.payment_known is False
    assert with_vocab["yooga:3"].payment_known is False
    assert with_vocab["yooga:3"].payments[0].method == "external"


@pytest.mark.django_db
def test_native_payment_split_and_change_travel_with_the_sale():
    _native(1, total_q=1000, payment={
        "method": "mixed", "cash_received_q": 600, "change_q": 100,
        "tenders": [{"method": "cash", "amount_q": 500}, {"method": "pix", "amount_q": 500}],
    })
    (sale,) = read_sales(_at(2).date(), _at(0).date()).sales
    assert [(p.method, p.amount_q) for p in sale.payments] == [("cash", 500), ("pix", 500)]
    assert sale.is_cash is True and sale.payment_known is True and sale.change_q == 100
