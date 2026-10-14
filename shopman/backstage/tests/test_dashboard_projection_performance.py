"""Query budgets for the Admin dashboard projections."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman.models import Hold, HoldStatus, Position, Quant, StockAlert
from shopman.stockman.services.alerts import check_alerts

from shopman.backstage.projections.dashboard import _stock_alerts


@pytest.mark.django_db
@pytest.mark.parametrize("alert_count", (1, 10))
def test_stock_alerts_batch_quantities_with_constant_query_budget(
    alert_count, django_assert_num_queries
):
    counter = Position.objects.create(ref="perf-counter", name="Balcão")
    storage = Position.objects.create(ref="perf-storage", name="Depósito")

    # Um alerta global prova a soma entre posições; nove específicos provam que
    # crescer até o limite visual do dashboard não cresce o número de queries.
    StockAlert.objects.create(sku="PERF-GLOBAL", min_quantity=10)
    Quant.objects.create(sku="PERF-GLOBAL", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="PERF-GLOBAL", position=storage, _quantity=Decimal("3"))
    for index in range(alert_count - 1):
        sku = f"PERF-{index}"
        StockAlert.objects.create(sku=sku, position=counter, min_quantity=Decimal("5"))
        Quant.objects.create(sku=sku, position=counter, _quantity=Decimal(index % 3))
        # Este saldo não pertence ao alerta específico da posição.
        Quant.objects.create(sku=sku, position=storage, _quantity=Decimal("100"))

    with django_assert_num_queries(2):
        rows = _stock_alerts()

    assert len(rows) == alert_count
    global_row = next(row for row in rows if row.sku == "PERF-GLOBAL")
    assert global_row.current == "5"
    assert global_row.deficit == "5.000"
    assert global_row.position == "Todas"
    assert all(row.position == "Balcão" for row in rows if row.sku != "PERF-GLOBAL")


@pytest.mark.django_db
def test_check_alerts_parity_with_dashboard_stock_alerts(django_assert_num_queries):
    """check_alerts e _stock_alerts concordam no conjunto disparado.

    A projeção do dashboard não modela reservas nem estoque planejado; este
    cenário de paridade usa só estoque físico e nenhuma reserva ativa (a
    reserva vencida é ignorada pelos dois). check_alerts continua gastando
    2 consultas: a leitura em bloco e o UPDATE dos disparados.
    """
    counter = Position.objects.create(ref="parity-counter", name="Balcão")
    storage = Position.objects.create(ref="parity-storage", name="Depósito")

    StockAlert.objects.create(sku="PARITY-GLOBAL", min_quantity=Decimal("10"))
    Quant.objects.create(sku="PARITY-GLOBAL", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="PARITY-GLOBAL", position=storage, _quantity=Decimal("3"))

    StockAlert.objects.create(sku="PARITY-POS", position=counter, min_quantity=Decimal("5"))
    Quant.objects.create(sku="PARITY-POS", position=counter, _quantity=Decimal("2"))
    Quant.objects.create(sku="PARITY-POS", position=storage, _quantity=Decimal("100"))

    StockAlert.objects.create(sku="PARITY-HIGH", position=counter, min_quantity=Decimal("1"))
    Quant.objects.create(sku="PARITY-HIGH", position=counter, _quantity=Decimal("10"))

    StockAlert.objects.create(
        sku="PARITY-OFF", position=counter, min_quantity=Decimal("99"), is_active=False
    )
    Quant.objects.create(sku="PARITY-OFF", position=counter, _quantity=Decimal("0"))

    # Reserva vencida: nem check_alerts nem o dashboard a descontam.
    quant = Quant.objects.get(sku="PARITY-GLOBAL", position=counter)
    Hold.objects.create(
        sku="PARITY-GLOBAL",
        quant=quant,
        quantity=Decimal("100"),
        target_date=timezone.localdate(),
        status=HoldStatus.CONFIRMED,
        expires_at=timezone.now() - timedelta(hours=1),
    )

    with django_assert_num_queries(2):
        triggered = check_alerts()
    rows = _stock_alerts()

    available_by_sku = {alert.sku: str(available) for alert, available in triggered}
    assert {row.sku: row.current for row in rows} == available_by_sku
    assert set(available_by_sku) == {"PARITY-GLOBAL", "PARITY-POS"}
