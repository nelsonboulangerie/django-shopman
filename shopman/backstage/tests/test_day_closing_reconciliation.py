from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.stockman import Position
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import ReconciliationError, build_day_closing
from shopman.shop.models import Shop


@pytest.fixture
def closing_user(db):
    user = User.objects.create_user("closing-recon", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="perform_closing",
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def setup_stock(db):
    Shop.objects.create(name="Loja")
    shop = Position.objects.create(ref="loja", name="Loja", is_saleable=True)
    Product.objects.create(sku="RECON-SKU", name="Recon SKU", shelf_life_days=0)
    StockMovements.receive(quantity=2, sku="RECON-SKU", position=shop, reason="seed")
    return shop


@pytest.mark.django_db
def test_build_day_closing_exposes_empty_production_summary(setup_stock):
    closing = build_day_closing()

    assert closing.production_summary == {}
    assert closing.reconciliation_errors == ()


@pytest.mark.django_db
def test_build_day_closing_exposes_today_production_summary(setup_stock):
    recipe = Recipe.objects.create(ref="recon-recipe", name="Recon", output_sku="RECON-SKU", batch_size=Decimal("10"))
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=8, actor="test")

    closing = build_day_closing()

    assert closing.production_summary["recon-recipe"]["planned"] == 10
    assert closing.production_summary["recon-recipe"]["finished"] == 8
    assert closing.production_summary["recon-recipe"]["loss"] == 2


@pytest.mark.django_db
def test_production_summary_keeps_fractional_quantities(setup_stock):
    """Receita por peso: 2,5 kg não pode virar 2 no resumo (int truncava)."""
    recipe = Recipe.objects.create(
        ref="recon-massa", name="Massa por peso", output_sku="RECON-SKU", batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, Decimal("2.5"), date=date.today())
    craft.start(wo, quantity=Decimal("2.5"), expected_rev=0)
    craft.finish(wo, finished=Decimal("1.75"), actor="test")

    closing = build_day_closing()

    row = closing.production_summary["recon-massa"]
    assert row["planned"] == 2.5
    assert row["finished"] == 1.75
    assert row["loss"] == 0.75


@pytest.mark.django_db
def test_production_summary_consolidates_quality_partition(setup_stock):
    """A partição do QC chega ao fechamento (ADR-017 §8): unidades por grau,
    por receita — e o finish escalar (sem grau) fica fora do dict de quality."""
    recipe = Recipe.objects.create(
        ref="recon-qc", name="Recon QC", output_sku="RECON-SKU", batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(
        wo,
        finished=[
            {"item_ref": "RECON-SKU", "quantity": "7", "quality_grade_ref": "standard"},
            {"item_ref": "RECON-SKU", "quantity": "2", "quality_grade_ref": "minimal"},
        ],
        wasted=[{"item_ref": "RECON-SKU", "quantity": "1"}],
        actor="test",
    )

    closing = build_day_closing()

    row = closing.production_summary["recon-qc"]
    assert row["finished"] == 9
    assert row["loss"] == 1
    assert row["quality"] == {"standard": 7, "minimal": 2}


@pytest.mark.django_db
def test_perform_day_closing_persists_production_summary(client, setup_stock, closing_user):
    recipe = Recipe.objects.create(ref="recon-close", name="Recon Close", output_sku="RECON-SKU", batch_size=Decimal("10"))
    wo = craft.plan(recipe, 5, date=date.today())
    craft.start(wo, quantity=5, expected_rev=0)
    craft.finish(wo, finished=4, actor="test")
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "1"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    closing = DayClosing.objects.get()
    assert closing.data["production_summary"]["recon-close"]["finished"] == 4
    assert "reconciliation_errors" in closing.data


@pytest.mark.django_db
def test_perform_day_closing_persists_cash_shift_summary(client, setup_stock, closing_user):
    terminal = Terminal.default()
    shift = cash.open_shift(operator=closing_user, terminal=terminal, float_q=1000)
    cash.close_shift(shift, counted_q=900, actor=closing_user)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    summary = DayClosing.objects.get().data["cash_shift_summary"]
    # Calculado do livro no momento do fechamento (snapshot): esperado, contado e
    # diferença são somas do cashman, não colunas.
    row = summary["closed_shifts"][0]
    assert row["id"] == shift.pk
    assert row["opening_amount_q"] == 1000
    assert row["expected_amount_q"] == 1000
    assert row["blind_closing_amount_q"] == 900
    assert row["difference_q"] == -100
    assert summary["totals"]["blind_closing_amount_q"] == 900
    assert summary["totals"]["difference_q"] == -100


def _settled(ref: str, *, order_ref: str, method: str, amount_q: int) -> PaymentIntent:
    intent = PaymentIntent.objects.create(
        ref=ref, order_ref=order_ref, method=method, status=PaymentIntent.Status.CAPTURED,
        amount_q=amount_q, gateway="" if method == "cash" else "test", captured_at=timezone.now(),
    )
    PaymentTransaction.objects.create(intent=intent, type=PaymentTransaction.Type.CAPTURE, amount_q=amount_q)
    return intent


@pytest.mark.django_db
def test_day_closing_summarizes_payment_methods_and_cod_pending(client, setup_stock, closing_user):
    """Mix de meios vem do ``payman`` (intents capturados no dia); o pendente de entrega, do pedido."""
    Order.objects.create(
        ref="RECON-PAY-SPLIT",
        channel_ref="pdv",
        status="completed",
        total_q=1500,
        data={
            "payment": {
                "method": "mixed",
                "tenders": [
                    {"method": "cash", "amount_q": 500, "collection": "terminal", "status": "received"},
                    {"method": "pix", "amount_q": 1000, "collection": "terminal", "status": "received"},
                ],
            }
        },
    )
    _settled("PI-SPLIT-CASH", order_ref="RECON-PAY-SPLIT", method="cash", amount_q=500)
    pix = _settled("PI-SPLIT-PIX", order_ref="RECON-PAY-SPLIT", method="pix", amount_q=1000)
    # Um estorno parcial no pix: o total do dia é líquido.
    PaymentTransaction.objects.create(intent=pix, type=PaymentTransaction.Type.REFUND, amount_q=200)
    Order.objects.create(
        ref="RECON-PAY-COD",
        channel_ref="pdv",
        status="dispatched",
        total_q=1200,
        data={
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "tenders": [{"method": "cash", "amount_q": 1200, "collection": "on_delivery", "status": "pending"}],
            }
        },
    )
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    methods = DayClosing.objects.get().data["cash_shift_summary"]["payment_method_totals"]
    assert methods["cash"] == 500
    assert methods["pix"] == 800
    assert methods["cod_pending_q"] == 1200
    assert methods["cod_pending_count"] == 1


