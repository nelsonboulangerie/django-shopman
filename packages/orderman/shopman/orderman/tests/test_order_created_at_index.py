"""O pedido tem índice por ``created_at`` — e ele existe no banco, não só no ``Meta``.

B.I., destaques, cestas, PDV recente e a listagem padrão (``-created_at``) leem
pedidos por janela de data. Sem este índice, cada leitura varre a tabela inteira.
"""

from __future__ import annotations

import importlib

import pytest
from django.db import connection
from shopman.orderman.models import Order

INDEX_NAME = "ord_order_created_at_idx"


def test_meta_declares_created_at_index():
    indexes = {index.name: index for index in Order._meta.indexes}
    assert INDEX_NAME in indexes
    assert indexes[INDEX_NAME].fields == ["created_at"]


@pytest.mark.django_db
def test_index_exists_in_database_on_created_at():
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Order._meta.db_table)
    assert INDEX_NAME in constraints
    assert constraints[INDEX_NAME]["index"] is True
    assert constraints[INDEX_NAME]["columns"] == ["created_at"]


def test_migration_is_non_atomic_for_concurrent_build():
    module = importlib.import_module("shopman.orderman.migrations.0007_order_created_at_index")
    assert module.Migration.atomic is False
    (operation,) = module.Migration.operations
    assert operation.index.name == INDEX_NAME
