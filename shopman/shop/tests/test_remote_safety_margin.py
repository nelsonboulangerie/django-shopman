"""Margem de segurança dos canais remotos: padrão 2 unidades, configurável.

Decisão do dono (22/09/2026): "Margem padrão fica em 2 unidades, configurável,
claro." A margem é o que evita a disputa balcão × pedido remoto pela última
unidade: o canal remoto não mostra nem reserva as últimas N unidades de cada
SKU. O balcão nunca tem margem — é ele que a margem protege.

Antes desta mudança nenhum canal declarava ``stock.safety_margin`` e todos
herdavam o 0 do ``ChannelConfig``: a margem existia no código e não protegia
nada.
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from io import StringIO

import pytest
from django.apps import apps

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

REMOTE_REFS = ("web", "whatsapp", "ifood")


def _seed_channels():
    from config.management.commands.seed import Command

    Shop.objects.get_or_create(name="Seed Test Shop")
    command = Command()
    command.stdout = StringIO()
    return command._seed_channels()


def _tracked_product(sku: str, qty: int):
    from shopman.offerman.models import Product
    from shopman.stockman import stock as stockman_stock
    from shopman.stockman.models import Position, PositionKind

    product = Product.objects.create(
        sku=sku,
        name=f"Produto {sku}",
        base_price_q=1000,
        is_published=True,
        is_sellable=True,
    )
    position, _ = Position.objects.get_or_create(
        ref="margem-vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stockman_stock.receive(Decimal(str(qty)), sku, position, reason="margem test setup")
    return product


# ── Seed: onde o padrão mora ──


@pytest.mark.parametrize("ref", REMOTE_REFS)
def test_seeded_remote_channel_keeps_two_units_back(ref):
    channels = _seed_channels()

    assert ChannelConfig.for_channel(channels[ref]).stock.safety_margin == 2


def test_seeded_pos_has_no_margin():
    channels = _seed_channels()

    assert ChannelConfig.for_channel(channels["pdv"]).stock.safety_margin == 0
    # Explícito, não herdado: um default de loja não chega ao caixa em silêncio.
    assert channels["pdv"].config["stock"]["safety_margin"] == 0


# ── O que o cliente vê: com 3 na prateleira, o remoto enxerga 1 e o balcão 3 ──


def test_remote_channel_sees_shelf_minus_margin_and_pos_sees_everything():
    from shopman.shop.services import availability

    _seed_channels()
    _tracked_product("MARGEM-PAO", 3)

    web = availability.check("MARGEM-PAO", Decimal("1"), channel_ref="web")
    pdv = availability.check("MARGEM-PAO", Decimal("1"), channel_ref="pdv")

    assert web["available_qty"] == Decimal("1")
    assert pdv["available_qty"] == Decimal("3")


def test_remote_channel_shows_sold_out_when_shelf_is_at_the_margin():
    from shopman.shop.services import availability

    _seed_channels()
    _tracked_product("MARGEM-ULTIMOS", 2)

    web = availability.check("MARGEM-ULTIMOS", Decimal("1"), channel_ref="web")
    pdv = availability.check("MARGEM-ULTIMOS", Decimal("2"), channel_ref="pdv")

    assert web["ok"] is False
    assert web["available_qty"] == Decimal("0")
    assert pdv["ok"] is True


def test_cart_hold_on_remote_channel_respects_margin():
    from shopman.shop.adapters.stock import create_hold

    _seed_channels()
    _tracked_product("MARGEM-SACOLA", 3)

    too_much = create_hold("MARGEM-SACOLA", Decimal("2"), channel_ref="web")
    fits = create_hold("MARGEM-SACOLA", Decimal("1"), channel_ref="web")

    assert too_much["success"] is False
    assert fits["success"] is True


# ── Configurável por canal ──


def test_channel_override_wins_over_default():
    _seed_channels()
    web = Channel.objects.get(ref="web")
    web.config = {**web.config, "stock": {**web.config["stock"], "safety_margin": 5}}
    web.save(update_fields=["config"])

    assert ChannelConfig.for_channel("web").stock.safety_margin == 5
    assert ChannelConfig.for_channel("whatsapp").stock.safety_margin == 2


# ── Migração: bancos que já existem (o alpha) ──


def _migration():
    return importlib.import_module("shopman.shop.migrations.0064_remote_channel_safety_margin")


def test_migration_gives_existing_remote_channels_the_default():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web", name="Web", config={"stock": {"hold_ttl_minutes": 30, "allow_untracked": False}}
    )
    whatsapp = Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})
    ifood = Channel.objects.create(ref="ifood", name="iFood", config={"stock": {"check_on_commit": False}})
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={"stock": {"check_on_commit": False}})

    _migration().forwards(apps, None)
    _migration().forwards(apps, None)  # idempotente

    for channel in (web, whatsapp, ifood, pdv):
        channel.refresh_from_db()
    assert web.config == {"stock": {"hold_ttl_minutes": 30, "allow_untracked": False, "safety_margin": 2}}
    assert whatsapp.config == {"stock": {"safety_margin": 2}}
    assert ifood.config == {"stock": {"check_on_commit": False, "safety_margin": 2}}
    assert pdv.config == {"stock": {"check_on_commit": False}}
    assert ChannelConfig.for_channel("pdv").stock.safety_margin == 0


def test_migration_preserves_a_margin_chosen_in_admin():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(ref="web", name="Web", config={"stock": {"safety_margin": 0}})
    whatsapp = Channel.objects.create(ref="whatsapp", name="WhatsApp", config={"stock": {"safety_margin": 4}})

    _migration().forwards(apps, None)

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    assert web.config == {"stock": {"safety_margin": 0}}
    assert whatsapp.config == {"stock": {"safety_margin": 4}}