@pytest.mark.django_db
def test_reconciliation_error_when_sold_exceeds_available(client, setup_stock, closing_user):
    order = Order.objects.create(ref="RECON-ORD", channel_ref="web", status="completed", total_q=3000)
    OrderItem.objects.create(order=order, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    error = DayClosing.objects.get().data["reconciliation_errors"][0]
    assert error["sku"] == "RECON-SKU"
    assert error["deficit"] == 3

    closing = build_day_closing()
    assert len(closing.reconciliation_errors) == 1
    typed = closing.reconciliation_errors[0]
    assert isinstance(typed, ReconciliationError)
    assert typed.sku == "RECON-SKU"
    assert typed.sold_qty == 5
    assert typed.deficit_qty == 3
    assert typed.available_qty == 2


def test_reconciliation_error_from_dict():
    raw = {"sku": "X", "sold": 10, "available": 6, "deficit": 4}
    err = ReconciliationError.from_dict(raw)
    assert err == ReconciliationError(sku="X", sold_qty=10, available_qty=6, deficit_qty=4)


@pytest.mark.django_db
def test_future_preorder_does_not_create_false_deficit(client, setup_stock, closing_user):
    """WP-D: encomenda vendida hoje para data futura NÃO conta como vendida
    hoje na reconciliação de estoque — a baixa só acontece na data combinada.
    Contá-la hoje fabricava um deficit falso (estoque nunca saiu)."""
    from datetime import timedelta

    from django.utils import timezone

    preorder = Order.objects.create(
        ref="RECON-ENC",
        channel_ref="web",
        status="accepted",
        total_q=500,
        data={"delivery_date": (timezone.localdate() + timedelta(days=2)).isoformat()},
    )
    OrderItem.objects.create(order=preorder, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "2"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert DayClosing.objects.get().data["reconciliation_errors"] == []


@pytest.mark.django_db
def test_preorder_counts_in_reconciliation_of_the_delivery_day(setup_stock):
    """Contraprova: no fechamento DA DATA combinada a encomenda conta como
    vendida — ali o estoque saiu de verdade."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.backstage.services.closing import _reconciliation_errors

    delivery_day = timezone.localdate() + timedelta(days=2)
    preorder = Order.objects.create(
        ref="RECON-ENC-DIA",
        channel_ref="web",
        status="accepted",
        total_q=500,
        data={"delivery_date": delivery_day.isoformat()},
    )
    OrderItem.objects.create(order=preorder, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)

    errors = _reconciliation_errors(closing_date=delivery_day, items=[])

    assert errors == [{"sku": "RECON-SKU", "sold": 5, "available": 0, "deficit": 5}]


@pytest.mark.django_db
def test_build_day_closing_lists_upcoming_preorders(setup_stock):
    """WP-D: o fechamento informa as encomendas dos próximos dias (qtd + total),
    agregadas pela data combinada."""
    from datetime import timedelta

    from django.utils import timezone

    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    saturday = (timezone.localdate() + timedelta(days=3)).isoformat()
    Order.objects.create(ref="ENC-1", channel_ref="web", status="accepted", total_q=1500, data={"delivery_date": tomorrow})
    Order.objects.create(ref="ENC-2", channel_ref="web", status="accepted", total_q=2500, data={"delivery_date": tomorrow})
    Order.objects.create(ref="ENC-3", channel_ref="web", status="accepted", total_q=1000, data={"delivery_date": saturday})
    # Cancelada e de hoje ficam de fora.
    Order.objects.create(ref="ENC-4", channel_ref="web", status="cancelled", total_q=999, data={"delivery_date": tomorrow})
    Order.objects.create(ref="HOJE-1", channel_ref="web", status="accepted", total_q=999, data={"delivery_date": timezone.localdate().isoformat()})

    closing = build_day_closing()

    assert closing.has_upcoming_preorders is True
    assert [(row.date_display, row.orders_count, row.total_display) for row in closing.upcoming_preorders] == [
        ("amanhã", 2, "R$ 40,00"),
        (closing.upcoming_preorders[1].date_display, 1, "R$ 10,00"),
    ]
    assert closing.upcoming_preorders[0].total_q == 4000
