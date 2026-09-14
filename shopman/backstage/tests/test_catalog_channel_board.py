"""Canais externos têm diagnóstico local, sem controles de exibição."""

import pytest

from shopman.backstage.projections.feeds import build_feed_board
from shopman.shop.models import Channel
from shopman.shop.models.catalog_sync import CatalogSyncState

pytestmark = pytest.mark.django_db


def test_existing_ifood_visible_with_disabled_projection(monkeypatch):
    monkeypatch.setattr('shopman.offerman.conf.get_projection_backend_channels', lambda: [])
    Channel.objects.create(ref='ifood', name='iFood', commerce_policy='order')
    Channel.objects.create(ref='web', name='Web', commerce_policy='order')
    board = build_feed_board()
    assert not board.feeds
    assert {channel.ref for channel in board.catalog_channels} == {'ifood', 'web'}
    channel = board.catalog_channels[0]
    assert channel.projection_enabled is False
    assert 'Sem envio externo' in channel.diagnostic
    assert channel.catalog_path == '/catalog'
    assert not hasattr(channel, 'is_active')
    assert not hasattr(channel, 'actions')


def test_configured_channels_show_only_their_local_sync_counts(monkeypatch):
    monkeypatch.setattr('shopman.offerman.conf.get_projection_backend_channels', lambda: ['partner', 'missing'])
    Channel.objects.create(ref='partner', name='Parceiro', commerce_policy='order')
    for sku, channel, status in [('a', 'partner', 'synced'), ('b', 'partner', 'pending'),
                                 ('c', 'partner', 'error'), ('d', 'other', 'error'),
                                 ('e', 'partner', 'retracted'), ('f', 'partner', 'skipped')]:
        CatalogSyncState.objects.create(sku=sku, channel_ref=channel, status=status)
    result, = build_feed_board().catalog_channels
    assert result.ref == 'partner'
    assert result.projection_enabled
    assert (result.observed, result.synced, result.pending, result.errors) == (5, 1, 1, 1)
    assert (result.retracted, result.skipped) == (1, 1)


def test_absent_ifood_not_invented(monkeypatch):
    monkeypatch.setattr('shopman.offerman.conf.get_projection_backend_channels', lambda: ['ifood'])
    assert not build_feed_board().catalog_channels


def test_custom_sales_channel_without_backend_is_visible(monkeypatch):
    monkeypatch.setattr('shopman.offerman.conf.get_projection_backend_channels', lambda: [])
    Channel.objects.create(ref='custom', name='Atacado', commerce_policy='order')
    result, = build_feed_board().catalog_channels
    assert result.ref == 'custom'
    assert not result.projection_enabled
    assert result.diagnostic == 'Sem envio externo de catálogo configurado.'
