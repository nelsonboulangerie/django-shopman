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
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.bi_cash import build_bi_cash
from shopman.backstage.projections.bi_customers import build_bi_customers
from shopman.backstage.projections.bi_sales import build_bi_sales
from shopman.backstage.tests.support import historical_batch


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
@pytest.mark.parametrize("url_name", ["api-backstage-bi-sales", "api-backstage-bi-customers"])
def test_bi_endpoints_respond_for_viewer(client, bi_viewer, url_name):
    client.force_login(bi_viewer)
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    assert "bi" in response.json()


def _audit_perm() -> Permission:
    from shopman.cashman.models import Shift

    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shift), codename="audit_shift"
    )


@pytest.mark.django_db
def test_cash_panel_is_audit_only_even_for_a_bi_viewer(client, bi_viewer):
    """Quebra por operador é apuração, não faturamento: quem opera não vê (decisão do dono, 19/08).

    `view_bi` sozinho abre vendas e produção; o caixa pede `cashman.audit_shift`
    além dele — a permissão que o fechamento cego reserva a quem audita.
    """
    client.force_login(bi_viewer)
    assert client.get(reverse("api-backstage-bi-cash")).status_code == 403
    # A gramática do explorador não oferece o que a API vai recusar…
    explore = client.get(reverse("api-backstage-bi-explore"))
    assert explore.status_code == 200
    assert "cash_difference" not in {m["key"] for m in explore.json()["bi"]["metrics"]}
    # …e pedir por ela direto é 403, com o motivo.
    denied = client.get(reverse("api-backstage-bi-explore"), {"metric": "cash_difference", "by": "operator"})
    assert denied.status_code == 403
    assert "audit" in denied.json()["detail"]

    bi_viewer.user_permissions.add(_audit_perm())
    client.force_login(bi_viewer)  # perms são cacheadas por request user; relogar limpa
    assert client.get(reverse("api-backstage-bi-cash")).status_code == 200
    explore = client.get(reverse("api-backstage-bi-explore"))
    assert "cash_difference" in {m["key"] for m in explore.json()["bi"]["metrics"]}
    assert client.get(reverse("api-backstage-bi-explore"), {"metric": "cash_difference", "by": "operator"}).status_code == 200


@pytest.mark.django_db
def test_audit_alone_does_not_open_the_bi(client):
    """As duas permissões são exigidas: auditar o turno não é ver o B.I."""
    auditor = User.objects.create_user("so-audita", password="pw", is_staff=True)
    auditor.user_permissions.add(_audit_perm())
    client.force_login(auditor)
    assert client.get(reverse("api-backstage-bi-cash")).status_code == 403


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
    assert report.days[-1].source == "shopman"
    assert report.historical_days == 0


@pytest.mark.django_db
def test_sales_historical_fills_only_days_without_native(db):
    from datetime import timedelta

    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem

    _order("BI-H1", total_q=2000, items=[("PAO", "Pão", 1, 2000)])
    now = timezone.now()
    yesterday_sale = HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=1, occurred_at=now - timedelta(days=1),
        total_q=3000, is_delivery=False,
    )
    HistoricalSaleItem.objects.create(
        sale=yesterday_sale, seq=1, product_name="Pão de Ontem", sku="",
        qty=Decimal("3"), unit_price_q=1000, line_total_q=3000,
    )
    # Mesmo dia que a venda nativa: o dia nativo VENCE — este registro não conta.
    HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=2, occurred_at=now, total_q=99900, is_delivery=True,
    )

    report = build_bi_sales()
    today, yesterday = report.days[-1], report.days[-2]
    assert today.source == "shopman" and today.revenue_q == 2000
    assert yesterday.source == "yooga" and yesterday.revenue_q == 3000
    assert report.historical_days == 1
    assert report.orders_total == 2
    assert report.revenue_total_q == 5000

    channels = {row.channel_ref: row.revenue_q for row in report.by_channel}
    assert channels == {"web": 2000, "yooga · loja": 3000}

    tops = {(row.sku, row.name): row.revenue_q for row in report.top_skus}
    # Item histórico sem sku agrega pelo nome; o do dia vencido não aparece.
    assert tops == {("PAO", "Pão"): 2000, ("", "Pão de Ontem"): 3000}


# ── Comparação (F7) ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sales_previous_window_agrees_with_main_build(db):
    """O `previous` usa a MESMA regra de fusão do principal: os totais têm que
    bater com um build feito diretamente sobre a janela anterior."""
    from datetime import date, timedelta

    from shopman.backstage.models import HistoricalSale

    today = timezone.localdate()
    # 3 vendas históricas dentro da janela ANTERIOR à default de 28 dias.
    for index in range(3):
        HistoricalSale.objects.create(
            batch=historical_batch("yooga"), source="yooga", external_id=100 + index,
            occurred_at=timezone.now() - timedelta(days=30 + index),
            total_q=1000 * (index + 1), is_delivery=False,
        )
    _order("BI-P1", total_q=2000)  # janela atual

    report = build_bi_sales()
    prev_from = date.fromisoformat(report.previous.date_from)
    prev_to = date.fromisoformat(report.previous.date_to)
    assert (prev_to - prev_from).days == (today - date.fromisoformat(report.date_from)).days
    assert prev_to == date.fromisoformat(report.date_from) - timedelta(days=1)

    direct = build_bi_sales(date_from=prev_from, date_to=prev_to)
    assert report.previous.orders_total == direct.orders_total == 3
    assert report.previous.revenue_total_q == direct.revenue_total_q == 6000
    assert report.previous.average_ticket_q == direct.average_ticket_q
    assert len(report.previous.revenue_by_day) == len(report.days)
    assert sum(report.previous.revenue_by_day) == 6000


