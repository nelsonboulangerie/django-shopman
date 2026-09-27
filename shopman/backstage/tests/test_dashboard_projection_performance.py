"""Query budgets for the Admin dashboard projections."""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.stockman.models import Position, Quant, StockAlert

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
