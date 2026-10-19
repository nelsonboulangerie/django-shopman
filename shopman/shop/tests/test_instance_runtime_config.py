"""The database is the only runtime authority for Instance configuration."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from shopman.shop.config import ChannelConfig, InstanceConfigurationError
from shopman.shop.models import Channel
from shopman.shop.services import availability, fomo, waitlist
from shopman.storefront.presentation import checkout

pytestmark = pytest.mark.django_db


def test_materialized_channel_is_resolved_without_reading_the_descriptor(monkeypatch):
    from config import instance_descriptors

    Channel.objects.create(
        ref="counter",
        name="Counter",
        config={"payment": {"method": "credit", "timing": "external"}},
    )

    def descriptor_is_not_a_runtime_source(*args, **kwargs):
        raise AssertionError("runtime tried to read the bootstrap descriptor")

    monkeypatch.setattr(instance_descriptors, "load_descriptor", descriptor_is_not_a_runtime_source)

    resolved = ChannelConfig.for_channel("counter")

    assert resolved.payment.method == "credit"
    assert resolved.payment.timing == "external"


@pytest.mark.parametrize(
    "resolve",
    [
        pytest.param(lambda: waitlist.config("missing"), id="waitlist"),
        pytest.param(lambda: fomo._channel_config("missing"), id="fomo"),
        pytest.param(lambda: availability._channel_hold_ttl_minutes("missing"), id="hold-ttl"),
        pytest.param(lambda: checkout._payment_methods("missing"), id="checkout-payment-methods"),
    ],
)
def test_missing_channel_never_becomes_a_hardcoded_runtime_policy(resolve):
    with pytest.raises(InstanceConfigurationError, match="not materialized"):
        resolve()


def test_payment_adapter_does_not_invent_config_when_channel_is_missing():
    from shopman.shop.services.payment import _adapter_config

    order = SimpleNamespace(ref="ORDER-1", channel_ref="missing")

    with pytest.raises(InstanceConfigurationError, match="not materialized"):
        _adapter_config(order, method="pix")


def _runtime_sources():
    root = Path(__file__).resolve().parents[2]
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts or "admin" in path.parts:
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_runtime_does_not_import_the_bootstrap_descriptor():
    violations = []
    for path, tree in _runtime_sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "config.instance_descriptors":
                violations.append(f"{path}:{node.lineno}")
            if isinstance(node, ast.Import):
                violations.extend(
                    f"{path}:{node.lineno}"
                    for alias in node.names
                    if alias.name == "config.instance_descriptors"
                )
    assert violations == []


def test_runtime_does_not_catch_channel_config_and_substitute_policy():
    violations = []
    for path, tree in _runtime_sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            calls = (child for statement in node.body for child in ast.walk(statement))
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "for_channel"
                for child in calls
            ):
                violations.append(f"{path}:{node.lineno}")
    assert violations == []
