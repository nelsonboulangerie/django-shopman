"""Observabilidade de baixo custo para a projeção do cardápio.

Dois tipos de estágio no ``Server-Timing``:

- **Estágios da view** (``projection``, ``availability``, ``personalization``,
  ``shadow``): abertos à mão com :func:`catalog_stage` em volta de um trecho.
- **Custo fixo do request** (``db``, ``connect``, ``cache``, ``gc``): medidos por
  sondas que somam ao request que os causou, sem ninguém abrir estágio.

``db`` é o SQL (wrapper de execução do Django). ``connect`` é a ABERTURA de
conexão de banco, que o ``db`` não vê: o ``connect()`` acontece ao criar o cursor,
antes do wrapper de execução. ``cache`` é o tempo e o número de chamadas ao cache
(``RedisCache`` em produção: cada chamada é uma ida e volta ao Redis, e a
primeira do request inclui abrir a conexão). ``gc`` é a coleta de lixo que
disparou durante o request (pausa do processo inteiro, contada para quem a
disparou). Os três aparecem com ``desc="<n>"``: conexões abertas, chamadas ao
cache, coletas. Todos ficam DENTRO de ``projection`` (são parte dela, não somam a
ela) e não se somam entre si de forma exata: uma coleta pode cair no meio de uma
consulta.

As sondas de ``connect`` e ``cache`` envolvem, uma vez por classe, o método da
classe do backend em uso (``connect`` do wrapper de banco; ``get``/``set``/... do
cache); a de ``gc`` é um ``gc.callbacks``. Fora de uma captura o custo é um
``ContextVar.get()`` por chamada. O estado vive no ``ContextVar`` do request, nunca
no objeto envolvido: sob ASGI cada request tem o seu contexto e nada vaza de um
para o outro.
"""

from __future__ import annotations

import functools
import gc
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from django.core.cache import DEFAULT_CACHE_ALIAS, caches
from django.db import DEFAULT_DB_ALIAS, connection, connections

logger = logging.getLogger("shopman.storefront.continuum")

#: Estágios da view, na ordem do header (o formato que o cardápio já publicava).
VIEW_STAGES = ("projection", "availability", "personalization", "shadow", "db")
#: Custo fixo do request: carregam ``desc`` com a contagem.
FIXED_COST_STAGES = ("connect", "cache", "gc")

#: Métodos públicos do cache que viram ida ao backend. Os ``a*`` assíncronos do
#: ``BaseCache`` caem nestes; ``get_or_set`` chama ``get``/``add`` por dentro e é
#: contado uma vez só (a sonda não conta a si mesma aninhada).
CACHE_METHODS = (
    "get",
    "get_many",
    "get_or_set",
    "set",
    "set_many",
    "add",
    "touch",
    "delete",
    "delete_many",
    "has_key",
    "incr",
    "decr",
    "clear",
)


@dataclass
class CatalogTiming:
    durations_ms: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    query_count: int = 0
    # Sondas abertas agora neste request: impede contar duas vezes a chamada que
    # chama a si mesma (``get_or_set`` → ``get``) ou a subclasse envolvida por cima
    # da classe-mãe já envolvida.
    _open_probes: set[str] = field(default_factory=set, repr=False)

    def add(self, name: str, duration_ms: float) -> None:
        self.durations_ms[name] += max(0.0, duration_ms)

    def server_timing(self, *, include_bff: bool = False) -> str:
        names = list(VIEW_STAGES)
        if include_bff:
            names.insert(0, "bff")
        parts = [f"{name};dur={self.durations_ms.get(name, 0.0):.2f}" for name in names]
        parts.extend(
            f'{name};dur={self.durations_ms.get(name, 0.0):.2f};desc="{self.counts.get(name, 0)}"'
            for name in FIXED_COST_STAGES
        )
        return ", ".join(parts)

    def fixed_cost_fields(self) -> dict[str, float | int]:
        """Os três estágios de custo fixo, no formato de :func:`log_catalog_observation`."""
        return {
            "connect_ms": self.durations_ms.get("connect", 0.0),
            "connect_count": self.counts.get("connect", 0),
            "cache_ms": self.durations_ms.get("cache", 0.0),
            "cache_calls": self.counts.get("cache", 0),
            "gc_ms": self.durations_ms.get("gc", 0.0),
            "gc_count": self.counts.get("gc", 0),
        }


_current: ContextVar[CatalogTiming | None] = ContextVar("catalog_timing", default=None)


@contextmanager
def catalog_stage(name: str) -> Iterator[None]:
    timing = _current.get()
    started = time.perf_counter()
    try:
        yield
    finally:
        if timing is not None:
            timing.add(name, (time.perf_counter() - started) * 1000)


