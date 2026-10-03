"""UX-R2: iFood, catálogo da Meta e feed Google/Meta respeitam o estoque.

A regra é a do portão de pedido (``availability.decide`` com uma unidade): o
canal de fora mostra disponível exatamente quando o pedido seria aceito. A
pausa continua vencendo, e produto sem rastreio de estoque segue disponível.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest
from shopman.offerman.models import Collection, CollectionItem, ListingItem, Product
from shopman.offerman.protocols.projection import ProjectedItem
from shopman.orderman.models import Directive
from shopman.stockman.models import Move, Position, Quant

from shopman.backstage.services import shelf_outages
from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.services import external_availability
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db

G = "{http://base.google.com/ns/1.0}"
MERCHANT = "00000000-0000-4000-8000-000000000001"
_OFFERMAN_BASE = {
    "COST_BACKEND": None,
    "PRICING_BACKEND": "shopman.shop.adapters.pricing.PromotionPricingBackend",
}
_OFFERMAN_PUSH = {
    **_OFFERMAN_BASE,
    "PROJECTION_BACKENDS": {
        "ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection",
        "meta-catalog": "shopman.shop.adapters.catalog_projection_meta.MetaCatalogProjection",
    },
}


@pytest.fixture
def loja(db, settings):
    from shopman.shop.models import Channel, Shop

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://www.loja.test"
    shop = Shop.objects.create(name="Nelson")
    Channel.objects.create(ref="web", name="Loja", commerce_policy="order", is_active=True, shop=shop)
    Channel.objects.create(ref="ifood", name="iFood", commerce_policy="order", is_active=True, shop=shop)
    display_channel("google", "Google", collections=["vitrine"], fmt="google_merchant", prices_from="web")
    display_channel("meta", "Meta", collections=["vitrine"], fmt="meta_catalog", prices_from="web")
    display_channel("meta-catalog", "Catálogo Meta", collections=["vitrine"], prices_from="web")
    return shop


@pytest.fixture
def vitrine_pos(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def pao(loja):
    product = Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=100, is_published=True,
        is_sellable=True, availability_policy="stock_only", image_url="https://cdn.test/pao.jpg",
    )
    vitrine = Collection.objects.create(ref="vitrine", name="Vitrine", is_active=True)
    CollectionItem.objects.create(collection=vitrine, product=product)
    return product


def _move(quant, delta: int, kind=Move.Kind.MAKE):
    Move.objects.create(quant=quant, delta=Decimal(delta), kind=kind, reason="teste")


def _feed_availability(client, ref: str) -> str:
    items = ET.fromstring(client.get(f"/feed/{ref}.xml").content).find("channel").findall("item")
    assert len(items) == 1
    return items[0].find(f"{G}availability").text


# ── A regra ───────────────────────────────────────────────────────────────────


class TestRule:
    def test_untracked_product_stays_available(self, pao):
        assert not Quant.objects.filter(sku="PAO").exists()
        assert external_availability.in_stock("PAO", channel_ref="ifood") is True

    def test_sold_out_is_unavailable_and_restock_brings_it_back(self, pao, vitrine_pos):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 3)
        assert external_availability.in_stock("PAO", channel_ref="ifood") is True

        _move(quant, -3, kind=Move.Kind.SELL)
        assert external_availability.in_stock("PAO", channel_ref="ifood") is False

        _move(quant, 2)
        assert external_availability.in_stock("PAO", channel_ref="ifood") is True

    def test_demand_ok_stays_available_at_zero(self, pao, vitrine_pos):
        Product.objects.filter(sku="PAO").update(availability_policy="demand_ok")
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 1)
        _move(quant, -1, kind=Move.Kind.SELL)
        assert external_availability.in_stock("PAO", channel_ref="ifood") is True

    def test_pause_is_not_a_stock_answer(self, pao, vitrine_pos):
        """Pausa é lida pelas flags; aqui só vale a falta de estoque."""
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 5)
        Product.objects.filter(sku="PAO").update(is_sellable=False)
        assert external_availability.in_stock("PAO", channel_ref="ifood") is True

    def test_display_channel_reads_stock_from_prices_from(self, loja):
        assert external_availability.stock_channel_ref("meta-catalog") == "web"
        assert external_availability.stock_channel_ref("ifood") == "ifood"

    def test_lookup_failure_does_not_take_the_item_down(self, pao):
        with patch("shopman.shop.services.availability.decide", side_effect=RuntimeError("db")):
            assert external_availability.in_stock("PAO", channel_ref="ifood") is True


# ── iFood ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def ifood_push(settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {"environment": "test", "merchant_allowlist": [MERCHANT]}
    settings.SHOPMAN_IFOOD = {
        "merchant_id": MERCHANT, "api_base": "https://mock-ifood.test",
        "catalog_default_category": "cat-default-uuid",
    }
    response = MagicMock(status_code=200)
    with (
        patch("shopman.shop.services.ifood_auth.token_with_reason", return_value=("tok", "")),
        patch("shopman.shop.adapters.catalog_projection_ifood.requests.put", return_value=response) as put,
    ):
        yield put


def _ifood_item(*, is_sellable=True) -> ProjectedItem:
    return ProjectedItem(
        sku="PAO", name="Pão", description="", unit="un", price_q=100,
        is_published=True, is_sellable=is_sellable, image_url="https://cdn.test/pao.jpg",
    )


def _ifood_status(put) -> str:
    return put.call_args.kwargs["json"]["item"]["status"]


class TestIFood:
    def _project(self, item):
        from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

        result = IFoodCatalogProjection().project([item], channel="ifood")
        assert result.success, result.errors

    def test_sold_out_goes_unavailable_and_back(self, pao, vitrine_pos, ifood_push):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 2)
        self._project(_ifood_item())
        assert _ifood_status(ifood_push) == "AVAILABLE"

        _move(quant, -2, kind=Move.Kind.SELL)
        self._project(_ifood_item())
        assert _ifood_status(ifood_push) == "UNAVAILABLE"

        _move(quant, 4)
        self._project(_ifood_item())
        assert _ifood_status(ifood_push) == "AVAILABLE"

    def test_untracked_stays_available(self, pao, ifood_push):
        self._project(_ifood_item())
        assert _ifood_status(ifood_push) == "AVAILABLE"

    def test_paused_with_stock_stays_unavailable(self, pao, vitrine_pos, ifood_push):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 10)
        self._project(_ifood_item(is_sellable=False))
        assert _ifood_status(ifood_push) == "UNAVAILABLE"


# ── Catálogo da Meta (empurrado) ──────────────────────────────────────────────


class TestMetaCatalog:
    def test_sold_out_goes_out_of_stock_and_pause_still_wins(self, pao, vitrine_pos):
        from shopman.shop.adapters.catalog_projection_meta import build_batch_requests, stock_for

        def availability(item):
            stock = stock_for([item], channel="meta-catalog")
            return build_batch_requests([item], {}, stock=stock)[0]["data"]["availability"]

        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 2)
        assert availability(_ifood_item()) == "in stock"
        _move(quant, -2, kind=Move.Kind.SELL)
        assert availability(_ifood_item()) == "out of stock"
        _move(quant, 1)
        assert availability(_ifood_item()) == "in stock"
        assert availability(_ifood_item(is_sellable=False)) == "out of stock"


# ── Feed Google/Meta ──────────────────────────────────────────────────────────


class TestFeed:
    @pytest.mark.parametrize(("ref", "yes", "no"), [
        ("google", "in_stock", "out_of_stock"),
        ("meta", "in stock", "out of stock"),
    ])
    def test_sold_out_is_out_of_stock_at_read_time(self, client, pao, vitrine_pos, ref, yes, no):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 2)
        assert _feed_availability(client, ref) == yes

        _move(quant, -2, kind=Move.Kind.SELL)
        assert _feed_availability(client, ref) == no

        _move(quant, 1)
        assert _feed_availability(client, ref) == yes

    def test_untracked_stays_in_stock(self, client, pao):
        assert _feed_availability(client, "google") == "in_stock"

    def test_paused_with_stock_stays_out_of_stock(self, client, pao, vitrine_pos):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 10)
        Product.objects.filter(sku="PAO").update(is_sellable=False)
        assert _feed_availability(client, "google") == "out_of_stock"

    def test_local_feed_pause_still_wins(self, client, pao, vitrine_pos):
        from shopman.shop.models import Channel

        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 10)
        channel = Channel.objects.get(ref="google")
        channel.config["display"]["paused_skus"] = ["PAO"]
        channel.save()
        assert _feed_availability(client, "google") == "out_of_stock"

    def test_follows_the_web_listing_stock_scope_not_absence(self, client, pao, vitrine_pos):
        """Fora da listagem da loja não é falta: só o estoque muda o feed."""
        from shopman.offerman.models import Listing

        Listing.objects.create(ref="web", name="Loja", is_active=True)
        assert not ListingItem.objects.filter(product=pao).exists()
        assert _feed_availability(client, "google") == "in_stock"


# ── Gatilho: a passagem por zero reenvia aos canais empurrados ────────────────


def _queued(listing_ref: str) -> list[Directive]:
    return [
        d for d in Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status="queued")
        if d.payload.get("listing_ref") == listing_ref
    ]


class TestTrigger:
    @pytest.fixture(autouse=True)
    def push_backends(self, settings):
        settings.OFFERMAN = _OFFERMAN_PUSH

    @pytest.fixture(autouse=True)
    def empty_queue(self, push_backends, pao):
        # Criar o produto já enfileira a projeção (``product_created``): a fila
        # começa vazia para medir só o gatilho de estoque.
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).delete()

    def test_zero_and_back_enqueue_ifood_projection(self, pao, vitrine_pos):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 2)
        shelf_outages.observe("PAO")
        assert _queued("ifood") == []  # com estoque não há transição

        _move(quant, -2, kind=Move.Kind.SELL)
        shelf_outages.observe("PAO")
        queued = _queued("ifood")
        assert len(queued) == 1
        assert queued[0].payload == {"sku": "PAO", "listing_ref": "ifood"}

        # Idempotente: observar de novo sem mudança não enfileira nada.
        shelf_outages.observe("PAO")
        assert len(_queued("ifood")) == 1

        # A volta, com a anterior ainda na fila, se junta a ela.
        _move(quant, 3)
        shelf_outages.observe("PAO")
        assert len(_queued("ifood")) == 1

        # Depois de enviada, a próxima virada gera outra.
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).update(status="done")
        _move(quant, -3, kind=Move.Kind.SELL)
        shelf_outages.observe("PAO")
        assert len(_queued("ifood")) == 1

    def test_web_transition_reaches_meta_catalog_through_prices_from(self, pao, vitrine_pos):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 1)
        _move(quant, -1, kind=Move.Kind.SELL)
        shelf_outages.observe("PAO", channels=["web"])
        assert len(_queued("meta-catalog")) == 1
        assert _queued("ifood") == []

    def test_stock_receivers_fire_the_trigger_after_commit(
        self, pao, vitrine_pos, django_capture_on_commit_callbacks
    ):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        with django_capture_on_commit_callbacks(execute=True):
            _move(quant, 2)
        with django_capture_on_commit_callbacks(execute=True):
            _move(quant, -2, kind=Move.Kind.SELL)
        assert len(_queued("ifood")) == 1

    def test_reconcile_catches_what_events_miss(self, pao, vitrine_pos):
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 1)
        _move(quant, -1, kind=Move.Kind.SELL)
        shelf_outages.reconcile_outages()
        assert len(_queued("ifood")) == 1
        shelf_outages.reconcile_outages()
        assert len(_queued("ifood")) == 1

    def test_no_push_backend_no_directive(self, pao, vitrine_pos, settings):
        settings.OFFERMAN = {**_OFFERMAN_BASE, "PROJECTION_BACKENDS": {}}
        quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
        _move(quant, 1)
        _move(quant, -1, kind=Move.Kind.SELL)
        shelf_outages.observe("PAO")
        assert not Directive.objects.filter(topic=CATALOG_PROJECT_SKU).exists()
