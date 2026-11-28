"""Política de rollout: autoaceite remoto vira manual sem esmagar configuração."""

from __future__ import annotations

import importlib
from io import StringIO

import pytest
from django.apps import apps

from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


def test_seeded_owned_remote_channels_require_human_confirmation():
    from config.management.commands.seed import NELSON_INSTANCE_DESCRIPTOR, Command
    from shopman.shop.config import ChannelConfig

    command = Command()
    command.stdout = StringIO()
    command._materialize_instance(NELSON_INSTANCE_DESCRIPTOR)
    channels = command._instance_channels()

    # A loja online paga ao pedir e tem prazo de aceite (ADR-036): quem não aceita
    # a tempo CANCELA e devolve, nunca aceita sozinho.
    assert ChannelConfig.for_channel(channels["web"]).confirmation.mode == "auto_cancel"
    assert ChannelConfig.for_channel(channels["whatsapp"]).confirmation.mode == "manual"
    assert ChannelConfig.for_channel(channels["pdv"]).confirmation.mode == "immediate"


def test_migration_only_changes_explicit_remote_auto_confirm():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web",
        name="Web",
        config={
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 7, "stale_new_alert_minutes": 12},
            "payment": {"timing": "post_commit"},
        },
    )
    whatsapp = Channel.objects.create(
        ref="whatsapp",
        name="WhatsApp",
        config={"confirmation": {"mode": "manual", "stale_new_alert_minutes": 30}},
    )
    ifood = Channel.objects.create(
        ref="ifood",
        name="iFood",
        config={"confirmation": {"mode": "auto_confirm", "timeout_minutes": 2}},
    )

    migration = importlib.import_module("shopman.shop.migrations.0054_disable_remote_auto_confirmation")
    migration.forwards(apps, None)

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    ifood.refresh_from_db()
    assert web.config == {
        "confirmation": {"mode": "manual", "timeout_minutes": 7, "stale_new_alert_minutes": 12},
        "payment": {"timing": "post_commit"},
    }
    assert whatsapp.config == {"confirmation": {"mode": "manual", "stale_new_alert_minutes": 30}}
    assert ifood.config == {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 2}}
