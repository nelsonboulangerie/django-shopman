"""Cadência das telas do cliente: config, não número mágico.

Antes: uma constante lida no import (exigia restart), um `8000` cravado no Vue e
um piso de 15s no front. O gestor não alcançava nenhum dos três.
"""
from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.shop.realtime import ABSOLUTE_FLOOR_SECONDS, RealtimeConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    """Shop singleton — `Shop.load()` devolve None sem ele, e a config cai no default."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


class TestCascata:
    def test_default_quando_nada_configurado(self):
        cfg = RealtimeConfig.load()

        assert cfg.tracking_poll_seconds == 30
        assert cfg.payment_poll_seconds == 8

    @override_settings(STOREFRONT_TRACKING_POLL_SECONDS=12)
    def test_settings_sobrescreve_o_default(self):
        assert RealtimeConfig.load().tracking_poll_seconds == 12

    @override_settings(STOREFRONT_TRACKING_POLL_SECONDS=12)
    def test_shop_sobrescreve_settings(self, shop):
        """O gestor manda mais que o deploy — é ele que sente a tela."""
        shop = shop
        shop.realtime = {"tracking_poll_seconds": 7}
        shop.save(update_fields=["realtime"])

        assert RealtimeConfig.load().tracking_poll_seconds == 7


class TestGuardaDeServidor:
    def test_piso_absoluto_vence_config_afobada(self, shop):
        shop = shop
        shop.realtime = {"tracking_poll_seconds": 0, "min_poll_seconds": 0}
        shop.save(update_fields=["realtime"])

        cfg = RealtimeConfig.load()

        assert cfg.tracking_seconds() >= ABSOLUTE_FLOOR_SECONDS

    def test_min_poll_seconds_eleva_as_duas_telas(self, shop):
        shop = shop
        shop.realtime = {
            "tracking_poll_seconds": 5,
            "payment_poll_seconds": 5,
            "min_poll_seconds": 20,
        }
        shop.save(update_fields=["realtime"])

        cfg = RealtimeConfig.load()

        assert cfg.tracking_seconds() == 20
        assert cfg.payment_seconds() == 20

    def test_lixo_no_json_cai_no_default_em_vez_de_explodir(self, shop):
        shop = shop
        shop.realtime = {"tracking_poll_seconds": "meia dúzia"}
        shop.save(update_fields=["realtime"])

        assert RealtimeConfig.load().tracking_poll_seconds == 30


class TestChegaNasProjecoes:
    def test_acompanhamento_carrega_a_cadencia_viva(self, shop):
        """Mudar no Admin vale na próxima carga, sem reiniciar o processo."""
        from shopman.shop.projections.order_tracking import _stale_after_seconds

        shop = shop
        shop.realtime = {"tracking_poll_seconds": 17}
        shop.save(update_fields=["realtime"])

        assert _stale_after_seconds() == 17