@pytest.mark.django_db
def test_cash_and_production_carry_previous(db):
    from shopman.backstage.projections.bi_production import build_bi_production

    cash = build_bi_cash()
    assert cash.previous.shifts_total == 0
    assert len(cash.previous.difference_by_day) == len(cash.days)

    production = build_bi_production()
    assert production.previous.batches_finished == 0
    assert len(production.previous.finished_by_day) == len(production.days)


# ── Caixa ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cash_variance_by_operator_and_missing_closings(db):
    operator = User.objects.create_user("caixa-ana", password="pw", is_staff=True)
    manager = User.objects.create_user("gerente-bi", password="pw", is_staff=True)
    terminal = Terminal.objects.create(ref="t1", label="Caixa 1")
    # Tudo pelo livro: fundo 100,00, sangria 50,00, contagem 48,00 → falta de 2,00.
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
    cash.record(Entry.Kind.CASH_OUT, shift=shift, operator=operator, approved_by=manager, amount_q=-5000, reason="teste")
    # E o comportamento de gaveta, do mesmo livro (WP-8): duas aberturas sem
    # venda, um destrave por gerente e um pedido de troco — por operador e por hora.
    cash.record(Entry.Kind.DRAWER_OPEN, shift=shift, operator=operator, reason="conferir")
    cash.record(Entry.Kind.DRAWER_OPEN, shift=shift, operator=operator, reason="conferir")
    cash.record(Entry.Kind.DRAWER_UNLOCK, shift=shift, operator=operator, approved_by=manager, reason="emperrou")
    cash.record(Entry.Kind.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 5000})
    cash.close_shift(shift, counted_q=4800, actor=operator)
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
    (ana,) = report.by_operator
    assert (ana.operator, ana.shifts, ana.difference_q) == ("caixa-ana", 1, -200)
    assert (ana.drawer_openings, ana.drawer_unlocks, ana.change_requests) == (2, 1, 1)
    hour = timezone.localtime(timezone.now()).hour
    assert [(row.hour, row.drawer_openings, row.drawer_unlocks) for row in report.drawer_by_hour] == [(hour, 2, 1)]
    assert {(m.method, m.amount_q) for m in report.payment_methods} == {("pix", 4000), ("cash", 6000)}
    # 28 dias de janela, só hoje fechado: 27 buracos DECLARADOS.
    assert report.closings_missing == 27


@pytest.mark.django_db
def test_cash_drawer_behaviour_comes_from_the_ledger(db):
    """Quem abre a gaveta, quantos destraves, e a que horas: a pergunta que
    motivou o livro. O operador com turno ainda ABERTO entra na tabela mesmo
    assim: a abertura de gaveta não espera o fechamento para contar."""
    from datetime import datetime, time

    ana = User.objects.create_user("caixa-ana", password="pw", is_staff=True)
    bia = User.objects.create_user("caixa-bia", password="pw", is_staff=True)
    manager = User.objects.create_user("gerente-bi", password="pw", is_staff=True)
    shift_a = cash.open_shift(operator=ana, terminal=Terminal.objects.create(ref="t1"), float_q=0)
    shift_b = cash.open_shift(operator=bia, terminal=Terminal.objects.create(ref="t2"), float_q=0)
    tz = timezone.get_current_timezone()
    at_10 = timezone.make_aware(datetime.combine(timezone.localdate(), time(10, 15)), tz)
    at_16 = timezone.make_aware(datetime.combine(timezone.localdate(), time(16, 40)), tz)

    for _ in range(3):
        cash.record(Entry.Kind.DRAWER_OPEN, shift=shift_a, operator=ana, at=at_10, reason="x")
    cash.record(Entry.Kind.DRAWER_UNLOCK, shift=shift_a, operator=ana, approved_by=manager, at=at_16)
    cash.record(Entry.Kind.CHANGE_REQUESTED, shift=shift_b, operator=bia, at=at_16, payload={"kind": "coins"})

    report = build_bi_cash()

    by_operator = {row.operator: row for row in report.by_operator}
    assert by_operator["caixa-ana"].drawer_openings == 3
    assert by_operator["caixa-ana"].drawer_unlocks == 1
    assert by_operator["caixa-ana"].shifts == 0  # turno aberto: ainda sem quebra
    assert by_operator["caixa-bia"].change_requests == 1
    assert [(h.hour, h.drawer_openings, h.drawer_unlocks) for h in report.drawer_by_hour] == [
        (10, 3, 0),
        (16, 0, 1),
    ]


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
