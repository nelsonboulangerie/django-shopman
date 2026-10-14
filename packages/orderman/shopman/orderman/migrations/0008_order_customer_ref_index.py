"""Índice de expressão em data -> customer_ref de orderman_order.

O histórico do cliente (services/history.py) filtra por
Order.objects.filter(data__customer_ref=...): sem índice o Postgres faz Seq Scan
na tabela inteira (15.311/dia medidos no alpha). O dado já vive no JSON, então o
índice de expressão resolve sem campo novo.

O ORM emite o filtro como (data -> customer_ref) = valor jsonb (não ->> texto):
por isso o índice é sobre KeyTransform (jsonb), e não KeyTextTransform.

No Postgres o índice nasce com CREATE INDEX CONCURRENTLY: a tabela recebe venda
durante o deploy e o CREATE INDEX comum bloquearia os INSERTs. CONCURRENTLY não
roda dentro de transação, daí atomic = False.

A operação é o AddIndexConcurrently do Django sem importar django.contrib.postgres:
aquele módulo exige o driver do Postgres no import e o shopman-orderman depende só
do Django (a suíte do pacote roda em SQLite). Nos bancos que não são Postgres o
índice nasce pelo AddIndex comum; o estado da migração é o mesmo nos dois caminhos.

Se um CONCURRENTLY anterior morreu no meio (timeout, deploy cancelado), o Postgres
deixa o índice INVÁLIDO com o nome ocupado, e todo release seguinte falharia com
"already exists". O caminho do Postgres remove essa sobra antes de criar.
"""

from django.db import NotSupportedError, migrations, models
from django.db.models.fields.json import KeyTransform

INDEX_NAME = "ord_order_customer_ref_idx"


class AddIndexConcurrentlyOnPostgres(migrations.AddIndex):
    """CREATE INDEX CONCURRENTLY no Postgres; AddIndex comum nos demais."""

    atomic = False

    def describe(self):
        return f"Create index {self.index.name} on {self.model_name} (concurrently on PostgreSQL)"

    @staticmethod
    def _is_postgres(schema_editor):
        return schema_editor.connection.vendor == "postgresql"

    @staticmethod
    def _ensure_not_in_transaction(schema_editor):
        if schema_editor.connection.in_atomic_block:
            raise NotSupportedError(
                "CREATE/DROP INDEX CONCURRENTLY cannot run inside a transaction "
                "(set atomic = False on the migration)."
            )

    @staticmethod
    def _drop_invalid_leftover(schema_editor, index_name):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = %s AND NOT i.indisvalid",
                [index_name],
            )
            leftover = cursor.fetchone() is not None
        if leftover:
            schema_editor.execute(
                f"DROP INDEX CONCURRENTLY IF EXISTS {schema_editor.quote_name(index_name)}"
            )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if not self._is_postgres(schema_editor):
            return super().database_forwards(app_label, schema_editor, from_state, to_state)
        self._ensure_not_in_transaction(schema_editor)
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            self._drop_invalid_leftover(schema_editor, self.index.name)
            schema_editor.add_index(model, self.index, concurrently=True)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if not self._is_postgres(schema_editor):
            return super().database_backwards(app_label, schema_editor, from_state, to_state)
        self._ensure_not_in_transaction(schema_editor)
        model = from_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            schema_editor.remove_index(model, self.index, concurrently=True)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("orderman", "0007_order_created_at_index")]

    operations = [
        AddIndexConcurrentlyOnPostgres(
            model_name="order",
            index=models.Index(
                KeyTransform("customer_ref", "data"),
                name=INDEX_NAME,
            ),
        ),
    ]
