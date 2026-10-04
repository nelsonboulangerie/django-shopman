"""B.I. "Sobrou ou faltou?" (V4-BI, prévia ``bi-sobra4``).

Cobre a perm fina, o veredito por produto (faltou / sobrou / na medida), a hora
em que acabou (o vendido acumulado alcança o feito), a estimativa de vendas
perdidas pela mesma régua da sugestão do Craftsman, o típico do mesmo dia da
semana e os lotes e vendas por hora que o "Ver lotes e vendas" abre.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.bi_over_short import build_bi_over_short

pytestmark = pytest.mark.django_db

EVERY_DAY = {
    day: {"open": "07:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture
def shop(db):
    from shopman.shop.models import Shop

    shop, _ = Shop.objects.get_or_create(name="Loja B.I.")
    shop.opening_hours = EVERY_DAY
    shop.save()
    return shop


@pytest.fixture
def day() -> date:
    return timezone.localdate() - timedelta(days=1)


def _recipe(sku: str, name: str) -> Recipe:
    Product.objects.get_or_create(sku=sku, defaults={"name": name, "base_price_q": 1000})
    return Recipe.objects.create(ref=f"{sku.lower()}-v1", name=name, output_sku=sku, batch_size=Decimal("10"))


def _lot(recipe: Recipe, day: date, qty: int, at: time = time(6, 30)) -> WorkOrder:
    wo = WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal(qty),
        finished=Decimal(qty),
        status=WorkOrder.Status.FINISHED,
        target_date=day,
    )
    WorkOrder.objects.filter(pk=wo.pk).update(
        finished_at=timezone.make_aware(datetime.combine(day, at)),
    )
    wo.refresh_from_db()
    return wo


_seq = iter(range(1, 10_000))


def _sale(day: date, at: time, sku: str, qty: int) -> None:
    ref = f"OS-{next(_seq)}"
    order = Order.objects.create(ref=ref, channel_ref="pdv", status=Order.Status.COMPLETED, total_q=qty * 1000)
    OrderItem.objects.create(
        order=order, line_id="l1", sku=sku, name=sku, qty=Decimal(qty), unit_price_q=1000, line_total_q=qty * 1000
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.make_aware(datetime.combine(day, at)))


def _row(report, sku):
    return next(row for row in report.rows if row.sku == sku)


# ── Gate ─────────────────────────────────────────────────────────────────────


def test_endpoint_requires_view_bi(client):
    bare = User.objects.create_user("bare-over-short", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-bi-over-short")).status_code == 403


def test_endpoint_answers_for_viewer(client, shop, day):
    viewer = User.objects.create_user("bi-over-short", password="pw", is_staff=True)
    viewer.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi")
    )
    client.force_login(viewer)
    response = client.get(reverse("api-backstage-bi-over-short"), {"day": day.isoformat()})
    assert response.status_code == 200
    assert response.json()["bi"]["day"] == day.isoformat()


# ── Veredito ─────────────────────────────────────────────────────────────────


def test_short_when_it_sells_out_early_with_lost_estimate(shop, day):
    croissant = _recipe("CRO", "Croissant")
    _lot(croissant, day, 20, time(6, 30))
    _lot(croissant, day, 20, time(8, 20))
    # 40 vendidos em 3h30 (07:00 → 10:30): acabou às 10:30.
    _sale(day, time(8, 0), "CRO", 15)
    _sale(day, time(9, 10), "CRO", 15)
    _sale(day, time(10, 30), "CRO", 10)

    report = build_bi_over_short(day=day)
    row = _row(report, "CRO")

    assert row.verdict == "short"
    assert row.made == "40" and row.sold == "40" and row.leftover == "0"
    assert row.soldout_at == "10:30"
    # Ritmo 40 em 210 min, expediente de 660 min → 125,7; teto 2× = 80; perdidas = 40.
    assert row.lost_estimate == "40"
    assert [lot.finished_at for lot in row.lots] == ["06:30", "08:20"]
    hours = {hour.hour: hour for hour in row.sales_by_hour}
    assert hours[8].sold == "15" and hours[10].sold == "10"
    # A estimativa mora nas horas depois que acabou, e soma a perda.
    assert hours[9].estimated_lost == "0"
    assert hours[17].estimated_lost == "5"
    # Arredondada hora a hora, a soma fica perto da perda (nunca inventa o dobro).
    assert abs(sum(int(h.estimated_lost) for h in row.sales_by_hour) - 40) <= 3
    assert report.summary.short == 1


def test_right_when_it_sells_out_in_the_last_hour(shop, day):
    shokupan = _recipe("FORMA", "Shokupan")
    _lot(shokupan, day, 18)
    _sale(day, time(9, 0), "FORMA", 10)
    _sale(day, time(17, 20), "FORMA", 8)

    row = _row(build_bi_over_short(day=day), "FORMA")
    assert row.verdict == "right"
    assert row.soldout_at == "17:20"
    assert row.lost_estimate == ""


def test_over_and_right_by_leftover(shop, day):
    baguete = _recipe("BGT", "Baguete")
    pain = _recipe("PCHOC", "Pain au Chocolat")
    _lot(baguete, day, 60)
    _lot(pain, day, 36)
    _sale(day, time(11, 0), "BGT", 48)
    _sale(day, time(12, 0), "PCHOC", 34)

    report = build_bi_over_short(day=day)
    assert _row(report, "BGT").verdict == "over"
    assert _row(report, "BGT").leftover == "12"
    assert _row(report, "PCHOC").verdict == "right"  # sobrou 2: na medida
    assert report.summary.over == 1 and report.summary.right == 1
    assert report.summary.leftover_units == "14"
    # Ordem da leitura: sobrou antes de na medida.
    assert [row.sku for row in report.rows] == ["BGT", "PCHOC"]


def test_typical_and_history_from_the_same_weekday(shop, day):
    croissant = _recipe("CRO", "Croissant")
    _lot(croissant, day, 30)
    _sale(day, time(15, 0), "CRO", 20)
    for week, sold in ((1, 41), (2, 40), (3, 30)):
        past = day - timedelta(days=7 * week)
        _lot(croissant, past, 40)
        _sale(past, time(9, 0) if sold >= 40 else time(12, 0), "CRO", sold)

    report = build_bi_over_short(day=day)
    row = _row(report, "CRO")
    assert len(report.compare_days) == 4
    assert report.compare_days[0] == (day - timedelta(days=7)).isoformat()
    # Produto feito em 3 dos 4 dias: média só onde foi feito.
    assert row.typical_sold == "37"
    assert row.history == ("short", "short", "over")
    assert report.typical.days == 4


def test_navigation_and_plan_day(shop, day):
    report = build_bi_over_short(day=day)
    assert report.next_day == ""  # o seguinte seria hoje: não se lê dia em curso
    assert report.previous_day == (day - timedelta(days=1)).isoformat()
    assert report.plan_day == (day + timedelta(days=7)).isoformat()
    assert report.opens_at == "07:00" and report.closes_at == "18:00"


def test_default_day_is_the_last_open_day(shop):
    report = build_bi_over_short()
    assert report.day == (timezone.localdate() - timedelta(days=1)).isoformat()


def test_selling_well_beyond_made_is_not_a_sellout(shop, day):
    # Havia estoque de antes: o feito "acabou" às 9h, mas a venda seguiu o dia todo.
    ciabatta = _recipe("CI", "Ciabatta")
    _lot(ciabatta, day, 10)
    _sale(day, time(9, 0), "CI", 10)
    _sale(day, time(15, 0), "CI", 8)

    row = _row(build_bi_over_short(day=day), "CI")
    assert row.soldout_at == ""
    assert row.verdict == "right"
    assert row.lost_estimate == ""


def test_lot_with_nothing_made_stays_out(shop, day):
    wo = _lot(_recipe("CRO", "Croissant"), day, 10)
    WorkOrder.objects.filter(pk=wo.pk).update(finished=Decimal(0))  # lote fechado sem nada pronto
    assert build_bi_over_short(day=day).rows == ()
