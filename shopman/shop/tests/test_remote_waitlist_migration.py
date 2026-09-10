"""Contrato da ativação incremental da fermata no banco já existente."""

from importlib import import_module

import pytest
from django.apps import apps

from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db

migration = import_module(
    "shopman.shop.migrations.0041_enable_remote_waitlist_notifications"
)


def test_migration_updates_only_owned_remote_channels_and_preserves_other_config():
    web = Channel.objects.create(
        ref="web",
        name="Loja online",
        config={
            "short_name": "Site",
            "waitlist": {"enabled": False, "legacy": "preserve-only-on-reverse"},
            "notifications": {"legacy": "discarded-by-policy"},
        },
    )
    whatsapp = Channel.objects.create(
        ref="whatsapp",
        name="WhatsApp",
        config={"confirmation": {"mode": "auto_confirm"}},
    )
    ifood = Channel.objects.create(
        ref="ifood",
        name="iFood",
        config={"waitlist": {"enabled": False}},
    )

    migration.forwards(apps, None)

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    ifood.refresh_from_db()
    for channel in (web, whatsapp):
        assert channel.config["waitlist"] == migration.WAITLIST_POLICY
        assert channel.config["notifications"]["backend"] == "manychat"
        assert channel.config["notifications"]["fallback_chain"] == ["sms", "email"]
    assert web.config["short_name"] == "Site"
    assert web.config["notifications"]["legacy"] == "discarded-by-policy"
    assert whatsapp.config["confirmation"] == {"mode": "auto_confirm"}
    assert ifood.config == {"waitlist": {"enabled": False}}


def test_reverse_stops_new_entries_without_reintroducing_console_delivery():
    web = Channel.objects.create(ref="web", name="Loja online", config={})
    migration.forwards(apps, None)
    migration.backwards(apps, None)

    web.refresh_from_db()
    assert web.config["waitlist"]["enabled"] is False
    assert web.config["notifications"] == migration.NOTIFICATION_POLICY
