"""O processo se cura sozinho: liveness do pool e higiene dos streams SSE.

Pedido do dono depois do incidente de 14/10/2026 (``web-operator`` travado no pool
até alguém reiniciar): não haverá webmaster. A liveness passa a falhar quando o pool
DESTE processo trava com o banco respondendo, e só aí; banco fora nunca vira loop de
reinício. E o SSE ganha vida máxima e teto por sessão.

Os de pool real precisam do PostgreSQL e rodam no gate de runtime.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from django.db import connection
from django.http import StreamingHttpResponse
from django.test import Client, override_settings
from django.urls import reverse

from shopman.shop import eventstream, pool_liveness

requires_postgres = pytest.mark.skipif(
    "sqlite" in connection.settings_dict.get("ENGINE", ""),
    reason="o pool do psycopg só existe no PostgreSQL",
)


@pytest.fixture(autouse=True)
def _fresh_liveness():
    pool_liveness.reset()
    yield
    pool_liveness.reset()


# ── Liveness: a regra ────────────────────────────────────────────────────────


class _FakePool:
    def __init__(self, *, hands_out: bool):
        self.hands_out = hands_out
        self.returned = 0

    def getconn(self, timeout=None):
        if not self.hands_out:
            raise TimeoutError("couldn't get a connection")
        return object()

    def putconn(self, conn):
        self.returned += 1

    def get_stats(self):
        return {"pool_available": 0, "pool_size": 8, "requests_waiting": 3}


def _live(client):
    return client.get(reverse("health-live"))


def test_live_stays_200_while_the_pool_hands_out_connections(monkeypatch):
    pool = _FakePool(hands_out=True)
    monkeypatch.setattr(pool_liveness, "_process_pool", lambda: pool)
    response = _live(Client())
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"process": "ok"}}
    assert pool.returned == 1, "a conexão da sonda volta ao pool"


@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=0)
def test_stuck_pool_with_database_up_fails_liveness(monkeypatch):
    monkeypatch.setattr(pool_liveness, "_process_pool", lambda: _FakePool(hands_out=False))
    monkeypatch.setattr(pool_liveness, "_database_answers_directly", lambda: True)
    response = _live(Client())
    assert response.status_code == 503
    assert response.json()["checks"] == {"process": "ok", "pool": "fail"}


@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=0)
def test_stuck_pool_with_database_down_never_fails_liveness(monkeypatch):
    monkeypatch.setattr(pool_liveness, "_process_pool", lambda: _FakePool(hands_out=False))
    monkeypatch.setattr(pool_liveness, "_database_answers_directly", lambda: False)
    response = _live(Client())
    assert response.status_code == 200


@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=60)
def test_a_short_wait_for_the_pool_is_load_not_a_stuck_process(monkeypatch):
    direct = []
    monkeypatch.setattr(pool_liveness, "_process_pool", lambda: _FakePool(hands_out=False))
    monkeypatch.setattr(pool_liveness, "_database_answers_directly", lambda: direct.append(1) or True)
    assert _live(Client()).status_code == 200
    assert direct == [], "dentro da janela nem a conexão direta é aberta"


@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=60)
def test_recovery_resets_the_window(monkeypatch):
    stuck = _FakePool(hands_out=False)
    monkeypatch.setattr(pool_liveness, "_process_pool", lambda: stuck)
    monkeypatch.setattr(pool_liveness, "_database_answers_directly", lambda: True)
    _live(Client())
    assert pool_liveness._stuck_since is not None
    stuck.hands_out = True
    _live(Client())
    assert pool_liveness._stuck_since is None


def test_without_pool_liveness_is_process_only(db, django_assert_num_queries):
    # SQLite / DATABASE_POOL_MAX_SIZE=0: nada a medir, zero consulta.
    with django_assert_num_queries(0):
        assert _live(Client()).status_code == 200


# ── Liveness: pool e banco de verdade ───────────────────────────────────────


@requires_postgres
@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=0)
def test_real_exhausted_pool_fails_liveness_and_releasing_it_recovers(monkeypatch):
    from shopman.shop.tests.test_orphan_connections import _POOL_SIZE, _process_pool

    monkeypatch.setattr(pool_liveness, "POOL_PROBE_TIMEOUT_SECONDS", 0.3)
    with _process_pool() as pool:
        pool.open(wait=True)
        held = [pool.getconn() for _ in range(_POOL_SIZE)]  # o processo travado
        try:
            stuck = _live(Client())
        finally:
            for conn in held:
                pool.putconn(conn)
        healed = _live(Client())
    assert stuck.status_code == 503
    assert stuck.json()["checks"]["pool"] == "fail"
    assert healed.status_code == 200


@requires_postgres
@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_LIVENESS_POOL_STUCK_SECONDS=0)
def test_real_exhausted_pool_with_database_unreachable_keeps_liveness(monkeypatch):
    """Banco fora: a conexão direta não chega, e a liveness NÃO pede reinício."""
    from django.db import connections

    from shopman.shop.tests.test_orphan_connections import _POOL_SIZE, _process_pool

    monkeypatch.setattr(pool_liveness, "POOL_PROBE_TIMEOUT_SECONDS", 0.3)
    wrapper = connections["default"]
    real_params = wrapper.get_connection_params

    def unreachable():
        params = real_params()
        params.update(host="127.0.0.1", port=1)  # ninguém escuta: o banco "caiu"
        return params

    with _process_pool() as pool:
        pool.open(wait=True)
        held = [pool.getconn() for _ in range(_POOL_SIZE)]
        monkeypatch.setattr(wrapper, "get_connection_params", unreachable)
        try:
            response = _live(Client())
        finally:
            monkeypatch.undo()
            for conn in held:
                pool.putconn(conn)
    assert response.status_code == 200


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_direct_probe_really_reaches_the_database():
    assert pool_liveness._database_answers_directly() is True


# ── SSE: vida máxima e teto por sessão ──────────────────────────────────────


def test_stream_ends_at_max_lifetime_and_frees_its_slot():
    finished = []

    async def endless():
        try:
            yield b"open"
            await asyncio.sleep(3600)  # esperando evento que não vem
            yield b"never"
        finally:
            finished.append(True)  # o django_eventstream remove o listener aqui

    async def consume():
        chunks = []
        started = time.monotonic()
        stream = eventstream._release_between_reads(endless(), max_lifetime=0.2, session_key="s1")
        async for chunk in stream:
            chunks.append(chunk)
            assert eventstream.open_streams("s1") == 1
        return chunks, time.monotonic() - started

    from unittest import mock

    with mock.patch.object(eventstream, "release_db_connections", lambda: None):
        chunks, elapsed = asyncio.run(consume())
    assert chunks == [b"open"]
    assert elapsed < 2
    assert finished == [True], "o stream interno foi fechado (listener removido)"
    assert eventstream.open_streams("s1") == 0


@override_settings(SHOPMAN_SSE_MAX_STREAMS_PER_SESSION=2)
def test_session_over_the_cap_gets_429_without_touching_the_stream(rf, monkeypatch):
    from unittest import mock

    request = rf.get("/events/kds/")
    request.COOKIES["sessionid"] = "abc"
    key = eventstream._session_bucket(request)
    monkeypatch.setitem(eventstream._open_streams, key, 2)
    with mock.patch.object(eventstream, "_eventstream_events") as raw:
        response = eventstream.events(request, channels=["c"])
    assert response.status_code == 429
    raw.assert_not_called()


@override_settings(SHOPMAN_SSE_MAX_STREAMS_PER_SESSION=2)
def test_session_under_the_cap_streams_normally(rf):
    from unittest import mock

    async def body():
        yield b"x"

    request = rf.get("/events/kds/")
    request.COOKIES["sessionid"] = "abc-under"
    streaming = StreamingHttpResponse(body(), content_type="text/event-stream")
    with mock.patch.object(eventstream, "_eventstream_events", return_value=streaming):
        response = eventstream.events(request, channels=["c"])
    assert response is streaming
    assert response._iterator.ag_code.co_name == "_release_between_reads"


def test_session_bucket_never_keeps_the_raw_cookie(rf):
    request = rf.get("/")
    request.COOKIES["sessionid"] = "segredo-da-sessao"
    bucket = eventstream._session_bucket(request)
    assert bucket and "segredo" not in bucket
    assert eventstream._session_bucket(rf.get("/")) is None
