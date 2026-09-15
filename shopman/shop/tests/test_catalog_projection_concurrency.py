"""Regressões de concorrência com transporte local e serviços reais de catálogo."""

from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from shopman.offerman.conf import reset_projection_backends
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.offerman.signals import availability_changed
from shopman.orderman import registry
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.handlers.catalog_projection import CatalogProjectHandler, on_availability_changed
from shopman.shop.models import CatalogSyncState, Channel
from shopman.shop.services import ifood_auth


@pytest.fixture(autouse=True)
def isolated_catalog_write_policy(settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {
        "environment": "test",
        "merchant_allowlist": ["00000000-0000-4000-8000-000000000001"],
    }


@pytest.mark.django_db
def test_pause_during_remote_upsert_leaves_durable_followup(settings):
    Channel.objects.create(ref="ifood", name="Local audit", is_active=True)
    product = Product.objects.create(sku="AUDIT-SKU", name="Audit", unit="un", is_published=True, is_sellable=True)
    listing = Listing.objects.create(ref="ifood", name="Local audit")
    cell = ListingItem.objects.create(listing=listing, product=product, price_q=1000, is_published=True, is_sellable=False)
    backend_map = {"ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"}
    remote = {}

    def http(_session, method, url, **kwargs):
        assert url.startswith("https://ifood.invalid/")
        if method.upper() == "PATCH":
            remote["status"] = kwargs["json"]["status"]
            return Mock(status_code=200, raise_for_status=lambda: None)
        assert method.upper() == "PUT"
        remote.update(kwargs["json"]["item"])
        assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status="running").count() == 1
        cell.is_sellable = False
        cell.save(update_fields=["is_sellable"])
        return Mock(status_code=200, raise_for_status=lambda: None)

    with override_settings(
        OFFERMAN={**settings.OFFERMAN, "PROJECTION_BACKENDS": backend_map},
        SHOPMAN_IFOOD={"merchant_id": "00000000-0000-4000-8000-000000000001", "api_base": "https://ifood.invalid", "catalog_default_category": "isolated-category"},
    ), patch.dict(registry._registry._directive_handlers, {CATALOG_PROJECT_SKU: CatalogProjectHandler()}, clear=True), patch.object(ifood_auth, "get_access_token", return_value="local-audit-token"), patch("requests.sessions.Session.request", new=http):
        reset_projection_backends()
        availability_changed.connect(on_availability_changed, dispatch_uid="temporary-catalog-race-audit", weak=False)
        try:
            cell.is_sellable = True
            cell.save(update_fields=["is_sellable"])
            directive = Directive.objects.get(topic=CATALOG_PROJECT_SKU)
            _process_directive(directive)
            cell.refresh_from_db()
            directive.refresh_from_db()
            sync = CatalogSyncState.objects.get(sku=product.sku, channel_ref="ifood")
            pending = Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status__in=["queued", "running"]).count()
            # O envio antigo não pode confirmar a edição recebida durante o HTTP.
            assert cell.is_sellable is False
            assert remote["status"] == "AVAILABLE"
            assert directive.status == "done"
            assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count() == 2
            assert pending == 1
            assert sync.status == "pending"
            followup = Directive.objects.get(topic=CATALOG_PROJECT_SKU, status="queued")
            _process_directive(followup)
            assert remote["status"] == "UNAVAILABLE"
            assert not Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status__in=["queued", "running"]).exists()
            sync.refresh_from_db()
            assert sync.status == "retracted"
        finally:
            availability_changed.disconnect(dispatch_uid="temporary-catalog-race-audit")
            reset_projection_backends()


def test_failed_enqueue_rolls_back_pending_badge(db):
    from shopman.shop.handlers.catalog_projection import enqueue_project
    from shopman.shop.services.catalog_sync import record_sync

    state = record_sync("AUDIT", "ifood", status="synced")
    with patch("shopman.shop.directives.create_deduped", return_value=None), pytest.raises(RuntimeError):
        enqueue_project("AUDIT", "ifood")
    state.refresh_from_db()
    assert state.status == "synced"
    assert not Directive.objects.filter(topic=CATALOG_PROJECT_SKU).exists()


