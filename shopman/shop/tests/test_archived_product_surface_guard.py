"""Trava transversal: produto arquivado não vaza para nenhuma superfície.

Esta é a lista de lugares que precisa crescer quando nasce uma nova superfície
de catálogo. O caso deliberadamente mantém ``is_published`` e ``is_sellable``
ligados: só ``is_active`` pode decidir o arquivamento.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.offerman.protocols import ProjectionResult
from shopman.offerman.service import CatalogService

from shopman.backstage.bi.mapping import suggest_products
from shopman.backstage.models import HistoricalSale, HistoricalSaleItem, ImportBatch, ProductAlias
from shopman.backstage.projections.catalog import build_catalog_matrix
from shopman.backstage.services.integration_readiness import _sellable_products_without_ncm
from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.handlers.catalog_projection import CatalogProjectHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import display_catalog
from shopman.shop.tests._display import display_channel
from shopman.shop.views.product_feed import build_feed_items
from shopman.storefront.presentation import build_catalog
from shopman.storefront.services.catalog import search_index

pytestmark = pytest.mark.django_db


class SimulatedCatalogTransport:
    """Estado remoto observável sem chamar adapter ou rede de plataforma."""

    def __init__(self):
        self.state: dict[str, str] = {}
        self.projected: list[str] = []
        self.retracted: list[str] = []

    def project(self, items, *, channel, full_sync=False):
        for item in items:
            self.state[item.sku] = "AVAILABLE"
            self.projected.append(item.sku)
        return ProjectionResult(success=True, projected=len(items), channel=channel)

    def retract(self, skus, *, channel):
        for sku in skus:
            self.state[sku] = "UNAVAILABLE"
            self.retracted.append(sku)
        return ProjectionResult(success=True, projected=len(skus), channel=channel)


@pytest.fixture
def catalog(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.test"
    Shop.objects.create(name="Loja", brand_name="Loja", short_name="Loja")
    Channel.objects.create(ref="web", name="Loja online", is_active=True, display_order=1)
    Channel.objects.create(ref="ifood", name="iFood", is_active=True, display_order=2)
    display_channel("google", "Google", collections=["vitrine"], fmt="google_merchant", prices_from="web")
    display_channel("meta", "Meta", collections=["vitrine"], fmt="meta_catalog", prices_from="web")

    web = Listing.objects.create(ref="web", name="Web", is_active=True)
    ifood = Listing.objects.create(ref="ifood", name="iFood", is_active=True)
    meta = Listing.objects.create(ref="meta", name="Meta", is_active=True)
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)

    active = Product.objects.create(
        sku="ATIVO",
        name="Produto ativo",
        base_price_q=900,
        image_url="https://cdn.test/ativo.jpg",
        is_active=True,
        is_published=True,
        is_sellable=True,
        metadata={"fiscal": {"ncm": "19059090"}},
    )
    archived = Product.objects.create(
        sku="ARQUIVADO",
        name="Produto arquivado",
        base_price_q=1200,
        image_url="https://cdn.test/arquivado.jpg",
        is_active=False,
        is_published=True,
        is_sellable=True,
    )
    for product in (active, archived):
        CollectionItem.objects.create(collection=vitrine, product=product, is_primary=product is active)
        for listing in (web, ifood, meta):
            ListingItem.objects.create(
                listing=listing,
                product=product,
                price_q=product.base_price_q,
                is_published=True,
                is_sellable=True,
            )
    return {"active": active, "archived": archived}


def test_archived_product_is_absent_from_every_read_surface(catalog):
    archived = catalog["archived"]

    # Loja online e índice de busca nascem da mesma projection pública.
    storefront = build_catalog(channel_ref="web")
    assert {item.sku for item in storefront.items} == {"ATIVO"}
    assert {item["sku"] for item in search_index(storefront)} == {"ATIVO"}

    # Gestor: padrão só ativos; o recorte explícito devolve apenas arquivados e
    # mantém os estados efêmeros intactos para uma futura restauração.
    default_matrix = build_catalog_matrix(page_size=50)
    assert {row.sku for row in default_matrix.rows} == {"ATIVO"}
    assert {item.sku for item in default_matrix.vocation_pending} == {"ATIVO"}
    archived_matrix = build_catalog_matrix(filters={"archived": True}, page_size=50)
    assert [row.sku for row in archived_matrix.rows] == ["ARQUIVADO"]
    row = archived_matrix.rows[0]
    assert row.is_active is False
    assert row.is_published is True
    assert row.is_sellable is True
    assert not any(cell.available for cell in row.cells)

    # O feed pull da Meta e o envio ao Google não mantêm o item no conjunto publicado.
    assert {item.sku for item in display_catalog.display_items("google")} == {"ATIVO"}
    assert {item["id"] for item in build_feed_items("meta")} == {"ATIVO"}

    # Snapshot normalizado de iFood/Meta preserva o SKU como indisponível para
    # o caminho retract-aware, nunca como payload vendável.
    for listing_ref in ("ifood", "meta"):
        snapshots = {item.sku: item for item in CatalogService.get_projection_items(listing_ref)}
        assert snapshots[archived.sku].is_published is False
        assert snapshots[archived.sku].is_sellable is False

    meta_remote = SimulatedCatalogTransport()
    with patch("shopman.offerman.service.get_projection_backend", return_value=meta_remote):
        assert CatalogService.project_listing("meta").success is True
    assert meta_remote.projected == ["ATIVO"]
    assert meta_remote.retracted == ["ARQUIVADO"]

    # B.I.: arquivado não é candidato do de-para nem pendência de vocação/NCM.
    batch = ImportBatch.objects.create(
        source="yooga", file_name="guard.csv", file_sha256="guard", status=ImportBatch.Status.DONE
    )
    sale = HistoricalSale.objects.create(
        batch=batch,
        source="yooga",
        external_id=1,
        occurred_at=timezone.now(),
        total_q=1200,
        payment="Dinheiro",
    )
    HistoricalSaleItem.objects.create(
        sale=sale,
        seq=1,
        sku=archived.sku,
        product_name=archived.name,
        qty=Decimal("1"),
        unit_price_q=1200,
        line_total_q=1200,
    )
    suggest_products("yooga", min_score=100)
    assert ProductAlias.objects.get(external_sku=archived.sku).product is None
    assert _sellable_products_without_ncm() == 0


def test_archiving_retracts_ifood_and_unarchiving_resends(catalog):
    product = catalog["archived"]
    product.is_active = True
    product.save(update_fields=["is_active"])
    remote = SimulatedCatalogTransport()
    message = SimpleNamespace(payload={"sku": product.sku, "listing_ref": "ifood", "trigger": "product_updated"})
    handler = CatalogProjectHandler(backend=remote)

    with patch("shopman.offerman.conf.get_projection_backend", return_value=None):
        handler.handle(message=message, ctx={})
        assert remote.state[product.sku] == "AVAILABLE"

        product.is_active = False
        product.save(update_fields=["is_active"])
        handler.handle(message=message, ctx={})
        assert remote.state[product.sku] == "UNAVAILABLE"
        assert remote.retracted[-1] == product.sku

        product.is_active = True
        product.save(update_fields=["is_active"])
        handler.handle(message=message, ctx={})
        assert remote.state[product.sku] == "AVAILABLE"
        assert remote.projected[-1] == product.sku


def test_archive_and_unarchive_enqueue_reconciliation(catalog):
    from shopman.orderman.models import Directive

    product = catalog["archived"]
    product.is_active = True
    product.save(update_fields=["is_active"])
    Directive.objects.all().delete()

    with patch(
        "shopman.shop.handlers.catalog_projection._projection_listing_refs",
        return_value=["ifood"],
    ):
        product.is_active = False
        product.save(update_fields=["is_active"])
        archived = Directive.objects.get(topic=CATALOG_PROJECT_SKU)
        assert archived.payload == {
            "sku": product.sku,
            "listing_ref": "ifood",
            "trigger": "product_updated",
        }

        archived.status = Directive.Status.DONE
        archived.save(update_fields=["status", "updated_at"])
        product.is_active = True
        product.save(update_fields=["is_active"])

    assert Directive.objects.filter(
        topic=CATALOG_PROJECT_SKU,
        status=Directive.Status.QUEUED,
        payload__sku=product.sku,
        payload__listing_ref="ifood",
    ).exists()
