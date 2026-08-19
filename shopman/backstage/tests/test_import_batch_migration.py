"""A migração 0022 dá lote às vendas históricas que já existiam.

Um ambiente com o Yooga carregado antes do controle de lote (o staging) não
pode ficar com FK nula nem ganhar um lote inventado com hash de mentira: ganha
UM lote por origem, declarado como "anterior ao controle", com a contagem
certa. É o único teste que exercita a migração de dados; o `migrate` de banco
zerado (CI) cobre o caminho vazio.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

BEFORE = [("backstage", "0023_consumption_eat_in_weight")]
AFTER = [("backstage", "0024_importbatch")]


@pytest.mark.django_db(transaction=True)
def test_existing_sales_receive_one_legacy_batch_per_source():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    old_apps = executor.loader.project_state(BEFORE).apps
    HistoricalSale = old_apps.get_model("backstage", "HistoricalSale")
    now = timezone.now()
    # Instantes DIFERENTES de propósito: com o `ordering = ["-occurred_at"]` do
    # model, um `.distinct()` sem `.order_by()` contaria uma "fonte" por instante
    # — e este teste passava com três linhas no mesmo segundo enquanto o staging
    # ficava preso em 81 mil iterações (19/08/2026).
    HistoricalSale.objects.bulk_create([
        HistoricalSale(source="yooga", external_id=n, occurred_at=now - timedelta(minutes=n), total_q=100 * n)
        for n in range(1, 41)
    ] + [
        HistoricalSale(source="seed", external_id=1, occurred_at=now, total_q=300),
    ])

    executor = MigrationExecutor(connection)  # relê o grafo depois de andar
    executor.migrate(AFTER)
    new_apps = executor.loader.project_state(AFTER).apps
    ImportBatch = new_apps.get_model("backstage", "ImportBatch")
    HistoricalSale = new_apps.get_model("backstage", "HistoricalSale")

    # UM lote por origem — nem um a mais, seja qual for o número de instantes.
    assert ImportBatch.objects.count() == 2
    batches = {b.source: b for b in ImportBatch.objects.all()}
    assert set(batches) == {"yooga", "seed"}
    assert batches["yooga"].sales_created == 40
    assert batches["yooga"].file_sha256 == ""
    assert "anterior ao controle" in batches["yooga"].notes
    assert HistoricalSale.objects.filter(batch__isnull=True).count() == 0
    assert HistoricalSale.objects.filter(source="yooga", batch=batches["yooga"]).count() == 40
