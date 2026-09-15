"""Escrita de catálogo exige autorização de teste, inclusive fora do worker."""

from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from shopman.offerman.protocols.projection import ProjectedItem
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.adapters import catalog_projection_ifood as adapter
from shopman.shop.handlers.catalog_projection import CatalogProjectHandler
from shopman.shop.models import CatalogSyncState, Channel

MERCHANT = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"


@pytest.fixture
def item():
    return ProjectedItem(sku="EXAMPLE", name="Exemplo", description="", unit="un",
                         price_q=100, is_published=True, is_sellable=True)


@pytest.fixture
def cfg(settings):
    settings.SHOPMAN_IFOOD = {"merchant_id": MERCHANT, "catalog_default_category": "category"}
    return settings.SHOPMAN_IFOOD


@pytest.fixture
def no_network():
    with patch.object(adapter.ifood_auth, "authorized_headers") as auth, patch("requests.sessions.Session.request") as http:
        yield auth, http
        auth.assert_not_called()
        http.assert_not_called()


@pytest.mark.parametrize("policy", [None, False, True, "test", {},
    {"environment": "production", "merchant_allowlist": [MERCHANT]},
    {"environment": "test", "merchant_allowlist": MERCHANT},
    {"environment": "test", "merchant_allowlist": True},
    {"environment": "test", "merchant_allowlist": []},
    {"environment": "test", "merchant_allowlist": [True]},
    {"environment": "test", "merchant_allowlist": [MERCHANT, "invalid"]},
    {"environment": "test", "merchant_allowlist": [OTHER]},
])
def test_invalid_policy_blocks_project_and_retract_before_auth(settings, cfg, item, no_network, policy):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = policy
    for result in (adapter.IFoodCatalogProjection().project([item], channel="ifood"),
                   adapter.IFoodCatalogProjection().retract([item.sku], channel="ifood")):
        assert not result.success
        assert result.projected == 0
        assert "bloqueada" in result.errors[0]


def test_absent_policy_blocks_direct_helpers(settings, cfg, item, no_network):
    if hasattr(settings, "SHOPMAN_IFOOD_CATALOG_WRITE_POLICY"):
        del settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY
    for operation in (lambda: adapter._headers(cfg),
                      lambda: adapter._upsert_item(item, cfg, {"Authorization": "local"}),
                      lambda: adapter._set_item_status(item.sku, "UNAVAILABLE", cfg, {})):
        with pytest.raises(adapter.IFoodCatalogWriteBlocked):
            operation()


def test_authorized_test_merchant_can_write_with_mock_transport(settings, cfg, item):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {"environment": "test", "merchant_allowlist": [MERCHANT]}
    response = Mock(status_code=200)
    with patch.object(adapter.ifood_auth, "authorized_headers", return_value={"Authorization": "fixture"}) as auth, patch("requests.sessions.Session.request", return_value=response) as http:
        assert adapter.IFoodCatalogProjection().project([item], channel="ifood").success
        assert adapter.IFoodCatalogProjection().retract([item.sku], channel="ifood").success
    assert auth.call_count == 2
    assert http.call_count == 2


@pytest.mark.parametrize("full", [False, True])
def test_cli_blocks_before_projection_even_without_database(cfg, no_network, full):
    with patch("shopman.offerman.service.CatalogService.project_listing") as project:
        with pytest.raises(CommandError, match="bloqueada"):
            call_command("sync_catalog_ifood", full=full)
    project.assert_not_called()


@pytest.mark.django_db
def test_cli_dry_run_remains_local_without_authorization(cfg, item, no_network, capsys):
    Channel.objects.create(ref="ifood", name="Loja de exemplo")
    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=[item]), patch("shopman.offerman.service.CatalogService.project_listing") as project:
        call_command("sync_catalog_ifood", dry_run=True)
    project.assert_not_called()
    assert "EXAMPLE" in capsys.readouterr().out


@pytest.mark.django_db
@pytest.mark.parametrize("retract", [False, True])
def test_directive_records_guard_failure_without_remote_calls(settings, cfg, item, no_network, retract):
    settings.OFFERMAN = {**settings.OFFERMAN, "PROJECTION_BACKENDS": {}}
    Channel.objects.create(ref="ifood", name="Loja de exemplo")
    message = Directive.objects.create(topic="catalog.project_sku", payload={"sku": item.sku, "listing_ref": "ifood"})
    snapshot = None if retract else item
    with patch("shopman.shop.handlers.catalog_projection._get_projected_item", return_value=snapshot):
        with pytest.raises(DirectiveTransientError, match="bloqueada"):
            CatalogProjectHandler(backend=adapter.IFoodCatalogProjection()).handle(message=message, ctx={})
    state = CatalogSyncState.objects.get(sku=item.sku, channel_ref="ifood")
    assert state.status == "error"
    assert "bloqueada" in state.last_error


def test_revoked_policy_after_auth_still_blocks_http(settings, cfg, item):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {"environment": "test", "merchant_allowlist": [MERCHANT]}

    def authorized_headers(*args):
        settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = None
        return {"Authorization": "fixture"}

    with patch.object(adapter.ifood_auth, "authorized_headers", side_effect=authorized_headers), patch("requests.sessions.Session.request") as http:
        result = adapter.IFoodCatalogProjection().project([item], channel="ifood")
    assert not result.success
    assert "bloqueada" in result.errors[0]
    http.assert_not_called()
