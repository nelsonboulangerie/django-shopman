"""Instance evolution preserves tenant-owned and operational data."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from config.instance_descriptors import apply_to_database, load_descriptor
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop

ROOT = Path(__file__).resolve().parents[2]
COUNTER = ROOT / "config/instances/counter-minimal.json"


@pytest.mark.django_db
def test_descriptor_upgrade_preserves_tenant_rows_and_memberships():
    declared = load_descriptor(COUNTER)
    apply_to_database(declared, actor="test")
    shop = Shop.objects.get()
    persona = Group.objects.get(name="Counter operator")
    operator = get_user_model().objects.create_user(username="tenant-operator")
    operator.groups.add(persona)
    tenant_channel = Channel.objects.create(
        ref="tenant-pop-up",
        name="Tenant pop-up",
        shop=shop,
        config={"payment": {"method": "credit", "timing": "external"}},
    )

    upgraded = copy.deepcopy(declared)
    counter = upgraded["bootstrap"]["channels"][0]
    counter["config"]["name"] = "Counter v2"
    counter["config"]["overrides"]["payment"]["method"] = ["cash", "credit"]
    apply_to_database(upgraded, actor="test")

    operator.refresh_from_db()
    tenant_channel.refresh_from_db()
    assert operator.groups.filter(pk=persona.pk).exists()
    assert tenant_channel.name == "Tenant pop-up"
    assert ChannelConfig.for_channel("tenant-pop-up").payment.method == "credit"
    assert Channel.objects.get(ref="counter").name == "Counter v2"
    assert ChannelConfig.for_channel("counter").payment.method == ["cash", "credit"]


@pytest.mark.django_db
def test_conflicting_upgrade_rolls_back_without_touching_tenant_data():
    declared = load_descriptor(COUNTER)
    apply_to_database(declared, actor="test")
    shop = Shop.objects.get()
    tenant_channel = Channel.objects.create(
        ref="tenant-pop-up",
        name="Tenant pop-up",
        shop=shop,
    )
    conflicting = copy.deepcopy(declared)
    conflicting["bootstrap"]["channels"][0]["config"]["name"] = "Must roll back"
    conflicting["bootstrap"]["rule_configs"] = [{
        "ref": "invalid-rule",
        "enabled": True,
        "config": {
            "rule_path": "shopman.shop.rules.validation.BusinessHoursRule",
            "label": "Invalid",
            "params": {},
            "channels": ["missing-channel"],
            "priority": 10,
        },
    }]

    with pytest.raises(ValueError, match="references unknown channel"):
        apply_to_database(conflicting, actor="test")

    assert Channel.objects.get(ref="counter").name == "Counter"
    assert Channel.objects.get(pk=tenant_channel.pk).name == "Tenant pop-up"
