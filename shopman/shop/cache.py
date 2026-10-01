"""Cache Redis com UM pool de conexões por processo.

Por que existe: sob ASGI (daphne) o ``CacheHandler`` do Django guarda a instância
do backend num ``asgiref.local.Local``, que é por contexto. Cada request monta um
``RedisCache`` novo, e o ``RedisCacheClient`` do Django guarda o ``ConnectionPool``
na própria instância (``self._pools``): pool novo por request, logo conexão TCP
nova (e handshake TLS no ``rediss://`` do Valkey gerenciado) por request. Medido
no alpha em 01/10/2026: ~25 ms por chamada ao cache, o maior custo fixo do request.

Aqui o pool sai de um dicionário do módulo, um por processo e por configuração
(servidor + opções). O ``ConnectionPool`` do redis-py é thread-safe, então as
threads do ``sync_to_async`` dividem o mesmo pool sem lock nosso no caminho
quente. A chave inclui ``os.getpid()``: depois de um ``fork`` o filho monta o
próprio pool em vez de usar sockets herdados do pai.

Comportamento de cache, serialização, timeouts e opções é o do Django, sem
mudança: só o dono do pool muda.
"""

from __future__ import annotations

import os
import threading

from django.core.cache.backends.redis import RedisCache, RedisCacheClient

#: Caminho deste backend em ``CACHES["default"]["BACKEND"]``.
SHARED_POOL_REDIS_BACKEND = "shopman.shop.cache.SharedPoolRedisCache"
#: Backends Redis que os checks e gates do Shopman aceitam como cache compartilhado.
REDIS_CACHE_BACKENDS = frozenset({
    "django.core.cache.backends.redis.RedisCache",
    SHARED_POOL_REDIS_BACKEND,
})

_pools: dict[tuple, object] = {}
_pools_lock = threading.Lock()


def is_redis_cache_backend(backend: str) -> bool:
    """O caminho de backend é o Redis nativo do Django (ou o nosso, com pool por processo)?"""
    return backend in REDIS_CACHE_BACKENDS


def _options_key(options: dict) -> tuple:
    return tuple(sorted((name, repr(value)) for name, value in options.items()))


class SharedPoolRedisCacheClient(RedisCacheClient):
    def __init__(self, servers, serializer=None, pool_class=None, parser_class=None, **options):
        super().__init__(
            servers,
            serializer=serializer,
            pool_class=pool_class,
            parser_class=parser_class,
            **options,
        )
        # A identidade do pool: o que muda a conexão. ``driver_info`` (montado
        # pelo Django a cada instância) fica de fora de propósito: é só o nome do
        # cliente reportado ao servidor.
        self._pool_identity = (
            repr(self._pool_class),
            repr(parser_class),
            _options_key(options),
        )

    def _get_connection_pool(self, write):
        index = self._get_connection_pool_index(write)
        key = (os.getpid(), self._servers[index], *self._pool_identity)
        pool = _pools.get(key)
        if pool is not None:
            return pool
        with _pools_lock:
            pool = _pools.get(key)
            if pool is None:
                pid = key[0]
                # Pools herdados de outro processo (fork) não são deste: solta a
                # referência sem fechar os sockets, que são do pai.
                for stale in [k for k in _pools if k[0] != pid]:
                    del _pools[stale]
                pool = self._pool_class.from_url(self._servers[index], **self._pool_options)
                _pools[key] = pool
        return pool


class SharedPoolRedisCache(RedisCache):
    """``RedisCache`` do Django com o pool de conexões por processo (ver o módulo)."""

    def __init__(self, server, params):
        super().__init__(server, params)
        self._class = SharedPoolRedisCacheClient