def test_pending_edits_coalesce_but_running_is_never_reused(db):
    from shopman.shop.handlers.catalog_projection import enqueue_project

    sku = "S" * 100
    first = enqueue_project(sku, "ifood")
    assert enqueue_project(sku, "ifood").pk == first.pk
    first.status = "running"
    first.save(update_fields=["status"])
    second = enqueue_project(sku, "ifood")
    assert second.pk != first.pk
    assert enqueue_project(sku, "ifood").pk == second.pk
    assert len(second.dedupe_key) <= 128


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("reaped", [False, True])
@pytest.mark.parametrize("provider_error", [False, True])
def test_postgres_serializes_http_reaper_and_atomic_operator_edit(settings, reaped, provider_error):
    """Conexões distintas: envio em voo, outro worker e edição atômica."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import requests
    from django.db import close_old_connections, connection, transaction

    from shopman.shop.handlers.catalog_projection import enqueue_project

    if connection.vendor != "postgresql":
        pytest.skip("Row-lock guarantee requires PostgreSQL")

    Channel.objects.create(ref="ifood", name="Local audit", is_active=True)
    product = Product.objects.create(sku="PG-AUDIT", name="Audit", unit="un", is_published=True, is_sellable=True)
    listing = Listing.objects.create(ref="ifood", name="Local audit")
    cell = ListingItem.objects.create(listing=listing, product=product, price_q=1000, is_published=True, is_sellable=True)
    sender_entered, release_sender, edit_started = Event(), Event(), Event()
    calls = []
    remote = {}

    def http(_session, method, url, **kwargs):
        assert url.startswith("https://ifood.invalid/")
        status = kwargs["json"].get("item", kwargs["json"])["status"]
        calls.append(status)
        if len(calls) == 1:
            sender_entered.set()
            assert release_sender.wait(10), "test did not release HTTP sender"
            if provider_error:
                remote["status"] = status  # O provedor aplicou; somente a resposta se perdeu.
                raise requests.Timeout("local timeout after send")
        remote["status"] = status
        return Mock(status_code=200, raise_for_status=lambda: None)

    def process(pk):
        close_old_connections()
        try:
            _process_directive(Directive.objects.get(pk=pk))
        finally:
            close_old_connections()

    def edit():
        close_old_connections()
        try:
            with transaction.atomic():
                locked = ListingItem.objects.select_for_update().get(pk=cell.pk)
                locked.is_sellable = False
                edit_started.set()
                locked.save(update_fields=["is_sellable"])
        finally:
            close_old_connections()

    with override_settings(
        OFFERMAN={**settings.OFFERMAN, "PROJECTION_BACKENDS": {"ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"}},
        SHOPMAN_IFOOD={"merchant_id": "00000000-0000-4000-8000-000000000001", "api_base": "https://ifood.invalid", "catalog_default_category": "isolated-category"},
    ), patch.dict(registry._registry._directive_handlers, {CATALOG_PROJECT_SKU: CatalogProjectHandler()}, clear=True), patch.object(ifood_auth, "get_access_token", return_value="local-audit-token"), patch("requests.sessions.Session.request", new=http):
        reset_projection_backends()
        availability_changed.connect(on_availability_changed, dispatch_uid="postgres-catalog-race-audit", weak=False)
        try:
            # Mantém as diretivas de setup na fila até os workers abrirem suas conexões.
            with patch("shopman.orderman.dispatch._on_commit_callback"):
                first = enqueue_project(product.sku, "ifood", trigger="availability_changed")
                second = enqueue_project(product.sku, "ifood", trigger="price_changed")
            with ThreadPoolExecutor(max_workers=2) as pool:
                sender = pool.submit(process, first.pk)
                try:
                    assert sender_entered.wait(10)
                    competing = first if reaped else second
                    if reaped:
                        Directive.objects.filter(pk=first.pk).update(status="queued")
                    _process_directive(Directive.objects.get(pk=competing.pk))
                    competing.refresh_from_db()
                    assert competing.status == "queued"
                    assert calls == ["AVAILABLE"], "second HTTP must not overlap the first"
                    mutation = pool.submit(edit)
                    assert edit_started.wait(10)
                    # O operador confirma enquanto a requisição remota está retida.
                    # O envio pós-commit encontra o mutex ocupado e mantém
                    # a nova ocorrência na fila, sem bloquear a interface.
                    mutation.result(timeout=3)
                    assert CatalogSyncState.objects.get(sku=product.sku, channel_ref="ifood").status == "pending"
                finally:
                    release_sender.set()
                sender.result(timeout=10)
                mutation.result(timeout=10)
            cell.refresh_from_db()
            assert cell.is_sellable is False
            assert CatalogSyncState.objects.get(sku=product.sku, channel_ref="ifood").status == "pending"
            queued = list(Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status="queued"))
            assert queued, "latest edit must retain durable work even after timeout/reaper"
            for directive in queued:
                _process_directive(directive)
            assert remote["status"] == "UNAVAILABLE"
            assert all(status == "UNAVAILABLE" for status in calls[1:])
            assert not Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status__in=["queued", "running"]).exists()
            assert CatalogSyncState.objects.get(sku=product.sku, channel_ref="ifood").status == "retracted"
        finally:
            availability_changed.disconnect(dispatch_uid="postgres-catalog-race-audit")
            reset_projection_backends()


@pytest.mark.django_db
def test_new_sender_finishes_before_old_dispatcher_marks_done(settings):
    """O estado running antigo não deixa o catálogo convergido preso em pending."""
    from shopman.shop.handlers.catalog_projection import enqueue_project

    Channel.objects.create(ref="ifood", name="Local audit", is_active=True)
    product = Product.objects.create(sku="FINALIZE", name="Audit", unit="un", is_published=True, is_sellable=True)
    listing = Listing.objects.create(ref="ifood", name="Local audit")
    cell = ListingItem.objects.create(listing=listing, product=product, price_q=1000, is_published=True, is_sellable=True)
    handler = CatalogProjectHandler()
    sent_prices = []

    def http(_session, method, url, **kwargs):
        assert url.startswith("https://ifood.invalid/")
        sent_prices.append(kwargs["json"]["item"]["price"]["value"])
        return Mock(status_code=200, raise_for_status=lambda: None)

    with override_settings(
        OFFERMAN={**settings.OFFERMAN, "PROJECTION_BACKENDS": {"ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"}},
        SHOPMAN_IFOOD={"merchant_id": "00000000-0000-4000-8000-000000000001", "api_base": "https://ifood.invalid", "catalog_default_category": "isolated-category"},
    ), patch.dict(registry._registry._directive_handlers, {CATALOG_PROJECT_SKU: handler}, clear=True), patch.object(ifood_auth, "get_access_token", return_value="local-audit-token"), patch("requests.sessions.Session.request", new=http):
        reset_projection_backends()
        try:
            first = enqueue_project(product.sku, "ifood")
            first.status = "running"
            first.save(update_fields=["status"])
            handler.handle(message=first, ctx={})
            # Janela real: HTTP terminou e mutex foi liberado, mas o dispatcher
            # antigo ainda não atualizou a própria diretiva para done.
            cell.price_q = 1200
            cell.save(update_fields=["price_q"])
            second = Directive.objects.get(topic=CATALOG_PROJECT_SKU, status="queued")
            _process_directive(second)
            first.status = "done"
            first.save(update_fields=["status"])
            assert sent_prices == [10.0, 12.0]
            assert not Directive.objects.filter(topic=CATALOG_PROJECT_SKU, status__in=["queued", "running"]).exists()
            assert CatalogSyncState.objects.get(sku=product.sku, channel_ref="ifood").status == "synced"
        finally:
            reset_projection_backends()
