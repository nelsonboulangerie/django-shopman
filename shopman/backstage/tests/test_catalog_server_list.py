"""Lista do catálogo no SERVIDOR: busca, filtro, ordenação e paginação (onda 1, B).

A página é do banco: a contagem de consultas não pode crescer com o número de
linhas do catálogo, senão o custo volta a ser o do catálogo inteiro.

As facetas de estoque, PIM e envio também são do banco, em lote: cada uma vira
um filtro por SKU depois de a leitura sair uma vez para todos os candidatos.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Product

from shopman.backstage.projections.catalog import build_catalog_matrix
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db

MATRIX_URL = fixtures.MATRIX_URL


def _make(count: int, prefix: str = "EXTRA") -> list[Product]:
    return [
        Product.objects.create(
            sku=f"{prefix}{index:03d}",
            name=f"{prefix} {index:03d}",
            base_price_q=100 + index,
        )
        for index in range(count)
    ]


def test_page_query_count_does_not_grow_with_rows(catalog):
    _make(3)
    with CaptureQueriesContext(connection) as before:
        first = build_catalog_matrix(page_size=10, order="name")
    _make(60, prefix="MUITO")
    with CaptureQueriesContext(connection) as after:
        second = build_catalog_matrix(page_size=10, order="name")

    assert first.total == 5
    assert second.total == 65
    assert len(second.rows) == 10
    assert len(after.captured_queries) == len(before.captured_queries), (
        "A página consulta o banco em número fixo; crescer com as linhas é N+1."
    )


def test_search_and_filters_run_in_the_database(catalog):
    _make(5)
    by_name = build_catalog_matrix(query="EXTRA 000", page_size=10)
    assert [row.sku for row in by_name.rows] == ["EXTRA000"]
    assert by_name.total == 1
    assert by_name.query == "EXTRA 000"

    # A busca também alcança o SKU, não só o nome.
    by_sku = build_catalog_matrix(query="PAO", page_size=10)
    assert {row.sku for row in by_sku.rows} == {"PAO"}

    catalog["bolo"].is_published = False
    catalog["bolo"].save()
    paused = build_catalog_matrix(filters={"is_published": False}, page_size=50)
    assert {row.sku for row in paused.rows} == {"BOLO"}
    assert paused.total == 1


def test_order_and_page_are_server_side(catalog):
    Product.objects.create(sku="BARATO", name="Barato", base_price_q=100)
    Product.objects.create(sku="CARO", name="Caro", base_price_q=9000)

    first = build_catalog_matrix(order="price", page=1, page_size=1)
    assert first.total == 4
    assert [row.sku for row in first.rows] == ["BARATO"]
    assert first.has_next is True

    last = build_catalog_matrix(order="price", page=4, page_size=1)
    assert [row.sku for row in last.rows] == ["CARO"]
    assert last.has_next is False

    top = build_catalog_matrix(order="-price", page=1, page_size=1)
    assert [row.sku for row in top.rows] == ["CARO"]


def test_page_size_is_capped(catalog):
    from shopman.backstage.projections.catalog import MAX_CATALOG_PAGE_SIZE

    page = build_catalog_matrix(page=1, page_size=10_000)
    assert page.page_size == MAX_CATALOG_PAGE_SIZE


def test_matrix_api_paginates_filters_and_orders(client, operator, catalog):
    client.force_login(operator)
    response = client.get(MATRIX_URL, {"q": "BOLO", "page": 1, "page_size": 1})
    assert response.status_code == 200
    matrix = response.json()["matrix"]
    assert [row["sku"] for row in matrix["rows"]] == ["BOLO"]
    assert matrix["total"] == 1
    assert matrix["query"] == "BOLO"
    assert matrix["page"] == 1
    assert matrix["page_size"] == 1
    assert matrix["has_next"] is False

    ordered = client.get(MATRIX_URL, {"order": "price", "page_size": 1}).json()["matrix"]
    assert [row["sku"] for row in ordered["rows"]] == ["PAO"]
    assert ordered["order"] == "price"
    assert ordered["has_next"] is True


def test_server_filters_vocation_and_surface(catalog):
    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

    role = ConsumptionRole.objects.create(ref="leva", label="Leva")
    ProductConsumptionTag.objects.create(sku="PAO", role=role)

    tagged = build_catalog_matrix(filters={"has_vocation": True}, page_size=10)
    assert {row.sku for row in tagged.rows} == {"PAO"}
    assert tagged.total == 1

    untagged = build_catalog_matrix(filters={"has_vocation": False}, page_size=10)
    assert {row.sku for row in untagged.rows} == {"BOLO"}

    on_web = build_catalog_matrix(filters={"surface": ["web"]}, page_size=10)
    assert {row.sku for row in on_web.rows} == {"PAO", "BOLO"}
    assert on_web.total == 2

    on_ifood = build_catalog_matrix(filters={"surface": ["ifood"]}, page_size=10)
    assert {row.sku for row in on_ifood.rows} == {"PAO"}
    assert on_ifood.total == 1


def test_matrix_api_filters_by_facets(client, operator, catalog):
    client.force_login(operator)
    on_ifood = client.get(MATRIX_URL, {"surface": "ifood"}).json()["matrix"]
    assert [row["sku"] for row in on_ifood["rows"]] == ["PAO"]
    assert on_ifood["total"] == 1

    sellable_only = client.get(MATRIX_URL, {"is_sellable": "false"}).json()["matrix"]
    assert [row["sku"] for row in sellable_only["rows"]] == []
    assert sellable_only["total"] == 0


# ── facetas novas no BANCO: estoque, PIM e envio ──────────────────────────────


def test_server_filters_stock(monkeypatch, catalog):
    """Estoque é balde por produto e casa os três lados, sem mentir no total."""
    from shopman.backstage.projections import catalog as projection

    monkeypatch.setattr(projection, "_stock_for", lambda skus: (
        {
            "PAO": {"is_tracked": True, "total_promisable": 0},
            "BOLO": {"is_tracked": True, "total_promisable": 2},
        },
        5,
        {},
    ))

    out = build_catalog_matrix(filters={"stock": ["out"]}, page_size=10)
    assert {row.sku for row in out.rows} == {"PAO"}
    assert out.total == 1
    # A contagem ignora a própria seleção: os três baldes continuam visíveis.
    assert out.facets.stock == {"ok": 0, "low": 1, "out": 1}

    low = build_catalog_matrix(filters={"stock": ["low"]}, page_size=10)
    assert {row.sku for row in low.rows} == {"BOLO"}
    assert low.total == 1
    assert low.facets.stock == {"ok": 0, "low": 1, "out": 1}


def test_server_filters_pim(catalog):
    """PIM completo é marca + categoria Google, o mesmo sinal da linha."""
    from shopman.offerman.contrib.social.schema import (
        ProductSocialAttributes,
        set_social_attributes,
    )

    pao = catalog["pao"]
    pao.metadata = set_social_attributes(
        pao.metadata,
        ProductSocialAttributes(brand="Nelson", google_product_category="Food"),
    )
    pao.save(update_fields=["metadata"])

    complete = build_catalog_matrix(filters={"pim_complete": True}, page_size=10)
    assert {row.sku for row in complete.rows} == {"PAO"}
    assert complete.total == 1

    incomplete = build_catalog_matrix(filters={"pim_complete": False}, page_size=10)
    assert {row.sku for row in incomplete.rows} == {"BOLO"}
    assert incomplete.total == 1


def test_server_filters_sync(monkeypatch, catalog):
    """Envio casa por QUALQUER célula-alvo: erro no iFood e "nunca" no web."""
    from shopman.shop.services import catalog_sync

    monkeypatch.setattr("shopman.offerman.conf.get_projection_backend", lambda _ref: object())
    catalog_sync.record_sync("PAO", "ifood", status="error", error="boom")

    error = build_catalog_matrix(filters={"sync_status": ["error"]}, page_size=10)
    assert {row.sku for row in error.rows} == {"PAO"}
    assert error.facets.sync_status["error"] == 1

    never = build_catalog_matrix(filters={"sync_status": ["never"]}, page_size=10)
    # PAO nunca foi ao web; BOLO nunca foi a plataforma nenhuma.
    assert {row.sku for row in never.rows} == {"PAO", "BOLO"}
    assert never.facets.sync_status["never"] == 2


def test_server_sync_respects_selected_surface(monkeypatch, catalog):
    """A lista de alvos importa: o erro do web não volta no recorte do iFood."""
    from shopman.shop.services import catalog_sync

    monkeypatch.setattr("shopman.offerman.conf.get_projection_backend", lambda _ref: object())
    catalog_sync.record_sync("PAO", "web", status="error", error="boom")

    on_web = build_catalog_matrix(
        filters={"surface": ["web"], "sync_status": ["error"]}, page_size=10
    )
    assert {row.sku for row in on_web.rows} == {"PAO"}

    on_ifood = build_catalog_matrix(
        filters={"surface": ["ifood"], "sync_status": ["error"]}, page_size=10
    )
    assert on_ifood.total == 0


def test_matrix_api_filters_new_facets(client, operator, catalog, monkeypatch):
    """As três facetas viram query do servidor, com as contagens no painel."""
    from shopman.offerman.contrib.social.schema import (
        ProductSocialAttributes,
        set_social_attributes,
    )

    from shopman.backstage.projections import catalog as projection
    from shopman.shop.services import catalog_sync

    client.force_login(operator)
    monkeypatch.setattr(projection, "_stock_for", lambda skus: (
        {
            "PAO": {"is_tracked": True, "total_promisable": 3},
            "BOLO": {"is_tracked": True, "total_promisable": 0},
        },
        0,
        {},
    ))
    monkeypatch.setattr("shopman.offerman.conf.get_projection_backend", lambda _ref: object())

    pao = catalog["pao"]
    pao.metadata = set_social_attributes(
        pao.metadata,
        ProductSocialAttributes(brand="Nelson", google_product_category="Food"),
    )
    pao.save(update_fields=["metadata"])
    catalog_sync.record_sync("PAO", "ifood", status="error", error="boom")

    stock = client.get(MATRIX_URL, {"stock": "out"}).json()["matrix"]
    assert {row["sku"] for row in stock["rows"]} == {"BOLO"}
    assert stock["facets"]["stock"] == {"ok": 1, "low": 0, "out": 1}

    pim = client.get(MATRIX_URL, {"pim_complete": "true"}).json()["matrix"]
    assert {row["sku"] for row in pim["rows"]} == {"PAO"}

    with_error = client.get(MATRIX_URL, {"sync_status": "error"}).json()["matrix"]
    assert {row["sku"] for row in with_error["rows"]} == {"PAO"}

    never = client.get(MATRIX_URL, {"sync_status": "never"}).json()["matrix"]
    assert {row["sku"] for row in never["rows"]} == {"PAO", "BOLO"}
