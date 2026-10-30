"""Envio do catálogo de plataforma (Google e Meta) — tradução, gatilhos e reconciliação.

Tudo offline: HTTP do Google e da Meta é mockado. O que se prova:

- a Merchant API recebe a MESMA decisão do feed (``display_catalog``): Pausar sai
  ``OUT_OF_STOCK``, Ocultar sai com todos os destinos excluídos, preço em micros;
- Pausar, Ocultar, coleções e liga/desliga do canal no Gestor enfileiram o envio na
  hora; preço da loja chega ao canal que lê preço dela;
- pausado e oculto continuam na plataforma (project); só o item que saiu do canal é
  retirado (retract);
- a reconciliação diária reenvia o vencido, poupa o recente e retira o que saiu.
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.offerman import conf as offerman_conf
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
from shopman.offerman.protocols.projection import ProjectionResult
from shopman.orderman.models import Directive
from shopman.stockman.models import Move, Position, Quant

from shopman.shop.adapters import catalog_projection_google as google
from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.services import display_catalog
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db

_STORE = {"account_id": "5881119366", "data_source_id": "999", "content_language": "pt", "feed_label": "BR"}
_SETTINGS = {
    "service_account_b64": base64.b64encode(json.dumps({
        "client_email": "shopman@projeto.iam.gserviceaccount.com",
        # A assinatura do JWT é mockada nos testes: a chave nunca é lida.
        "private_key": "chave-de-teste",
        "token_uri": "https://oauth2.mock.test/token",
    }).encode()).decode(),
    "api_base": "https://merchant.mock.test",
    "timeout": 5,
}
_CFG = {**_SETTINGS, **_STORE}


class FakeBackend:
    def __init__(self):
        self.projected = []
        self.retracted = []

    def project(self, items, *, channel, full_sync=False):
        self.projected.extend(items)
        return ProjectionResult(success=True, projected=len(items), channel=channel)

    def retract(self, skus, *, channel):
        self.retracted.extend(skus)
        return ProjectionResult(success=True, projected=len(skus), channel=channel)


@pytest.fixture
def loja(db, settings):
    from shopman.shop.models import Channel, Shop

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://www.loja.test"
    # Conta e fonte de dados são dado da loja (ADR-042); o segredo vem do settings.
    shop = Shop.objects.create(name="Nelson", defaults={"google_merchant": _STORE})
    Channel.objects.create(ref="web", name="Loja", commerce_policy="order", is_active=True, shop=shop)
    display_channel("google", "Google", collections=["vitrine"], fmt="google_merchant", prices_from="web")
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
    listing = Listing.objects.create(ref="web", name="Loja")
    ListingItem.objects.create(listing=listing, product=product, price_q=1600)
    return product


@pytest.fixture
def stocked(pao, vitrine_pos):
    quant = Quant.objects.create(sku="PAO", position=vitrine_pos)
    Move.objects.create(quant=quant, delta=Decimal(5), kind=Move.Kind.MAKE, reason="teste")
    return quant


@pytest.fixture
def push(settings, pao):
    """O canal ``google`` com backend de envio, e a fila vazia para medir o gatilho."""
    backend = FakeBackend()
    settings.OFFERMAN = {
        "COST_BACKEND": None,
        "PRICING_BACKEND": "shopman.shop.adapters.pricing.PromotionPricingBackend",
        "PROJECTION_BACKENDS": {"google": "shopman.shop.adapters.catalog_projection_google.GoogleMerchantProjection"},
    }
    offerman_conf.reset_projection_backends()
    offerman_conf._projection_backend_instances["google"] = backend
    Directive.objects.filter(topic=CATALOG_PROJECT_SKU).delete()
    yield backend
    offerman_conf.reset_projection_backends()


def _queued(ref: str = "google") -> list[Directive]:
    return [
        d for d in Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status="queued")
        if d.payload.get("listing_ref") == ref
    ]


def _handle_all() -> None:
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    for directive in _queued():
        CatalogProjectHandler().handle(message=directive, ctx={})
        directive.status = "done"
        directive.save(update_fields=["status"])


# ── tradução para a Merchant API ──────────────────────────────────────────────


class TestProductInput:
    def _input(self, **over):
        item = display_catalog.display_item("google", "PAO")
        from dataclasses import replace

        return google.build_product_input(replace(item, **over), _CFG)

    def test_available_item_with_price_in_micros(self, stocked):
        body = self._input()
        assert body["offerId"] == "PAO"
        assert body["contentLanguage"] == "pt"
        assert body["feedLabel"] == "BR"
        attrs = body["productAttributes"]
        assert attrs["availability"] == "IN_STOCK"
        # O preço é o da loja (prices_from), não o base_price_q.
        assert attrs["price"] == {"amountMicros": "16000000", "currencyCode": "BRL"}
        assert attrs["link"] == "https://www.loja.test/produto/PAO"
        assert attrs["condition"] == "NEW"
        assert attrs["customLabel0"] == "vitrine"
        assert "excludedDestinations" not in attrs

    def test_paused_is_out_of_stock_and_stays_in_every_destination(self, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_paused("google", "PAO", paused=True)
        attrs = google.build_product_input(display_catalog.display_item("google", "PAO"), _CFG)["productAttributes"]
        assert attrs["availability"] == "OUT_OF_STOCK"
        assert "excludedDestinations" not in attrs

    def test_hidden_excludes_every_destination(self, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_hidden("google", "PAO", hidden=True)
        attrs = google.build_product_input(display_catalog.display_item("google", "PAO"), _CFG)["productAttributes"]
        assert attrs["availability"] == "OUT_OF_STOCK"
        assert attrs["excludedDestinations"] == list(display_catalog.GOOGLE_DESTINATIONS)

    def test_sold_out_is_out_of_stock(self, stocked):
        Move.objects.create(quant=stocked, delta=Decimal(-5), kind=Move.Kind.SELL, reason="teste")
        attrs = google.build_product_input(display_catalog.display_item("google", "PAO"), _CFG)["productAttributes"]
        assert attrs["availability"] == "OUT_OF_STOCK"

    def test_product_input_id_is_unpadded_base64url(self):
        segment = google.product_input_id("PAO", _CFG)
        assert "=" not in segment
        padded = segment + "=" * (-len(segment) % 4)
        assert base64.urlsafe_b64decode(padded).decode() == "pt~BR~PAO"


# ── backend HTTP (mockado) ────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def token(settings, loja):
    settings.SHOPMAN_GOOGLE_MERCHANT = _SETTINGS
    google._token_cache.clear()
    with mock.patch.object(google.jwt, "encode", return_value="assinado"), mock.patch.object(
        google.requests, "post", return_value=_Resp(200, {"access_token": "tok", "expires_in": 3600})
    ) as post:
        yield post
    google._token_cache.clear()


class TestBackend:
    def _item(self):
        from shopman.shop.handlers.catalog_projection import display_projected_item

        return display_projected_item("google", "PAO")

    def test_inert_without_configuration(self, settings, stocked):
        settings.SHOPMAN_GOOGLE_MERCHANT = dict(_SETTINGS, service_account_b64="")
        with mock.patch.object(google.requests, "post") as post:
            result = google.GoogleMerchantProjection().project([self._item()], channel="google")
        assert result.success is False
        assert "não configurado" in result.errors[0]
        post.assert_not_called()

    def test_raw_json_secret_is_refused(self):
        """O segredo é o JSON em base64; o JSON cru não passa, nem por engano."""
        raw = base64.b64decode(_SETTINGS["service_account_b64"]).decode()
        assert google._service_account({"service_account_b64": raw}) is None
        assert google._service_account(_SETTINGS)["client_email"] == "shopman@projeto.iam.gserviceaccount.com"

    def test_project_inserts_into_the_api_data_source(self, token, stocked):
        calls = []

        def fake_post(url, params=None, json=None, headers=None, timeout=None, data=None):
            if "oauth2" in url:
                return _Resp(200, {"access_token": "tok", "expires_in": 3600})
            calls.append((url, params, json, headers))
            return _Resp(200)

        with mock.patch.object(google.requests, "post", fake_post):
            result = google.GoogleMerchantProjection().project([self._item()], channel="google")

        assert result.success is True and result.projected == 1
        url, params, body, headers = calls[0]
        assert url == "https://merchant.mock.test/products/v1/accounts/5881119366/productInputs:insert"
        assert params == {"dataSource": "accounts/5881119366/dataSources/999"}
        assert body["offerId"] == "PAO"
        assert headers["Authorization"] == "Bearer tok"

    def _project_with_store(self, settings, item):
        settings.SHOPMAN_GOOGLE_MERCHANT = dict(_SETTINGS, store_code="18102236950405822206")
        calls = []

        def fake_post(url, params=None, json=None, headers=None, timeout=None, data=None):
            if "oauth2" in url:
                return _Resp(200, {"access_token": "tok", "expires_in": 3600})
            calls.append((url, json))
            return _Resp(200)

        with mock.patch.object(google.requests, "post", fake_post):
            result = google.GoogleMerchantProjection().project([item], channel="google")
        return result, calls

    def test_store_code_sends_pickup_with_the_same_stock(self, token, settings, stocked):
        result, calls = self._project_with_store(settings, self._item())
        assert result.success is True and result.projected == 1
        url, body = calls[1]
        assert url == (
            "https://merchant.mock.test/inventories/v1/accounts/5881119366/products/"
            f"{google.product_input_id('PAO', _CFG)}/localInventories:insert"
        )
        assert body == {
            "storeCode": "18102236950405822206",
            "localInventoryAttributes": {
                "availability": "IN_STOCK",
                "price": {"amountMicros": "16000000", "currencyCode": "BRL"},
                "pickupMethod": "BUY",
                "pickupSla": "SAME_DAY",
            },
        }

    def test_paused_pickup_is_out_of_stock(self, token, settings, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_paused("google", "PAO", paused=True)
        _result, calls = self._project_with_store(settings, self._item())
        assert calls[1][1]["localInventoryAttributes"]["availability"] == "OUT_OF_STOCK"

    def test_hidden_item_gets_no_pickup(self, token, settings, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_hidden("google", "PAO", hidden=True)
        result, calls = self._project_with_store(settings, self._item())
        assert result.success is True
        assert [url for url, _ in calls if "localInventories" in url] == []

    def test_without_store_code_no_pickup(self, token, stocked):
        calls = []

        def fake_post(url, params=None, json=None, headers=None, timeout=None, data=None):
            if "oauth2" in url:
                return _Resp(200, {"access_token": "tok", "expires_in": 3600})
            calls.append(url)
            return _Resp(200)

        with mock.patch.object(google.requests, "post", fake_post):
            google.GoogleMerchantProjection().project([self._item()], channel="google")
        assert len(calls) == 1 and "productInputs" in calls[0]

    def test_retract_deletes_and_missing_is_success(self, token):
        urls = []

        def fake_delete(url, params=None, headers=None, timeout=None):
            urls.append((url, params))
            return _Resp(404)

        with mock.patch.object(google.requests, "delete", fake_delete):
            result = google.GoogleMerchantProjection().retract(["PAO"], channel="google")
        assert result.success is True
        url, params = urls[0]
        assert url.endswith(f"/productInputs/{google.product_input_id('PAO', _CFG)}")
        assert params == {"dataSource": "accounts/5881119366/dataSources/999"}

    def test_rate_limit_raises_with_retry_after(self, token, stocked):
        def fake_post(url, params=None, json=None, headers=None, timeout=None, data=None):
            if "oauth2" in url:
                return _Resp(200, {"access_token": "tok", "expires_in": 3600})
            return _Resp(429, headers={"Retry-After": "17"})

        with mock.patch.object(google.requests, "post", fake_post):
            with pytest.raises(google.GoogleMerchantRateLimitError) as exc:
                google.GoogleMerchantProjection().project([self._item()], channel="google")
        assert exc.value.retry_after == 17


# ── registro do projeto no Merchant Center (developerRegistration) ───────────


class TestDeveloperRegistration:
    """Sem o registro, toda chamada da Merchant API volta 401."""

    def _post(self, status, body=None):
        def fake_post(url, params=None, json=None, headers=None, timeout=None, data=None):
            if "oauth2" in url:
                return _Resp(200, {"access_token": "tok", "expires_in": 3600})
            fake_post.calls.append((url, json, headers))
            resp = _Resp(status, body)
            resp.content = b"x" if body else b""
            resp.text = ""
            return resp

        fake_post.calls = []
        return fake_post

    def test_registers_the_project_and_returns_gcp_ids(self, token):
        fake = self._post(200, {"name": "accounts/5881119366/developerRegistration", "gcpIds": ["123456789"]})
        with mock.patch.object(google.requests, "post", fake):
            result = google.register_gcp()
        assert result.ok is True and result.gcp_ids == ("123456789",)
        url, body, headers = fake.calls[0]
        assert url == "https://merchant.mock.test/accounts/v1/accounts/5881119366/developerRegistration:registerGcp"
        assert body == {}
        assert headers["Authorization"] == "Bearer tok"

    def test_repeating_is_safe(self, token):
        fake = self._post(200, {"gcpIds": ["123456789"]})
        with mock.patch.object(google.requests, "post", fake):
            first, second = google.register_gcp(), google.register_gcp()
        assert first == second and first.ok

    def test_google_error_message_is_shown_with_the_access_hint(self, token):
        fake = self._post(403, {"error": {
            "code": 403, "message": "The caller does not have permission", "status": "PERMISSION_DENIED",
        }})
        with mock.patch.object(google.requests, "post", fake):
            result = google.register_gcp()
        assert result.ok is False
        assert "The caller does not have permission (PERMISSION_DENIED)" in result.error
        assert "acesso de Administrador" in result.error

    def test_without_account_or_key_nothing_is_called(self, settings, loja):
        settings.SHOPMAN_GOOGLE_MERCHANT = dict(_SETTINGS, service_account_b64="")
        with mock.patch.object(google.requests, "post") as post:
            result = google.register_gcp()
        assert result.ok is False and "chave da service account" in result.error
        post.assert_not_called()

    def test_admin_action_registers_and_shows_the_project(self, token, rf, monkeypatch):
        from django.contrib import admin
        from django.contrib.auth.models import User

        from shopman.shop.models import Shop, ShopIntegrations

        user = User.objects.create_superuser("gerente", "g@loja.test", "x")
        shop = Shop.objects.get()
        request = rf.post("/", data={"_form_submitted": "1"})
        request.user = user
        model_admin = admin.site._registry[ShopIntegrations]
        said = []
        monkeypatch.setattr(model_admin, "message_user", lambda request, message, **kw: said.append(message))
        fake = self._post(200, {"gcpIds": ["123456789"]})

        with mock.patch.object(google.requests, "post", fake):
            response = model_admin.register_google_merchant(request, object_id=str(shop.pk))

        assert response.status_code == 302
        assert said == ["Envio registrado no Google. Projeto vinculado: 123456789."]
        shop.refresh_from_db()
        assert shop.defaults["google_merchant"]["registration"]["gcp_ids"] == ["123456789"]
        assert shop.defaults["google_merchant"]["account_id"] == "5881119366"
        assert "123456789" in str(model_admin.google_merchant_display(shop))

    def test_admin_action_shows_google_error_and_keeps_defaults(self, token, rf, monkeypatch):
        from django.contrib import admin
        from django.contrib.auth.models import User

        from shopman.shop.models import Shop, ShopIntegrations

        user = User.objects.create_superuser("gerente", "g@loja.test", "x")
        shop = Shop.objects.get()
        before = dict(shop.defaults)
        request = rf.post("/", data={"_form_submitted": "1"})
        request.user = user
        model_admin = admin.site._registry[ShopIntegrations]
        said = []
        monkeypatch.setattr(model_admin, "message_user", lambda request, message, **kw: said.append(message))
        fake = self._post(401, {"error": {"message": "Request had invalid authentication", "status": "UNAUTHENTICATED"}})

        with mock.patch.object(google.requests, "post", fake):
            model_admin.register_google_merchant(request, object_id=str(shop.pk))

        assert said and said[0].startswith("O Google não registrou o envio: Request had invalid authentication")
        shop.refresh_from_db()
        assert shop.defaults == before


# ── gatilhos e handler ────────────────────────────────────────────────────────


class TestTriggers:
    def test_pause_and_hide_enqueue_the_sku(self, push, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_paused("google", "PAO", paused=True)
        assert len(_queued()) == 1
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).update(status="done")
        feeds.set_items_hidden("google", ["PAO"], hidden=True)
        assert len(_queued()) == 1

    def test_no_backend_no_queue(self, settings, stocked):
        from shopman.backstage.services import feeds

        offerman_conf.reset_projection_backends()
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).delete()
        feeds.set_item_paused("google", "PAO", paused=True)
        assert _queued() == []

    def test_collections_change_enqueues_who_left(self, push, stocked):
        from shopman.backstage.services import feeds

        Collection.objects.create(ref="outra", name="Outra", is_active=True)
        feeds.set_collections("google", ["outra"])
        assert [d.payload["sku"] for d in _queued()] == ["PAO"]

    def test_store_price_reaches_the_platform_channel(self, push, stocked):
        ListingItem.objects.filter(product__sku="PAO", listing__ref="web").update(price_q=1700)
        item = ListingItem.objects.get(product__sku="PAO", listing__ref="web")
        from shopman.shop.handlers.catalog_projection import on_price_changed

        on_price_changed(None, item, listing_ref="web", sku="PAO", old_price_q=1600, new_price_q=1700)
        assert [d.payload["trigger"] for d in _queued()] == ["price_changed"]

    def test_switching_the_channel_off_resends_everything(self, push, stocked):
        from shopman.shop.models import Channel
        from shopman.shop.services import channel_switch

        channel = Channel.objects.get(ref="google")
        channel_switch._apply_effects(channel, is_active=False, changed=True, actor=None)
        assert [d.payload["sku"] for d in _queued()] == ["PAO"]

    def test_paused_and_hidden_are_projected_not_retracted(self, push, stocked):
        from shopman.backstage.services import feeds

        feeds.set_item_hidden("google", "PAO", hidden=True)
        _handle_all()
        assert push.retracted == []
        sent = push.projected[-1].metadata["display"]
        assert sent.hidden is True and sent.available is False

    def test_item_that_left_the_channel_is_retracted(self, push, stocked):
        from shopman.backstage.services import feeds

        Collection.objects.create(ref="outra", name="Outra", is_active=True)
        feeds.set_collections("google", ["outra"])
        _handle_all()
        assert push.retracted == ["PAO"]

    def test_switched_off_channel_still_sends_out_of_stock(self, push, stocked):
        from shopman.shop.handlers.catalog_projection import enqueue_project
        from shopman.shop.models import Channel

        Channel.objects.filter(ref="google").update(is_active=False)

        enqueue_project("PAO", "google", trigger="manual_resync")
        _handle_all()
        assert push.projected and push.projected[-1].sku == "PAO"


# ── reconciliação diária ──────────────────────────────────────────────────────


class TestDailySync:
    def test_sends_stale_spares_fresh_and_retracts_who_left(self, push, stocked):
        from shopman.shop.models import CatalogSyncState

        call_command("sync_platform_catalogs", stdout=StringIO())
        assert [d.payload["sku"] for d in _queued()] == ["PAO"]
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).update(status="done")

        CatalogSyncState.objects.filter(sku="PAO", channel_ref="google").update(
            status="synced", last_synced_at=timezone.now()
        )
        call_command("sync_platform_catalogs", stdout=StringIO())
        assert _queued() == []

        CatalogSyncState.objects.filter(sku="PAO", channel_ref="google").update(
            last_synced_at=timezone.now() - timedelta(hours=25)
        )
        call_command("sync_platform_catalogs", stdout=StringIO())
        assert [d.payload["trigger"] for d in _queued()] == ["daily_resync"]
        Directive.objects.filter(topic=CATALOG_PROJECT_SKU).update(status="done")

        CatalogSyncState.objects.create(sku="SUMIU", channel_ref="google", status="synced")
        CatalogSyncState.objects.filter(sku="PAO").update(status="synced", last_synced_at=timezone.now())
        call_command("sync_platform_catalogs", stdout=StringIO())
        assert [(d.payload["sku"], d.payload["trigger"]) for d in _queued()] == [("SUMIU", "left_channel")]

    def test_dry_run_prints_the_api_payload_without_credentials(self, settings, stocked):
        settings.SHOPMAN_GOOGLE_MERCHANT = dict(_SETTINGS, service_account_b64="")
        out = StringIO()
        call_command("sync_platform_catalogs", "--dry-run", "--channel", "google", stdout=out)
        output = out.getvalue()
        assert "Dry run — 1 item(s) em google" in output
        assert '"offerId": "PAO"' in output
        assert '"availability": "IN_STOCK"' in output
