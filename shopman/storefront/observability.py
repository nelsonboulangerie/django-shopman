"""Observabilidade de baixo custo para a projeção do cardápio."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from django.db import connection

logger = logging.getLogger("shopman.storefront.continuum")


@dataclass
class CatalogTiming:
    durations_ms: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    query_count: int = 0

    def add(self, name: str, duration_ms: float) -> None:
        self.durations_ms[name] += max(0.0, duration_ms)

    def server_timing(self, *, include_bff: bool = False) -> str:
        names = ["projection", "availability", "personalization", "db"]
        if include_bff:
            names.insert(0, "bff")
        return ", ".join(
            f"{name};dur={self.durations_ms.get(name, 0.0):.2f}"
            for name in names
        )


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


@contextmanager
def capture_catalog_timing() -> Iterator[CatalogTiming]:
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
            "cache_status",
            "snapshot_sequence",
            "snapshot_age_ms",
            "shadow_equal",
            "projection_ms",
            "availability_ms",
            "personalization_ms",
            "db_ms",
        }
    }
    # Campos numéricos precisam permanecer tipos numéricos. Interpolar o dict na
    # mensagem transforma durações em texto e o redactor de PII pode confundir a
    # sequência com telefone; extras estruturados passam pelo mesmo redactor sem
    # perder o valor da métrica.
    logger.info("storefront_catalog_observation", extra=safe)
