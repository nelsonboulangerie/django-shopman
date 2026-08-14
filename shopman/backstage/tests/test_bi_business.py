"""B.I. de vendas, caixa e clientes (ADR-021, BI-PLAN F4).

Cobre a perm fina ``backstage.view_bi`` nos três endpoints e o cálculo dos
agregados: série de vendas (cancelado fora do faturamento, contado à parte),
quebra de caixa por operador com ``closings_missing`` declarado, e a
distribuição RFM lida do ``CustomerInsight`` (o B.I. só lê, nunca recalcula).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import CashMovement, CashShift, DayClosing, POSTerminal
from shopman.backstage.projections.bi_cash import build_bi_cash
from shopman.backstage.projections.bi_customers import build_bi_customers
from shopman.backstage.projections.bi_sales import build_bi_sales


def _view_bi_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="view_bi",
    )


@pytest.fixture
def bi_viewer(db):
    user = User.objects.create_user("bi-biz", password="pw", is_staff=True)
    user.user_permissions.add(_view_bi_perm())
    return user


def _order(ref: str, *, total_q: int, status=Order.Status.COMPLETED, channel_ref="web", items=()):
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=total_q)
    for index, (sku, name, qty, line_total_q) in enumerate(items, start=1):
        OrderItem.objects.create(
            order=order,
            line_id=f"l{index}",
            sku=sku,
            name=name,
            qty=Decimal(qty),
            unit_price_q=line_total_q // qty,
            line_total_q=line_total_q,
        )
    return order


# ── Gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name", ["api-backstage-bi-sales", "api-backstage-bi-cash", "api-backstage-bi-customers"]
)
def test_bi_endpoints_require_view_bi(client, url_name):
    bare = User.objects.create_user(f"bare-{url_name}", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name", ["api-backstage-bi-sales", "api-backstage-bi-cash", "api-backstage-bi-customers"]
)
def test_bi_endpoints_respond_for_viewer(client, bi_viewer, url_name):
    client.force_login(bi_viewer)
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    assert "bi" in response.json()


# ── Vendas ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sales_series_excludes_cancelled_and_counts_it(db):
    _order("BI-S1", total_q=1500, items=[("PAO", "Pão", 2, 1000), ("CAFE", "Café", 1, 500)])
    _order("BI-S2", total_q=2500, channel_ref="pdv", items=[("PAO", "Pão", 3, 2500)])
    _order("BI-S3", total_q=9900, status=Order.Status.CANCELLED)

    report = build_bi_sales()
    today = report.days[-1]
    assert today.orders == 2
    assert today.revenue_q == 4000
    assert today.average_ticket_q == 2000
    assert report.cancelled_total == 1
    assert report.orders_total == 2
    assert {row.channel_ref for row in report.by_channel} == {"web", "pdv"}

    top = report.top_skus[0]
    assert top.sku == "PAO"
    assert top.qty == "5"
    assert top.revenue_q == 3500

    now = timezone.localtime()
    assert report.orders_by_hour[now.hour] == 2
    assert report.orders_by_weekday[now.weekday()] == 2


# ── Caixa ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cash_variance_by_operator_and_missing_closings(db):
    operator = User.objects.create_user("caixa-ana", password="pw")
    terminal = POSTerminal.objects.create(ref="t1", label="Caixa 1")
    now = timezone.now()
    shift = CashShift.objects.create(
        terminal=terminal,
        operator=operator,
        opened_at=now,
        closed_at=now,
        opening_amount_q=10000,
        blind_closing_amount_q=9800,
        expected_amount_q=10000,
        difference_q=-200,
        status=CashShift.Status.CLOSED,
    )
    CashMovement.objects.create(
        shift=shift, movement_type="sangria", amount_q=5000, reason="teste", created_by=operator
    )
    DayClosing.objects.create(
        date=timezone.localdate(),
        closed_by=operator,
        data={"cash_shift_summary": {"payment_method_totals": {"pix": 4000, "cash": 6000, "cod_pending_count": 2}}},
    )

    report = build_bi_cash()
    today = report.days[-1]
    assert today.shifts == 1
    assert today.difference_q == -200
    assert today.sangria_q == 5000
    assert report.by_operator == (
        report.by_operator[0].__class__(operator="caixa-ana", shifts=1, difference_q=-200),
    )
    assert {(m.method, m.amount_q) for m in report.payment_methods} == {("pix", 4000), ("cash", 6000)}
    # 28 dias de janela, só hoje fechado: 27 buracos DECLARADOS.
    assert report.closings_missing == 27


# ── Clientes ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_customers_reads_insights_without_recalculating(db):
    vip = Customer.objects.create(ref="cli-vip", first_name="Alice")
    risk = Customer.objects.create(ref="cli-risk", first_name="Bia")
    CustomerInsight.objects.create(
        customer=vip, rfm_segment="champion", average_ticket_q=6000, total_orders=12
    )
    CustomerInsight.objects.create(
        customer=risk,
        rfm_segment="at_risk",
        average_ticket_q=2000,
        total_orders=3,
        churn_risk=Decimal("0.9"),
    )

    report = build_bi_customers()
    assert report.customers_total == 2
    assert report.with_insight == 2
    assert report.at_risk == 1
    assert report.average_ticket_q == 4000
    segments = {row.segment: row.customers for row in report.segments}
    assert segments == {"champion": 1, "at_risk": 1}
    assert report.new_by_week[-1].new_customers == 2
