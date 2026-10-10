"""Conexão de banco sob ASGI: o SSE não prende conexão e o processo reaproveita.

Duas regressões, uma por metade do problema medido no ar:

1. O stream do ``django_eventstream`` lia o banco e segurava a conexão pela vida
   inteira do ``EventSource`` (bancada: 10 streams abertos, 10 conexões ociosas).
   Com pool, isso ESGOTA o pool: 8 streams levam as 8 conexões e o 9º request
   espera até dar ``PoolTimeout``. Por isso o conserto do SSE vem antes do pool.
2. Com ``DATABASE_CONN_MAX_AGE=0`` (o que o deploy usa, porque sob Daphne o
   ``CONN_MAX_AGE`` é por thread e não reaproveita nada), cada request abria uma
   conexão nova. O pool do psycopg é do processo e liga sozinho nesse caso.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
from pathlib import Path
from unittest import mock

import pytest
from django.http import StreamingHttpResponse

from config import settings as project_settings
from shopman.shop import eventstream

_SETTINGS_PATH = Path(project_settings.__file__)
_REPO = _SETTINGS_PATH.parent.parent


def _load_settings(monkeypatch, **env):
    # Mesmo cuidado do test_shopman_environment: o `.env` do dev não entra na prova.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    for name in (
        "DATABASE_URL",
        "DATABASE_CONN_MAX_AGE",
        "DATABASE_POOL_MAX_SIZE",
        "DATABASE_POOL_MIN_SIZE",
        "DATABASE_POOL_TIMEOUT",
        "DATABASE_POOL_MAX_IDLE",
        "DJANGO_DEBUG",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("shopman_settings_db_pool", _SETTINGS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DATABASES["default"]


_URL = "postgres://u:p@db.invalid:25061/shopman-pool"


class TestPoolSettings:
    def test_conn_max_age_zero_turns_on_the_process_pool(self, monkeypatch):
        db = _load_settings(monkeypatch, DATABASE_URL=_URL, DATABASE_CONN_MAX_AGE="0")
        pool = db["OPTIONS"]["pool"]
        assert db["CONN_MAX_AGE"] == 0
        assert pool["max_size"] == 8
        assert pool["min_size"] == 1
        assert pool["timeout"] == 10.0
        assert pool["max_idle"] == 300.0

    def test_pool_size_comes_from_env(self, monkeypatch):
        db = _load_settings(
            monkeypatch,
            DATABASE_URL=_URL,
            DATABASE_CONN_MAX_AGE="0",
            DATABASE_POOL_MAX_SIZE="4",
            DATABASE_POOL_MIN_SIZE="9",
        )
        assert db["OPTIONS"]["pool"]["max_size"] == 4
        # min nunca passa do max: o psycopg_pool recusaria o pool no boot.
        assert db["OPTIONS"]["pool"]["min_size"] == 4

    def test_pool_size_zero_turns_it_off_without_code_deploy(self, monkeypatch):
        db = _load_settings(
            monkeypatch, DATABASE_URL=_URL, DATABASE_CONN_MAX_AGE="0", DATABASE_POOL_MAX_SIZE="0"
        )
        assert "pool" not in db["OPTIONS"]

    def test_persistent_connections_never_combine_with_the_pool(self, monkeypatch):
        # O Django recusa os dois juntos ("Pooling doesn't support persistent
        # connections"); o default de dev (60) segue sem pool.
        db = _load_settings(monkeypatch, DATABASE_URL=_URL)
        assert db["CONN_MAX_AGE"] == 60
        assert "pool" not in db["OPTIONS"]

    def test_prepared_statements_stay_off_for_the_pgbouncer(self, monkeypatch):
        # O pool do deploy fala com PgBouncer em modo transaction: prepared
        # statement de servidor quebraria ("prepared statement does not exist").
        from django.db.backends.postgresql.base import DatabaseWrapper

        db = _load_settings(monkeypatch, DATABASE_URL=_URL, DATABASE_CONN_MAX_AGE="0")
        settings_dict = {
            **db,
            "TIME_ZONE": None,
            "AUTOCOMMIT": True,
            "ATOMIC_REQUESTS": False,
            "TEST": {},
        }
        params = DatabaseWrapper(settings_dict).get_connection_params()
        assert params["prepare_threshold"] is None
        assert "pool" not in params
        assert db["OPTIONS"].get("server_side_binding") is not True

    def test_pool_dependency_is_installed(self):
        # `psycopg[pool]` no pyproject, no Makefile e pinado no constraints.txt.
        import psycopg_pool  # noqa: F401


class TestSseReleasesTheConnection:
    def test_release_happens_before_the_stream_starts_and_after_each_chunk(self):
        calls: list[str] = []

        async def inner():
            calls.append("read-1")
            yield b"a"
            calls.append("read-2")
            yield b"b"

        def fake_release():
            calls.append("release")

        async def consume():
            out = []
            async for chunk in eventstream._release_between_reads(inner()):
                calls.append(f"sent-{chunk.decode()}")
                out.append(chunk)
            return out

        with mock.patch.object(eventstream, "release_db_connections", fake_release):
            assert asyncio.run(consume()) == [b"a", b"b"]
        # A conexão da view/middleware sai antes da 1ª leitura, e cada leitura
        # devolve a sua ANTES de o pedaço sair (o stream espera logo depois).
        assert calls == [
            "release",
            "read-1",
            "release",
            "sent-a",
            "read-2",
            "release",
            "sent-b",
        ]

    def test_events_wraps_only_async_streams(self, rf):
        async def body():
            yield b"x"

        streaming = StreamingHttpResponse(body(), content_type="text/event-stream")
        with mock.patch.object(eventstream, "_eventstream_events", return_value=streaming):
            response = eventstream.events(rf.get("/"), channels=["c"])
        assert response is streaming
        assert response.is_async
        assert response._iterator.ag_code.co_name == "_release_between_reads"

    def test_release_skips_connections_inside_atomic(self):
        open_conn = mock.Mock(connection=object(), in_atomic_block=False)
        atomic_conn = mock.Mock(connection=object(), in_atomic_block=True)
        idle_conn = mock.Mock(connection=None, in_atomic_block=False)
        with mock.patch.object(eventstream.connections, "all", return_value=[open_conn, atomic_conn, idle_conn]):
            eventstream.release_db_connections()
        open_conn.close.assert_called_once_with()
        atomic_conn.close.assert_not_called()
        idle_conn.close.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    def test_release_really_closes_an_open_connection(self):
        from django.db import connection

        if connection.vendor == "sqlite" and connection.is_in_memory_db():
            pytest.skip("o SQLite em memória da suíte ignora close() de propósito")
        connection.ensure_connection()
        assert connection.connection is not None
        eventstream.release_db_connections()
        assert connection.connection is None


def test_no_route_uses_the_raw_eventstream_view():
    """Toda rota SSE passa por ``shopman.shop.eventstream.events``.

    A view crua do ``django_eventstream`` segura a conexão de banco pela vida do
    stream. Só o próprio wrapper pode importá-la.
    """
    offenders = []
    for root in ("shopman", "config"):
        for path in (_REPO / root).rglob("*.py"):
            if "tests" in path.parts or path.name == "eventstream.py" and path.parent.name == "shop":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "django_eventstream.views":
                    if any(alias.name == "events" for alias in node.names):
                        offenders.append(str(path.relative_to(_REPO)))
    assert offenders == []


@pytest.mark.django_db
def test_sold_today_counts_the_local_day_by_instant_range():
    """``fomo.sold_today`` filtra por intervalo de instantes, não por ``__date``.

    O ``__date`` converte cada pedido para o fuso antes de comparar e deixa o
    índice ``ord_order_created_at_idx`` de fora. A troca não pode mudar a borda:
    o dia é o dia LOCAL da loja (00:00 às 23:59:59 em America/Sao_Paulo).
    """
    from datetime import date, datetime

    from django.utils import timezone as dj_tz
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.services import fomo

    day = date(2026, 10, 10)

    def order(ref, local_dt, status=Order.Status.COMPLETED, qty=1):
        o = Order.objects.create(ref=ref, channel_ref="pdv", status=status, total_q=100)
        OrderItem.objects.create(
            order=o, line_id="1", sku="PAO-FOMO", name="Pão", qty=qty, unit_price_q=100, line_total_q=100 * qty
        )
        Order.objects.filter(pk=o.pk).update(created_at=dj_tz.make_aware(local_dt))

    order("FOMO-1", datetime(2026, 10, 10, 0, 0, 5), qty=2)  # primeiro minuto do dia
    order("FOMO-2", datetime(2026, 10, 10, 23, 59, 55), qty=3)  # último minuto do dia
    order("FOMO-3", datetime(2026, 10, 9, 23, 59, 55), qty=7)  # ontem, no limite
    order("FOMO-4", datetime(2026, 10, 11, 0, 0, 0), qty=11)  # amanhã, no limite
    order("FOMO-5", datetime(2026, 10, 10, 12, 0), status=Order.Status.CANCELLED, qty=13)

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with mock.patch.object(dj_tz, "localdate", return_value=day), CaptureQueriesContext(connection) as ctx:
        assert fomo.sold_today("PAO-FOMO") == 5
    sql = " ".join(q["sql"] for q in ctx.captured_queries)
    # Postgres converte com AT TIME ZONE; SQLite com a função do Django. Nenhum dos dois.
    assert "AT TIME ZONE" not in sql
    assert "django_datetime_cast_date" not in sql
