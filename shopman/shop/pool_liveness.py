"""A liveness sabe quando ESTE processo travou no pool de banco, e só isso.

Sem webmaster, o processo precisa se fazer reiniciar sozinho quando trava. O
incidente de 14/10/2026 foi exatamente esse: o pool do psycopg do ``web-operator``
esgotou, todo request esperava 10 s e caía, e a liveness (``/health/live/``,
sem banco de propósito) seguia 200, então a plataforma nunca reiniciou nada.

A regra tem duas metades, e as duas precisam valer para a liveness falhar:

1. **o pool deste processo não entrega conexão**: um ``getconn`` curto falha, e
   continua falhando há pelo menos ``SHOPMAN_LIVENESS_POOL_STUCK_SECONDS``
   (carga normal entrega conexão em milissegundos; um pico passa em segundos);
2. **o banco responde por fora do pool**: uma conexão nova, direta, faz ``SELECT 1``.

Banco fora ou lento falha a metade 2: a liveness segue 200, e quem tira a instância
da rota é a readiness (``/health/database/``). Reiniciar não conserta banco, e um
loop de reinício com banco fora só tiraria o processo que vai voltar a funcionar
quando o banco voltar. Processo travado é o contrário: o banco está bem, o processo
não, e reiniciar é o remédio.

Sem pool (``DATABASE_POOL_MAX_SIZE=0``, SQLite dos testes) não há o que medir: a
liveness continua só "o processo atende".
"""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections

logger = logging.getLogger(__name__)

#: Quanto o ``getconn`` da sonda espera. Pequeno: a sonda da plataforma tem 5 s.
POOL_PROBE_TIMEOUT_SECONDS = 1.5
#: Quanto a conexão direta tem para conectar e responder ``SELECT 1``.
DIRECT_PROBE_TIMEOUT_SECONDS = 2.0

_lock = threading.Lock()
_stuck_since: float | None = None


def _stuck_seconds() -> float:
    return float(getattr(settings, "SHOPMAN_LIVENESS_POOL_STUCK_SECONDS", 30))


def _pool_hands_out_a_connection(pool) -> bool:
    try:
        conn = pool.getconn(timeout=POOL_PROBE_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — PoolTimeout, ou o pool não consegue conectar
        logger.debug("liveness pool probe got no connection", exc_info=True)
        return False
    pool.putconn(conn)
    return True


def _database_answers_directly() -> bool:
    """Conexão nova, fora do pool, com prazo; o resultado sai de uma thread à parte.

    Se o banco (ou o PgBouncer) estiver lento, a resposta não chega no prazo e conta
    como banco fora: a liveness não reinicia o processo por culpa do banco.
    """
    import psycopg

    params = connections[DEFAULT_DB_ALIAS].get_connection_params()
    result: dict[str, bool] = {}

    def probe():
        try:
            with psycopg.connect(**params, connect_timeout=max(1, int(DIRECT_PROBE_TIMEOUT_SECONDS))) as conn:
                conn.execute("SELECT 1").fetchone()
            result["ok"] = True
        except Exception:  # noqa: BLE001
            logger.debug("liveness direct database probe failed", exc_info=True)
            result["ok"] = False

    t = threading.Thread(target=probe, name="liveness-direct-db", daemon=True)
    t.start()
    t.join(timeout=DIRECT_PROBE_TIMEOUT_SECONDS)
    return result.get("ok", False)


def _process_pool():
    wrapper = connections[DEFAULT_DB_ALIAS]
    return wrapper.pool if wrapper.vendor == "postgresql" else None


def check_pool() -> tuple[str, str | None]:
    """``("ok"|"fail", motivo)`` para a liveness. ``fail`` só com o processo travado."""
    global _stuck_since
    pool = _process_pool()
    if pool is None or getattr(pool, "closed", False):
        # Sem pool, ou pool que nenhum request abriu ainda (processo recém-nascido).
        return "ok", None
    if _pool_hands_out_a_connection(pool):
        with _lock:
            if _stuck_since is not None:
                logger.warning("liveness_pool_recovered stuck_for=%.0fs", time.monotonic() - _stuck_since)
            _stuck_since = None
        return "ok", None

    now = time.monotonic()
    with _lock:
        if _stuck_since is None:
            _stuck_since = now
        stuck_for = now - _stuck_since
    stats = pool.get_stats()
    if stuck_for < _stuck_seconds():
        logger.warning(
            "liveness_pool_waiting stuck_for=%.0fs available=%s size=%s waiting=%s",
            stuck_for,
            stats.get("pool_available"),
            stats.get("pool_size"),
            stats.get("requests_waiting"),
        )
        return "ok", None
    if not _database_answers_directly():
        # Banco fora/lento: não é o processo. A readiness cuida; a liveness não reinicia.
        logger.warning("liveness_pool_stuck_but_database_down stuck_for=%.0fs", stuck_for)
        return "ok", None
    logger.error(
        "liveness_pool_stuck_restart stuck_for=%.0fs available=%s size=%s waiting=%s",
        stuck_for,
        stats.get("pool_available"),
        stats.get("pool_size"),
        stats.get("requests_waiting"),
    )
    return "fail", "pool_stuck"


def reset() -> None:
    """Esquece o "travado desde" (testes)."""
    global _stuck_since
    with _lock:
        _stuck_since = None
