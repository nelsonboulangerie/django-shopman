"""Server-Timing nas leituras do storefront: presença e formato único.

Sem o header não se prova melhora de performance em produção, e sem o MESMO
formato do cardápio não se compara uma rota com a outra.
"""

from __future__ import annotations

import gc
import re
import threading

import pytest
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections

from shopman.shop.observability import capture_catalog_timing
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

# O formato de CatalogTiming.server_timing(): os cinco estágios da view e os três
# de custo fixo (com a contagem em ``desc``), nesta ordem.
SERVER_TIMING = re.compile(
    r"^projection;dur=\d+\.\d{2}, availability;dur=\d+\.\d{2}, "
    r"personalization;dur=\d+\.\d{2}, shadow;dur=\d+\.\d{2}, db;dur=\d+\.\d{2}, "
    r'connect;dur=\d+\.\d{2};desc="\d+", cache;dur=\d+\.\d{2};desc="\d+", '
    r'gc;dur=\d+\.\d{2};desc="\d+"$'
)


def _stages(header: str) -> dict[str, tuple[float, int | None]]:
    """``{"cache": (1.23, 4), "db": (0.5, None), ...}`` a partir do header."""
    out = {}
    for part in header.split(", "):
        name, *params = part.split(";")
        values = dict(param.split("=", 1) for param in params)
        count = int(values["desc"].strip('"')) if "desc" in values else None
        out[name] = (float(values["dur"]), count)
    return out

INSTRUMENTED_READS = (
    # superfície da loja
    "/api/v1/storefront/home/",
    "/api/v1/storefront/shell/",
    "/api/v1/storefront/site/",
    "/api/v1/storefront/legal/",
    "/api/v1/storefront/sku-redirects/",
    "/api/v1/storefront/products/PAO-FRANCES/",
    "/api/v1/storefront/cart/",
    "/api/v1/storefront/checkout/",
    # gêmeas públicas (cache de borda): o header vai junto para a borda
    "/api/v1/storefront/public/home/",
    "/api/v1/storefront/public/shell/",
    "/api/v1/storefront/public/catalog/",
    # os que já tinham, para travar que o formato é um só
    "/api/v1/storefront/menu/",
    "/api/v1/storefront/catalog/",
    # catálogo público
    "/api/v1/catalog/products/",
    "/api/v1/catalog/products/PAO-FRANCES/",
    "/api/v1/catalog/collections/",
    # acompanhamento (pedido inexistente: o header vale também no 404)
    "/api/v1/tracking/NAO-EXISTE/",
    # conta (anônimo: o header vale também na recusa)
    "/api/v1/account/summary/",
    "/api/v1/account/profile/",
    "/api/v1/account/addresses/",
    "/api/v1/account/favorites/",
    "/api/v1/account/orders/",
    "/api/v1/account/orders/active/",
    "/api/v1/account/passkeys/",
    "/api/v1/account/devices/",
    "/api/v1/account/accesses/",
)


@pytest.mark.parametrize("path", INSTRUMENTED_READS)
def test_read_route_emits_server_timing_in_the_menu_format(client, path):
    _seed_surface()

    response = client.get(path)

    assert response.status_code < 500, response.content[:300]
    assert SERVER_TIMING.match(response["Server-Timing"]), (path, response["Server-Timing"])


def test_home_timing_breaks_down_the_catalog_it_builds(client):
    """A home passa por build_catalog: o estágio de disponibilidade aparece nela."""
    _seed_surface()

    response = client.get("/api/v1/storefront/home/")

    timings = {name: dur for name, (dur, _count) in _stages(response["Server-Timing"]).items()}
    assert timings["projection"] > 0
    assert timings["availability"] > 0
    assert timings["db"] > 0
    assert timings["availability"] <= timings["projection"]


def test_mutation_is_not_timed(client):
    """O header mede leitura; o PATCH da mesma view de perfil não o carrega."""
    _seed_surface()

    read = client.get("/api/v1/account/profile/")
    write = client.patch("/api/v1/account/profile/", data={}, content_type="application/json")

    assert "Server-Timing" in read
    assert "Server-Timing" not in write


# ── Custo fixo do request: connect, cache, gc ────────────────────────────────


def test_shell_reports_its_cache_round_trips(client):
    """A shell lê a loja pelo cache: a chamada aparece em ``cache`` com contagem."""
    _seed_surface()

    stages = _stages(client.get("/api/v1/storefront/shell/")["Server-Timing"])

    cache_ms, cache_calls = stages["cache"]
    assert cache_calls >= 1
    assert cache_ms <= stages["projection"][0]


def test_connect_counts_the_connection_opened_inside_the_request():
    """Abrir conexão de banco dentro da captura vira ``connect`` (o ``db`` não a vê)."""
    fresh = connections.create_connection(DEFAULT_DB_ALIAS)
    try:
        with capture_catalog_timing() as timing:
            fresh.ensure_connection()
            fresh.ensure_connection()  # já aberta: não é outra conexão
    finally:
        fresh.close()

    assert timing.counts["connect"] == 1
    assert timing.durations_ms["connect"] > 0


def test_connect_outside_a_capture_is_not_counted():
    fresh = connections.create_connection(DEFAULT_DB_ALIAS)
    with capture_catalog_timing() as timing:
        pass
    try:
        fresh.ensure_connection()
    finally:
        fresh.close()

    assert timing.counts["connect"] == 0


def test_cache_counts_each_call_once():
    """``get_or_set`` chama ``get``/``add`` por dentro e conta uma vez só."""
    cache.get("server-timing-probe")  # fora da captura: não conta
    with capture_catalog_timing() as timing:
        cache.get("server-timing-probe")
        cache.set("server-timing-probe", 1, 5)
        cache.get_many(["server-timing-probe", "other"])
        cache.get_or_set("server-timing-probe-2", 2, 5)
    cache.delete("server-timing-probe")

    assert timing.counts["cache"] == 4
    assert timing.durations_ms["cache"] > 0
    assert f'cache;dur={timing.durations_ms["cache"]:.2f};desc="4"' in timing.server_timing()


def test_gc_counts_the_collection_that_ran_inside_the_request():
    with capture_catalog_timing() as timing:
        gc.collect()
    gc.collect()  # fora da captura: não conta

    assert timing.counts["gc"] == 1
    assert timing.durations_ms["gc"] > 0


def test_nothing_measured_reads_zero():
    with capture_catalog_timing() as timing:
        pass

    stages = _stages(timing.server_timing())
    assert stages["connect"] == (0.0, 0)
    assert stages["cache"] == (0.0, 0)
    assert stages["gc"] == (0.0, 0)


def test_concurrent_requests_do_not_see_each_other():
    """Cada request mede o SEU custo: o estado mora no ContextVar, não na classe sondada."""
    barrier = threading.Barrier(2)
    results = {}

    def request(name: str, calls: int) -> None:
        with capture_catalog_timing() as timing:
            barrier.wait()
            for _ in range(calls):
                cache.get(f"server-timing-{name}")
            barrier.wait()
        results[name] = timing.counts["cache"]

    threads = [
        threading.Thread(target=request, args=("a", 3)),
        threading.Thread(target=request, args=("b", 1)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == {"a": 3, "b": 1}
