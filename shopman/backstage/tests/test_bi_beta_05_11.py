"""Achados do beta de 05/11/2026 no B.I. (frente "bi").

Cada teste trava um defeito com o id do achado: dia em curso comparado com um dia
inteiro (ge:BI-06), período futuro colado na URL (ge:BI-14), preparo em gramas
somado com a peça na leitura de produção (ge:BI-12).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Order
from shopman.stockman.models import Position

from shopman.backstage.projections import bi_sales
from shopman.backstage.projections.bi_production import build_bi_production
from shopman.backstage.services.production import apply_finish

pytestmark = pytest.mark.django_db


def _at(day, hour):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)), timezone.get_current_timezone())


def _sale(ref, at, total_q=1000):
    order = Order.objects.create(ref=ref, channel_ref="web", status=Order.Status.COMPLETED, total_q=total_q)
    Order.objects.filter(pk=order.pk).update(created_at=at)
    return order


def test_today_is_compared_with_the_base_day_up_to_the_same_hour(monkeypatch):
    """ge:BI-06: às 12:00 o hoje não se compara com o dia inteiro de ontem."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    _sale("BI06-MORNING", _at(yesterday, 8))
    _sale("BI06-EVENING", _at(yesterday, 20), total_q=9000)
    _sale("BI06-TODAY", _at(today, 9))
    noon = _at(today, 12)
    monkeypatch.setattr(bi_sales, "timezone", SimpleNamespace(localtime=lambda *args: noon))

    report = bi_sales.build_bi_sales(date_from=today, date_to=today)

    assert report.previous.date_from == yesterday.isoformat()
    assert report.previous.orders_total == 1
    assert report.previous.revenue_total_q == 1000
    assert report.previous.partial_until == "12:00"

    whole = bi_sales.build_bi_sales(date_from=yesterday, date_to=yesterday)
    assert whole.previous.partial_until == ""


def test_future_window_falls_back_to_the_last_day_read():
    """ge:BI-14: janeiro do ano que vem não é lido como "nenhuma venda no período"."""
    today = timezone.localdate()
    report = bi_sales.build_bi_sales(date_from=today + timedelta(days=60), date_to=today + timedelta(days=90))
    assert report.date_to == today.isoformat()
    assert report.date_from == today.isoformat()


def _finish(recipe, quantity):
    wo = craft.plan(recipe, Decimal(quantity), date=timezone.localdate(), position_ref="forno")
    craft.start(wo, quantity=Decimal(quantity), position_ref="forno", expected_rev=0)
    apply_finish(
        work_order_id=wo.pk,
        quantity=quantity,
        actor="test",
        expected_rev=wo.rev,
        idempotency_key=f"bi12-{recipe.ref}",
    )


def test_production_reading_counts_pieces_not_grams_of_preparation():
    """ge:BI-12: massa em gramas não entra na soma de peças do dia."""
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja B.I.")
    Position.objects.create(ref="loja", name="Loja", is_saleable=True)
    Position.objects.create(ref="forno", name="Forno", kind="oven", is_default=True)
    piece = Recipe.objects.create(ref="bi12-pao", name="Pão", output_sku="BI12-PAO", batch_size=Decimal("10"))
    dough = Recipe.objects.create(
        ref="bi12-massa",
        name="Massa",
        output_sku="BI12-MASSA",
        batch_size=Decimal("1000"),
        meta={"output_unit": "g"},
    )
    _finish(piece, "40")
    _finish(dough, "18000")

    report = build_bi_production()

    assert report.batches_finished == 1
    today = next(day for day in report.days if day.date == timezone.localdate().isoformat())
    assert Decimal(str(today.finished)) == Decimal("40")
