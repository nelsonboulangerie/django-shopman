"""
Testes de check_alerts: orcamento de consultas constante e semantica.

O check_alerts dispara alerta quando disponivel < min_quantity, onde
disponivel = estoque fisico (Quant sem data alvo ou com data <= hoje) menos as
reservas ativas de hoje. O alerta por posicao so enxerga a propria posicao; o
alerta global soma todas. Estes testes prendem o orcamento de consultas em 2
(uma leitura em bloco + um UPDATE dos disparados) e a semantica que a versao
anterior entregava.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman.models import Hold, HoldStatus, Position, Quant, StockAlert
from shopman.stockman.services.alerts import check_alerts

pytestmark = pytest.mark.django_db


@pytest.fixture
def counter(db):
    return Position.objects.create(ref="alerts-counter", name="Balcao")


@pytest.fixture
def storage(db):
    return Position.objects.create(ref="alerts-storage", name="Deposito")


# ── Orcamento de consultas ─────────────────────────────────────────────


@pytest.mark.parametrize("alert_count", (1, 10))
def test_check_alerts_query_count_does_not_grow_with_alerts(
    alert_count, counter, storage, django_assert_num_queries
):
    """1 ou 10 alertas: sempre 2 consultas (leitura em bloco + UPDATE)."""
    StockAlert.objects.create(sku="BUDGET-GLOBAL", min_quantity=Decimal("10"))
    Quant.objects.create(sku="BUDGET-GLOBAL", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="BUDGET-GLOBAL", position=storage, _quantity=Decimal("3"))

    for index in range(alert_count - 1):
        sku = f"BUDGET-{index}"
        StockAlert.objects.create(sku=sku, position=counter, min_quantity=Decimal("5"))
        Quant.objects.create(sku=sku, position=counter, _quantity=Decimal(index % 3))
        # Este saldo nao pertence ao alerta especifico da posicao.
        Quant.objects.create(sku=sku, position=storage, _quantity=Decimal("100"))

    with django_assert_num_queries(2):
        triggered = check_alerts()

    assert len(triggered) == alert_count
    available_by_sku = {alert.sku: available for alert, available in triggered}
    assert available_by_sku["BUDGET-GLOBAL"] == Decimal("5")
    for index in range(alert_count - 1):
        assert available_by_sku[f"BUDGET-{index}"] == Decimal(index % 3)
    # Todos dispararam: o UPDATE unico gravou last_triggered_at.
    assert not StockAlert.objects.filter(last_triggered_at__isnull=True).exists()


# ── Semantica: posicao ─────────────────────────────────────────────────


def test_global_alert_sums_all_positions(counter, storage):
    StockAlert.objects.create(sku="GLOBAL", min_quantity=Decimal("10"))
    Quant.objects.create(sku="GLOBAL", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="GLOBAL", position=storage, _quantity=Decimal("3"))

    triggered = check_alerts()

    assert [(alert.sku, available) for alert, available in triggered] == [
        ("GLOBAL", Decimal("5"))
    ]


def test_position_alert_only_counts_its_own_position(counter, storage):
    StockAlert.objects.create(sku="POS", position=counter, min_quantity=Decimal("5"))
    Quant.objects.create(sku="POS", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="POS", position=storage, _quantity=Decimal("100"))

    triggered = check_alerts()

    assert [(alert.sku, available) for alert, available in triggered] == [
        ("POS", Decimal("2"))
    ]


# ── Semantica: reservas ────────────────────────────────────────────────


def test_global_alert_subtracts_active_holds_from_every_position(counter, storage):
    StockAlert.objects.create(sku="HOLD-GLOBAL", min_quantity=Decimal("10"))
    quant_counter = Quant.objects.create(
        sku="HOLD-GLOBAL", position=counter, _quantity=Decimal("4")
    )
    quant_storage = Quant.objects.create(
        sku="HOLD-GLOBAL", position=storage, _quantity=Decimal("4")
    )
    # Ativas: 2 no balcao + 1 no deposito + 5 de demanda sem quant.
    Hold.objects.create(
        sku="HOLD-GLOBAL", quant=quant_counter, quantity=Decimal("2"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
    )
    Hold.objects.create(
        sku="HOLD-GLOBAL", quant=quant_storage, quantity=Decimal("1"),
        target_date=timezone.localdate(), status=HoldStatus.PENDING,
    )
    Hold.objects.create(
        sku="HOLD-GLOBAL", quant=None, quantity=Decimal("5"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
    )
    # Ignoradas: vencida e ja cumprida.
    expired = timezone.now() - timedelta(hours=1)
    Hold.objects.create(
        sku="HOLD-GLOBAL", quant=quant_counter, quantity=Decimal("100"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED, expires_at=expired,
    )
    Hold.objects.create(
        sku="HOLD-GLOBAL", quant=quant_counter, quantity=Decimal("100"),
        target_date=timezone.localdate(), status=HoldStatus.FULFILLED,
    )

    triggered = check_alerts()

    # 8 fisico - 8 reservado = 0 < 10.
    assert [(alert.sku, available) for alert, available in triggered] == [
        ("HOLD-GLOBAL", Decimal("0"))
    ]


def test_position_alert_ignores_holds_on_other_positions_and_demand(counter, storage):
    StockAlert.objects.create(sku="HOLD-POS", position=counter, min_quantity=Decimal("5"))
    quant_counter = Quant.objects.create(
        sku="HOLD-POS", position=counter, _quantity=Decimal("10")
    )
    quant_storage = Quant.objects.create(
        sku="HOLD-POS", position=storage, _quantity=Decimal("0")
    )
    Hold.objects.create(
        sku="HOLD-POS", quant=quant_counter, quantity=Decimal("6"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
    )
    Hold.objects.create(
        sku="HOLD-POS", quant=quant_storage, quantity=Decimal("100"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
    )
    Hold.objects.create(
        sku="HOLD-POS", quant=None, quantity=Decimal("50"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
    )

    triggered = check_alerts()

    # 10 - 6 = 4 < 5; as reservas do deposito e de demanda nao entram.
    assert [(alert.sku, available) for alert, available in triggered] == [
        ("HOLD-POS", Decimal("4"))
    ]


def test_expired_hold_does_not_lower_availability(counter):
    StockAlert.objects.create(sku="EXPIRED", position=counter, min_quantity=Decimal("1"))
    quant = Quant.objects.create(sku="EXPIRED", position=counter, _quantity=Decimal("5"))
    Hold.objects.create(
        sku="EXPIRED", quant=quant, quantity=Decimal("5"),
        target_date=timezone.localdate(), status=HoldStatus.CONFIRMED,
        expires_at=timezone.now() - timedelta(hours=1),
    )

    assert check_alerts() == []


# ── Semantica: estoque fisico x planejado ──────────────────────────────


def test_future_quant_is_not_physical_stock(counter):
    StockAlert.objects.create(sku="FUTURE", position=counter, min_quantity=Decimal("6"))
    Quant.objects.create(
        sku="FUTURE", position=counter, _quantity=Decimal("100"),
        target_date=timezone.localdate() + timedelta(days=1),
    )

    triggered = check_alerts()

    assert [(alert.sku, available) for alert, available in triggered] == [
        ("FUTURE", Decimal("0"))
    ]


def test_past_quant_counts_as_physical_stock(counter):
    StockAlert.objects.create(sku="PAST", position=counter, min_quantity=Decimal("6"))
    Quant.objects.create(
        sku="PAST", position=counter, _quantity=Decimal("10"),
        target_date=timezone.localdate() - timedelta(days=1),
    )

    assert check_alerts() == []


# ── Semantica: selecao ─────────────────────────────────────────────────


def test_inactive_alert_is_skipped(counter):
    StockAlert.objects.create(
        sku="INACTIVE", position=counter, min_quantity=Decimal("100"), is_active=False
    )
    Quant.objects.create(sku="INACTIVE", position=counter, _quantity=Decimal("0"))

    assert check_alerts() == []


def test_sku_filter_checks_only_that_sku(counter):
    StockAlert.objects.create(sku="FILTER-A", position=counter, min_quantity=Decimal("10"))
    StockAlert.objects.create(sku="FILTER-B", position=counter, min_quantity=Decimal("10"))
    Quant.objects.create(sku="FILTER-A", position=counter, _quantity=Decimal("1"))
    Quant.objects.create(sku="FILTER-B", position=counter, _quantity=Decimal("1"))

    triggered = check_alerts(sku="FILTER-A")

    assert [alert.sku for alert, _ in triggered] == ["FILTER-A"]
    assert StockAlert.objects.get(sku="FILTER-B").last_triggered_at is None


def test_no_alerts_returns_empty(db):
    assert check_alerts() == []


def test_available_equal_to_minimum_does_not_trigger(counter):
    StockAlert.objects.create(sku="BOUNDARY", position=counter, min_quantity=Decimal("5"))
    Quant.objects.create(sku="BOUNDARY", position=counter, _quantity=Decimal("5"))

    assert check_alerts() == []


def test_trigger_stamps_last_triggered_at_and_returns_original_order(counter, storage):
    StockAlert.objects.create(sku="ORDER-A", min_quantity=Decimal("10"))
    StockAlert.objects.create(sku="ORDER-B", position=counter, min_quantity=Decimal("10"))
    Quant.objects.create(sku="ORDER-A", position=counter, _quantity=Decimal("1"))
    Quant.objects.create(sku="ORDER-B", position=counter, _quantity=Decimal("1"))

    triggered = check_alerts()

    assert [alert.pk for alert, _ in triggered] == list(
        StockAlert.objects.filter(is_active=True).values_list("pk", flat=True)
    )
    assert all(alert.last_triggered_at is not None for alert, _ in triggered)
    assert not StockAlert.objects.filter(last_triggered_at__isnull=True).exists()
