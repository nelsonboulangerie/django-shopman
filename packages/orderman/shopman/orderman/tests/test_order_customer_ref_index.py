"""O histórico do cliente filtra Order.data.customer_ref, e o índice existe no banco.

services/history.py filtra por Order.objects.filter(data__customer_ref=...). Sem
índice, o Postgres faz Seq Scan em orderman_order. O ORM emite o filtro como
(data -> customer_ref) = valor jsonb, então o índice é sobre KeyTransform (jsonb),
e não KeyTextTransform (->>): o índice ->> não é usado pelo planner.
"""

from __future__ import annotations

import importlib

import pytest
from django.db import connection
from shopman.orderman.models import Order

INDEX_NAME = "ord_order_customer_ref_idx"


def test_meta_declares_customer_ref_index():
    indexes = {index.name: index for index in Order._meta.indexes}
    assert INDEX_NAME in indexes
    (expression,) = indexes[INDEX_NAME].expressions
    assert type(expression).__name__ == "KeyTransform"


def test_migration_is_non_atomic_and_uses_key_transform():
    module = importlib.import_module("shopman.orderman.migrations.0008_order_customer_ref_index")
    assert module.Migration.atomic is False
    (operation,) = module.Migration.operations
    assert operation.index.name == INDEX_NAME
    (expression,) = operation.index.expressions
    assert type(expression).__name__ == "KeyTransform"


@pytest.mark.django_db
def test_index_exists_in_database_on_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("índice de expressão jsonb só existe no Postgres")
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s", [INDEX_NAME])
        row = cursor.fetchone()
    assert row is not None, f"índice {INDEX_NAME} ausente no banco"
    assert "data -> 'customer_ref'" in row[0]
