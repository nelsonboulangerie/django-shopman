"""Request cancelado não leva conexão do pool embora (incidente do alpha, 14/10/2026).

O ``web-operator`` esgotou o pool do psycopg (8 conexões) e passou a responder
tudo com ``PoolTimeout`` depois de 10 s, até ser reiniciado. A causa medida em
bancada: cliente que desiste no meio do request (aba fechada, troca de página, o BFF
abortando o upstream do ``EventSource``) deixa a conexão aberta pela thread do request
fora do alcance do ``request_finished``. Cada desistência no momento errado era uma
conexão a menos, para sempre. ``shop/orphan_connections.py`` devolve ao pool a
conexão cuja thread dona já morreu.

As duas provas de ponta a ponta (ASGI de verdade, pool de verdade) precisam do
PostgreSQL e rodam no gate de runtime; as de unidade rodam em qualquer banco.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from unittest import mock

import pytest
from django.db import connection, connections
from django.http import HttpResponse
from django.test import override_settings
from django.urls import path

from shopman.shop import eventstream, orphan_connections

requires_postgres = pytest.mark.skipif(
    "sqlite" in connection.settings_dict.get("ENGINE", ""),
    reason="o pool do psycopg só existe no PostgreSQL",
)


# ── Unidade: a varredura ─────────────────────────────────────────────────────


class _FakeWrapper:
    alias = "default"

    def __init__(self, *, fail=False):
        self.connection = object()
        self.sharing = 0
        self.closed = 0
        self.fail = fail

    def inc_thread_sharing(self):
        self.sharing += 1

    def dec_thread_sharing(self):
        self.sharing -= 1

    def close(self):
        assert self.sharing == 1, "fechar o wrapper de outra thread exige o compartilhamento declarado"
        self.closed += 1
        if self.fail:
            raise RuntimeError("putconn falhou")
        self.connection = None


def _dead_thread():
    t = threading.Thread(target=lambda: None)
    t.start()
    t.join()
    return t


@pytest.fixture
def owners(monkeypatch):
    table = {}
    monkeypatch.setattr(orphan_connections, "_owners", table)
    return table


def test_connection_of_a_dead_thread_goes_back(owners):
    orphan = _FakeWrapper()
    owners[orphan] = _dead_thread()
    assert orphan_connections.reclaim_dead_thread_connections() == 1
    assert orphan.closed == 1
    assert orphan.sharing == 0
    assert owners == {}


def test_connection_of_a_live_thread_is_never_touched(owners):
    in_use = _FakeWrapper()
    owners[in_use] = threading.current_thread()
    assert orphan_connections.reclaim_dead_thread_connections() == 0
    assert in_use.closed == 0
    assert in_use in owners


def test_closed_connection_only_leaves_the_table(owners):
    done = _FakeWrapper()
    done.connection = None
    owners[done] = _dead_thread()
    assert orphan_connections.reclaim_dead_thread_connections() == 0
    assert done.closed == 0
    assert owners == {}


def test_a_failed_give_back_never_breaks_the_request(owners):
    broken = _FakeWrapper(fail=True)
    owners[broken] = _dead_thread()
    assert orphan_connections.reclaim_dead_thread_connections() == 0
    assert broken.sharing == 0


def test_receivers_are_wired_at_boot():
    from django.core.signals import request_started
    from django.db.backends.signals import connection_created

    def uids(signal):
        return {entry[0][0] for entry in signal.receivers}

    assert "shopman.orphan_connections.owner" in uids(connection_created)
    assert "shopman.orphan_connections.reclaim" in uids(request_started)


def test_owner_is_the_thread_that_opened_the_connection(owners):
    wrapper = _FakeWrapper()
    seen = {}

    def opener():
        orphan_connections.remember_owner(sender=None, connection=wrapper)
        seen["thread"] = threading.current_thread()

    t = threading.Thread(target=opener)
    t.start()
    t.join()
    assert owners[wrapper] is seen["thread"]


# ── Ponta a ponta: ASGI + pool do psycopg ───────────────────────────────────


def _db_view(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok")


urlpatterns = [
    path("db/", _db_view),
    path("events/", eventstream.events, {"channels": ["pooltest-main"]}),
]

_POOL_SIZE = 2
_POOL_TIMEOUT = 2.0


@contextlib.contextmanager
def _process_pool():
    """Liga o pool do processo (como ``config/settings.py`` com CONN_MAX_AGE=0)."""
    settings_dict = connections.settings["default"]
    saved = settings_dict["OPTIONS"], settings_dict["CONN_MAX_AGE"]
    connections["default"].close()
    settings_dict["OPTIONS"] = {
        **saved[0],
        "pool": {"min_size": 0, "max_size": _POOL_SIZE, "timeout": _POOL_TIMEOUT},
    }
    settings_dict["CONN_MAX_AGE"] = 0
    try:
        yield connections["default"].pool
    finally:
        connections["default"].close()
        connections["default"].close_pool()
        settings_dict["OPTIONS"], settings_dict["CONN_MAX_AGE"] = saved


def _scope(path_):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path_,
        "raw_path": path_.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"accept", b"text/event-stream")],
        "client": ("127.0.0.1", 40000),
        "server": ("testserver", 80),
    }


class _Client:
    """Um cliente HTTP falando ASGI direto com o ``ASGIHandler`` do Django."""

    def __init__(self, handler, path_):
        self.gone = asyncio.Event()
        self.sent: list[dict] = []
        self._asked = False
        self.task = asyncio.ensure_future(handler(_scope(path_), self._receive, self._send))

    async def _receive(self):
        if not self._asked:
            self._asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message):
        self.sent.append(message)

    @property
    def status(self):
        return next((m["status"] for m in self.sent if m["type"] == "http.response.start"), None)

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")


def _serve(scenario, *args):
    """Roda o cenário num loop próprio, numa thread sem banco, como o daphne."""
    out = {}

    def target():
        try:
            out["value"] = asyncio.run(scenario(*args))
        except BaseException as exc:  # noqa: BLE001 — repassado ao teste
            out["error"] = exc

    t = threading.Thread(target=target, name="asgi-loop")
    t.start()
    t.join(timeout=60)
    if "error" in out:
        raise out["error"]
    return out["value"]


async def _get(handler, path_):
    client = _Client(handler, path_)
    started = time.monotonic()
    await asyncio.wait_for(client.task, timeout=_POOL_TIMEOUT * 3)
    return client.status, time.monotonic() - started


def _leave_an_orphan():
    """O que a thread de um request cancelado deixa: conexão do pool aberta, sem dono.

    Na bancada de 14/10 (daphne + pilha de middlewares do deploy): o cliente desiste,
    o Django dá o ``request_finished`` do request, e a thread, que não se cancela,
    segue e abre a conexão (sessão, usuário) depois disso. Acertar essa janela exige
    centenas de desistências contra um daphne; o estado que ela produz é este, e é
    dele que o pool precisa sair vivo.
    """

    def work():
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")

    t = threading.Thread(target=work, name="cancelled-request")
    t.start()
    t.join(timeout=10)


def _checked_out(pool) -> int:
    stats = pool.get_stats()
    return stats.get("pool_size", 0) - stats.get("pool_available", 0)


@requires_postgres
@pytest.mark.django_db(transaction=True)
@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=[])
def test_orphaned_connections_do_not_drain_the_pool():
    from django.core.handlers.asgi import ASGIHandler

    async def one_request():
        return await _get(ASGIHandler(), "/db/")

    with _process_pool() as pool:
        answers = []
        for _ in range(_POOL_SIZE * 3):  # três vezes mais órfãs que conexões no pool
            _leave_an_orphan()
            answers.append(_serve(one_request))
        _serve(one_request)  # a varredura roda no começo de cada request
        leaked = _checked_out(pool)
    assert [status for status, _ in answers] == [200] * len(answers)
    slowest = max(elapsed for _, elapsed in answers)
    assert slowest < _POOL_TIMEOUT, f"um request comum esperou o pool ({slowest:.1f} s)"
    assert leaked == 0


@requires_postgres
@pytest.mark.django_db(transaction=True)
@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=[])
def test_more_sse_streams_than_pool_connections_keep_requests_answering():
    from django.core.handlers.asgi import ASGIHandler
    from django_eventstream.views import get_listener_manager

    async def scenario(pool):
        handler = ASGIHandler()
        streams = [_Client(handler, "/events/") for _ in range(_POOL_SIZE + 3)]
        deadline = time.monotonic() + 5
        while not all(b"stream-open" in s.body for s in streams):
            assert time.monotonic() < deadline, "os streams não abriram"
            await asyncio.sleep(0.01)
        held = _checked_out(pool)
        status, elapsed = await _get(handler, "/db/")
        for s in streams:
            s.gone.set()
        await asyncio.wait_for(asyncio.gather(*(s.task for s in streams)), timeout=5)
        listeners = sum(len(v) for v in get_listener_manager().listeners_by_channel.values())
        return held, status, elapsed, listeners

    # Sem Redis neste loop: o ouvinte de Redis é do processo e não sobrevive ao asyncio.run.
    with mock.patch.object(get_listener_manager(), "redis_listener", None), _process_pool() as pool:
        held, status, elapsed, listeners = _serve(scenario, pool)
    assert held == 0, "stream SSE aberto não pode segurar conexão do pool"
    assert status == 200
    assert elapsed < _POOL_TIMEOUT
    assert listeners == 0, "cliente que saiu não deixa ouvinte para trás"
