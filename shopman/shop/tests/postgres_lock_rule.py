"""A regra de lock do PostgreSQL, aplicada à suíte que roda em SQLite.

O PostgreSQL recusa ``FOR UPDATE`` no lado anulável de um OUTER JOIN ("FOR UPDATE
cannot be applied to the nullable side of an outer join"). O SQLite ignora ``FOR
UPDATE`` em silêncio, então ``select_for_update()`` + ``select_related("<fk
anulável>")`` passava verde aqui e quebrava no alpha (pulso da gaveta, #1640,
10/10/2026).

``install()`` (chamado pelo ``shopman/conftest.py``) envolve o compilador SQL do
Django: toda consulta ``FOR UPDATE`` que a suíte executa é conferida contra o
``FROM`` que de fato foi emitido. Por isso pega também a consulta montada em
etapas, a relação aninhada (``a__b``) e o filtro ``__isnull`` que promove o JOIN
a OUTER, coisas que nenhuma varredura de texto enxerga. A correção é travar só o
que precisa: ``select_for_update(of=("self",))``.

O que fica de fora: caminho de código que nenhum teste executa. Para esse, a rede
é o ``scripts/run_runtime_tests.py``, que roda os testes ``requires_postgres``
contra o PostgreSQL real.
"""

from __future__ import annotations

from django.db.models.sql import compiler as sql_compiler
from django.db.models.sql.constants import LOUTER


class PostgresForUpdateOuterJoinError(AssertionError):
    """``FOR UPDATE`` que o PostgreSQL recusaria, pego já no SQLite da suíte."""


def locked_outer_join_aliases(compiler) -> list[str]:
    """Aliases travados que entraram no ``FROM`` por ``LEFT OUTER JOIN``.

    ``FOR UPDATE`` sem ``OF`` trava TODAS as tabelas do ``FROM``; com ``OF`` trava
    só as listadas.
    """
    query = compiler.query
    emitted = getattr(compiler, "_emitted_from_aliases", {})
    if query.select_for_update_of:
        locked = {arg.strip('"') for arg in compiler.get_select_for_update_of_arguments()}
    else:
        locked = set(emitted)
    return sorted(alias for alias in locked if getattr(emitted.get(alias), "join_type", None) == LOUTER)


_original_as_sql = sql_compiler.SQLCompiler.as_sql
_original_get_from_clause = sql_compiler.SQLCompiler.get_from_clause


def _get_from_clause_remembering_aliases(self):
    # O ``as_sql`` zera as contagens de referência ao sair; o ``FROM`` que de fato
    # foi emitido só é visível aqui dentro.
    query = self.query
    self._emitted_from_aliases = {
        alias: join for alias, join in query.alias_map.items() if query.alias_refcount.get(alias)
    }
    return _original_get_from_clause(self)


def _as_sql_with_postgres_lock_rule(self, *args, **kwargs):
    result = _original_as_sql(self, *args, **kwargs)
    if (
        self.query.select_for_update
        and self.connection.vendor != "postgresql"
        and type(self) is sql_compiler.SQLCompiler
    ):
        offenders = locked_outer_join_aliases(self)
        if offenders:
            raise PostgresForUpdateOuterJoinError(
                "select_for_update() trava tabela no lado anulável de um OUTER JOIN "
                f"({', '.join(offenders)}) em {self.query.model.__name__}; o PostgreSQL "
                'recusa. Use select_for_update(of=("self",)) ou trave só o que entra por INNER JOIN.'
            )
    return result


def install() -> None:
    """Idempotente: liga a regra uma vez por processo (cada worker do xdist)."""
    if sql_compiler.SQLCompiler.as_sql is _as_sql_with_postgres_lock_rule:
        return
    sql_compiler.SQLCompiler.get_from_clause = _get_from_clause_remembering_aliases
    sql_compiler.SQLCompiler.as_sql = _as_sql_with_postgres_lock_rule


def pytest_configure(config) -> None:
    """Também serve de plugin: ``pytest -p shopman.shop.tests.postgres_lock_rule``
    liga a mesma regra nas suítes dos pacotes do Core, que têm conftest próprio."""
    install()