# ── Sondas de custo fixo ─────────────────────────────────────────────────────

_PROBE_MARK = "_shopman_server_timing_probe"
_install_lock = threading.Lock()


def _probe(stage: str, original: Callable) -> Callable:
    @functools.wraps(original)
    def probed(self, *args, **kwargs):
        timing = _current.get()
        if timing is None or stage in timing._open_probes:
            return original(self, *args, **kwargs)
        timing._open_probes.add(stage)
        started = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            timing._open_probes.discard(stage)
            timing.add(stage, (time.perf_counter() - started) * 1000)
            timing.counts[stage] += 1

    return probed


def _install_probe(cls: type, stage: str, method_names: tuple[str, ...]) -> None:
    """Envolve ``method_names`` de ``cls`` uma vez (idempotente, por classe)."""
    if cls.__dict__.get(_PROBE_MARK):
        return
    with _install_lock:
        if cls.__dict__.get(_PROBE_MARK):
            return
        for name in method_names:
            original = getattr(cls, name, None)
            if callable(original):
                setattr(cls, name, _probe(stage, original))
        setattr(cls, _PROBE_MARK, True)


# Início da coleta em curso. A coleta de lixo não roda em paralelo consigo mesma
# (o coletor segura o GIL do começo ao fim), então um valor de módulo basta.
_gc_started: float | None = None


def _gc_probe(phase: str, info: dict) -> None:
    global _gc_started
    if phase == "start":
        _gc_started = time.perf_counter() if _current.get() is not None else None
        return
    started, _gc_started = _gc_started, None
    timing = _current.get()
    if started is None or timing is None:
        return
    timing.add("gc", (time.perf_counter() - started) * 1000)
    timing.counts["gc"] += 1


def _install_probes() -> None:
    _install_probe(type(connections[DEFAULT_DB_ALIAS]), "connect", ("connect",))
    _install_probe(type(caches[DEFAULT_CACHE_ALIAS]), "cache", CACHE_METHODS)
    if _gc_probe not in gc.callbacks:
        with _install_lock:
            if _gc_probe not in gc.callbacks:
                gc.callbacks.append(_gc_probe)


@contextmanager
def capture_catalog_timing() -> Iterator[CatalogTiming]:
    _install_probes()
    timing = CatalogTiming()
    token = _current.set(timing)

    def count_query(execute, sql, params, many, context):
        started = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            timing.query_count += 1
            timing.add("db", (time.perf_counter() - started) * 1000)

    try:
        with connection.execute_wrapper(count_query):
            yield timing
    finally:
        _current.reset(token)


class ServerTimingMixin:
    """Carimba ``Server-Timing`` numa view de leitura, no MESMO formato do cardápio.

    O valor do header é ser comparável entre rotas: por isso reusa
    ``capture_catalog_timing`` e os nomes de ``CatalogTiming``, sem formato
    próprio. ``projection`` é a view inteira; ``availability`` e
    ``personalization`` aparecem quando a view passa por ``build_catalog`` (a
    home passa); ``db`` é a soma do SQL do request; ``connect``, ``cache`` e
    ``gc`` são o custo fixo (ver o docstring do módulo). Só leitura (GET/HEAD):
    mutação não é o que este header mede.

    Não use em view que já abre a própria captura (cardápio, Continuum): a
    captura aninhada contaria o SQL duas vezes.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.method not in ("GET", "HEAD"):
            return super().dispatch(request, *args, **kwargs)
        with capture_catalog_timing() as timing:
            with catalog_stage("projection"):
                response = super().dispatch(request, *args, **kwargs)
        response["Server-Timing"] = timing.server_timing()
        return response


def log_catalog_observation(**fields) -> None:
    """Loga somente métricas agregadas; nunca payload, SKU, sessão ou pessoa."""
    safe = {
        key: value
        for key, value in fields.items()
        if key in {
            "path",
            "mode",
            "status",
            "query_count",
            "response_bytes",
            "snapshot_bytes",
            "cache_status",
            "snapshot_sequence",
            "snapshot_age_ms",
            "shadow_equal",
            "shadow_error",
            "shadow_ms",
            "shadow_query_count",
            "projection_ms",
            "availability_ms",
            "personalization_ms",
            "db_ms",
            "connect_ms",
            "connect_count",
            "cache_ms",
            "cache_calls",
            "gc_ms",
            "gc_count",
        }
    }
    # Campos numéricos precisam permanecer tipos numéricos. Interpolar o dict na
    # mensagem transforma durações em texto e o redactor de PII pode confundir a
    # sequência com telefone; extras estruturados passam pelo mesmo redactor sem
    # perder o valor da métrica.
    logger.info("storefront_catalog_observation", extra=safe)
