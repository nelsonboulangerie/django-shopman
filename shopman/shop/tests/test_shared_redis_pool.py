"""O cache Redis divide UM pool de conexões por processo, não um por request.

Sob ASGI o ``CacheHandler`` do Django guarda o backend por contexto: cada request
monta um ``RedisCache`` novo. Com o cliente nativo, o pool mora na instância, e
pool novo é conexão nova (e TLS novo no ``rediss://``) a cada request. Estes testes
não precisam de Redis de pé: ``ConnectionPool.from_url`` não conecta.
"""

from __future__ import annotations

import contextvars
import importlib.util
import threading
from pathlib import Path

import pytest
from django.core.cache import CacheHandler
from django.core.cache.backends.redis import RedisCache
from django.test import override_settings

from config import settings as project_settings
from shopman.shop import cache as shared_cache
from shopman.shop.cache import SHARED_POOL_REDIS_BACKEND, SharedPoolRedisCache, is_redis_cache_backend

LOCATION = "redis://127.0.0.1:6399/0"


@pytest.fixture(autouse=True)
def _fresh_pools(monkeypatch):
    monkeypatch.setattr(shared_cache, "_pools", {})


def _pool(backend) -> object:
    return backend._cache._get_connection_pool(write=True)


def _backend(location=LOCATION, **options):
    return SharedPoolRedisCache(location, {"OPTIONS": options} if options else {})


def test_two_instances_share_one_pool():
    assert _pool(_backend()) is _pool(_backend())


def test_the_native_django_backend_does_not_and_that_is_the_cost_being_removed():
    native_a = RedisCache(LOCATION, {})
    native_b = RedisCache(LOCATION, {})

    assert _pool(native_a) is not _pool(native_b)


def test_two_request_contexts_get_two_backends_but_one_pool():
    """O cenário do daphne: cada request é um contexto, e o handler monta um backend por contexto."""
    handler = CacheHandler({"default": {"BACKEND": SHARED_POOL_REDIS_BACKEND, "LOCATION": LOCATION}})

    first = contextvars.Context().run(lambda: handler["default"])
    second = contextvars.Context().run(lambda: handler["default"])

    assert first is not second
    assert _pool(first) is _pool(second)


def test_threads_share_the_pool():
    pools = []

    def worker():
        pools.append(_pool(_backend()))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(pools) == 8
    assert len({id(pool) for pool in pools}) == 1


def test_different_server_or_options_get_their_own_pool():
    base = _pool(_backend())

    assert _pool(_backend("redis://127.0.0.1:6399/1")) is not base
    assert _pool(_backend(socket_timeout=3)) is not base
    assert _pool(_backend(socket_timeout=3)) is _pool(_backend(socket_timeout=3))


def test_a_forked_process_builds_its_own_pool_and_drops_the_inherited_one(monkeypatch):
    parent_pool = _pool(_backend())
    parent_pid = shared_cache.os.getpid()

    monkeypatch.setattr(shared_cache.os, "getpid", lambda: parent_pid + 1)
    child_pool = _pool(_backend())

    assert child_pool is not parent_pool
    assert all(key[0] == parent_pid + 1 for key in shared_cache._pools)
    assert _pool(_backend()) is child_pool


def test_rediss_keeps_tls():
    from redis.connection import SSLConnection

    pool = _pool(_backend("rediss://127.0.0.1:6399/0"))

    assert pool.connection_class is SSLConnection


def test_cache_api_is_the_django_one():
    """Mesma API e mesma serialização do RedisCache: só o dono do pool muda."""
    assert issubclass(SharedPoolRedisCache, RedisCache)
    assert _backend().make_key("x") == RedisCache(LOCATION, {}).make_key("x")


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        ("django.core.cache.backends.redis.RedisCache", True),
        (SHARED_POOL_REDIS_BACKEND, True),
        ("django_redis.cache.RedisCache", False),
        ("django.core.cache.backends.locmem.LocMemCache", False),
    ],
)
def test_redis_backend_recognition(backend, expected):
    assert is_redis_cache_backend(backend) is expected


@override_settings(DEBUG=False, CACHES={"default": {"BACKEND": SHARED_POOL_REDIS_BACKEND}})
def test_deploy_check_accepts_the_shared_pool_backend():
    from shopman.shop import checks

    assert checks.check_shared_cache_backend(None) == []


@override_settings(CACHES={"default": {"BACKEND": SHARED_POOL_REDIS_BACKEND, "LOCATION": LOCATION}})
def test_manychat_serialization_counts_the_shared_pool_backend_as_shared():
    from shopman.shop.services import manychat_marketing_safety as safety

    assert safety.serialization_available() is True


@override_settings(CACHES={"default": {"BACKEND": SHARED_POOL_REDIS_BACKEND, "LOCATION": LOCATION}})
def test_ratelimit_check_only_warns_unsupported_never_broken():
    """django-ratelimit não conhece a subclasse: W001 (silenciado no settings), nunca E003."""
    from django_ratelimit.checks import check_caches

    assert [message.id for message in check_caches(None)] == ["django_ratelimit.W001"]


def _load_settings(monkeypatch, **env):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location(
        "shopman_settings_cache_under_test", Path(project_settings.__file__)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_settings_with_redis_url_use_the_shared_pool_backend(monkeypatch):
    settings = _load_settings(monkeypatch, DJANGO_DEBUG="1", REDIS_URL="rediss://user:pw@cache.invalid:25061/0")

    assert settings.CACHES["default"] == {
        "BACKEND": SHARED_POOL_REDIS_BACKEND,
        "LOCATION": "rediss://user:pw@cache.invalid:25061/0",
    }
    assert "django_ratelimit.W001" in settings.SILENCED_SYSTEM_CHECKS
    assert settings.EVENTSTREAM_REDIS["ssl"] is True


def test_settings_without_redis_url_stay_on_locmem(monkeypatch):
    settings = _load_settings(monkeypatch, DJANGO_DEBUG="1")

    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
