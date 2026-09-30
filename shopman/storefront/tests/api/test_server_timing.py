"""Server-Timing nas leituras do storefront: presença e formato único.

Sem o header não se prova melhora de performance em produção, e sem o MESMO
formato do cardápio não se compara uma rota com a outra.
"""

from __future__ import annotations

import re

import pytest

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

# O formato de CatalogTiming.server_timing(): cinco nomes, nesta ordem.
SERVER_TIMING = re.compile(
    r"^projection;dur=\d+\.\d{2}, availability;dur=\d+\.\d{2}, "
    r"personalization;dur=\d+\.\d{2}, shadow;dur=\d+\.\d{2}, db;dur=\d+\.\d{2}$"
)

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

    timings = dict(
        part.split(";dur=") for part in response["Server-Timing"].split(", ")
    )
    assert float(timings["projection"]) > 0
    assert float(timings["availability"]) > 0
    assert float(timings["db"]) > 0
    assert float(timings["availability"]) <= float(timings["projection"])


def test_mutation_is_not_timed(client):
    """O header mede leitura; o PATCH da mesma view de perfil não o carrega."""
    _seed_surface()

    read = client.get("/api/v1/account/profile/")
    write = client.patch("/api/v1/account/profile/", data={}, content_type="application/json")

    assert "Server-Timing" in read
    assert "Server-Timing" not in write
