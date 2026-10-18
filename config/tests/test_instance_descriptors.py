from __future__ import annotations

import copy
import json
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from config.instance_descriptors import (
    UnsafeDescriptor,
    assert_export_safe,
    descriptor_diff,
    load_descriptor,
    project_from_database,
)
from shopman.shop.models import Channel, RuleConfig, Shop

ROOT = Path(__file__).resolve().parents[2]
DECLARED = ROOT / "config/instances/counter-minimal.json"


@pytest.mark.django_db
def test_projection_is_deterministic_and_read_only():
    shop = Shop.objects.create(name="Counter lab")
    channel = Channel.objects.create(
        ref="counter",
        name="Balcão",
        shop=shop,
        config={"payment": {"method": "cash"}},
    )
    rule = RuleConfig.objects.create(
        ref="happy-hour",
        rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Happy hour",
        params={"discount_percent": 10},
        priority=20,
    )
    rule.channels.add(channel)
    group = Group.objects.create(name="Counter operator")
    group.permissions.add(Permission.objects.get(codename="operate_pos"))
    template = load_descriptor(DECLARED)

    with CaptureQueriesContext(connection) as queries:
        first = project_from_database(template)
        second = project_from_database(template)

    assert first == second
    assert first["instance"]["display_name"] == "Counter lab"
    assert first["bootstrap"]["channels"][0]["ref"] == "counter"
    assert first["bootstrap"]["rule_configs"][0]["config"]["channels"] == ["counter"]
    assert first["bootstrap"]["rbac_personas"][0]["permissions"] == ["cashman.operate_pos"]
    statements = [query["sql"].lstrip().upper() for query in queries.captured_queries]
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)


def test_diff_is_stable_and_does_not_mutate_inputs():
    declared = load_descriptor(DECLARED)
    actual = copy.deepcopy(declared)
    actual["instance"]["display_name"] = "Changed"
    before = copy.deepcopy(declared)
    assert descriptor_diff(declared, actual) == [{
        "path": "/instance/display_name",
        "declared": "Counter minimal",
        "database": "Changed",
    }]
    assert declared == before


def test_export_refuses_secret_like_keys_and_values():
    with pytest.raises(UnsafeDescriptor, match="secret-like key"):
        assert_export_safe({"channels": [{"config": {"api_token": "value"}}]})
    with pytest.raises(UnsafeDescriptor, match="secret-like value"):
        assert_export_safe({"channels": [{"config": {"endpoint": "redis://user:pass@cache/0"}}]})


@pytest.mark.django_db
def test_dump_command_emits_json_without_writing():
    Shop.objects.create(name="Command lab")
    before = {
        "shops": Shop.objects.count(),
        "channels": Channel.objects.count(),
        "rules": RuleConfig.objects.count(),
        "groups": Group.objects.count(),
    }
    stdout = StringIO()
    call_command("instance_descriptor", "dump", descriptor=DECLARED, stdout=stdout)
    document = json.loads(stdout.getvalue())
    after = {
        "shops": Shop.objects.count(),
        "channels": Channel.objects.count(),
        "rules": RuleConfig.objects.count(),
        "groups": Group.objects.count(),
    }
    assert document["instance"]["display_name"] == "Command lab"
    assert after == before


@pytest.mark.django_db
def test_diff_refuses_an_unsafe_declared_descriptor_before_output(tmp_path):
    declared = load_descriptor(DECLARED)
    declared["bootstrap"]["channels"][0]["config"] = {
        "endpoint": "redis://user:password@cache.internal/0"
    }
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(declared), encoding="utf-8")
    stdout = StringIO()
    with pytest.raises(CommandError, match="secret-like value"):
        call_command("instance_descriptor", "diff", descriptor=unsafe, stdout=stdout)
    assert stdout.getvalue() == ""
