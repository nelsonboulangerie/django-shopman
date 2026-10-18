"""An Instance composes kernels through DB configuration without deforming them."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.core.checks import Error, Tags, run_checks
from django.test import override_settings
from shopman.cashman.models.terminal import Terminal

from config.instance_descriptors import apply_to_database, load_descriptor
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop

ROOT = Path(__file__).resolve().parents[2]
COUNTER = ROOT / "config/instances/counter-minimal.json"


@pytest.mark.django_db
@pytest.mark.instance_runtime_strict
def test_counter_instance_materializes_and_boots_from_its_own_contract():
    descriptor = load_descriptor(COUNTER)

    result = apply_to_database(descriptor)

    assert result["instance"] == "counter-minimal"
    assert Shop.objects.get().name == "Counter minimal"
    assert list(Channel.objects.values_list("ref", flat=True)) == ["counter"]
    assert Group.objects.get(name="Counter operator").permissions.filter(
        content_type__app_label="cashman",
        codename="operate_pos",
    ).exists()

    config = ChannelConfig.for_channel("counter")
    assert config.confirmation.mode == "immediate"
    assert config.payment.method == "cash"
    assert config.payment.timing == "external"
    assert config.stock.check_on_commit is False
    assert config.stock.allow_untracked is False
    assert config.stock.sells_nonconforming is True
    assert config.stock.safety_margin == 0

    with override_settings(SHOPMAN_POS_CHANNEL_REF="counter"):
        assert Terminal.default().channel_ref == "counter"
        assert not [
            message
            for message in run_checks(tags=[Tags.models])
            if isinstance(message, Error)
        ]


def test_counter_instance_names_every_deploy_value_needed_to_select_its_counter():
    descriptor = load_descriptor(COUNTER)

    assert "SHOPMAN_POS_CHANNEL_REF" in descriptor["ownership"]["deploy"]
    assert descriptor["bootstrap"]["channels"][0]["ref"] == "counter"
