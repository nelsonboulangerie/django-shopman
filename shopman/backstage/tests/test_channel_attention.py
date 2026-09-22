"""Indicador da navegação e aviso da fila: canais desligados, pausados ou divergentes.

Estado normal não produz nada. A fila de Pedidos só recebe canal de VENDA (é o que
muda o que entra nela); o indicador da navegação conta venda e exibição.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings

from shopman.backstage.projections.channel_attention import build_channel_attention
from shopman.shop.models import Channel, IFoodStoreStatus, Shop
from shopman.shop.services import channel_switch
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db
TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 12, 22, 10, 0, tzinfo=TZ)
WEEK = {d: {"open": "09:00", "close": "18:00"} for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}


@pytest.fixture
def channels():
    Shop.objects.create(name="Nelson", timezone="America/Sao_Paulo", opening_hours=WEEK)
    for ref, name, order in (("web", "Loja online", 1), ("ifood", "iFood", 2), ("whatsapp", "WhatsApp", 3)):
        Channel.objects.create(ref=ref, name=name, display_order=order)
    display_channel("tv-1", "TV do Café", collections=[], prices_from="pdv")


def test_estado_normal_nao_diz_nada(channels):
    attention = build_channel_attention(now=NOW)
    assert (attention.count, attention.label, attention.queue) == (0, "", ())


def test_desligado_e_pausado_contam_e_so_venda_vai_para_a_fila(channels):
    channel_switch.request_switch("ifood", False, period="30m", reason="Loja cheia", actor=None, now=NOW)
    channel_switch.request_switch("web", False, period="open", reason="Desfalque na equipe", actor=None, now=NOW)
    channel_switch.request_switch("tv-1", False, period="open", reason="Férias", actor=None, now=NOW)

    attention = build_channel_attention(now=NOW + timedelta(minutes=1))

    assert attention.count == 3
    assert attention.label == "3 desligados"
    assert [(item.ref, item.state, item.line) for item in attention.queue] == [
        ("web", "off", "Loja online: pedidos desligados — Desfalque na equipe"),
        ("ifood", "paused", "iFood: pedidos pausados até hoje às 10h30 — Loja cheia"),
    ]
    assert attention.queue[0].focus_path == "/feeds?focus=web"
    # Fim da pausa pelo relógio, sem esperar o worker.
    assert build_channel_attention(now=NOW + timedelta(minutes=31)).label == "2 desligados"


@override_settings(SHOPMAN_IFOOD={"client_id": "c", "merchant_id": "m-1", "merchant_sync_enabled": True})
def test_ifood_divergente_entra_como_divergente(channels):
    IFoodStoreStatus.objects.create(merchant_id="m-1", checked_at=NOW, available=False, divergent_since=NOW)

    attention = build_channel_attention(now=NOW)

    assert attention.label == "1 divergente"
    assert attention.queue[0].state == "diverges"


def test_api_quem_ve_a_fila_le_e_so_quem_edita_canais_recebe_o_link(client, channels):
    caixa = User.objects.create_user("caixa", is_staff=True)
    caixa.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None)
    client.force_login(caixa)

    body = client.get("/api/v1/backstage/channels/attention/").json()["attention"]

    assert body["label"] == "1 desligado"
    assert body["can_open_channels"] is False
    assert body["queue"][0]["ref"] == "web"
