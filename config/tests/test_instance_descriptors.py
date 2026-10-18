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
    UnsupportedInstanceSection,
    apply_to_database,
    assert_export_safe,
    descriptor_diff,
    load_descriptor,
    project_from_database,
)
from shopman.backstage.models import (
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationTaskTemplate,
)
from shopman.shop.models import Channel, RuleConfig, Shop

ROOT = Path(__file__).resolve().parents[2]
DECLARED = ROOT / "config/instances/counter-minimal.json"
NELSON = ROOT / "config/instances/nelson.json"


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
    assert first["bootstrap"]["rbac_personas"][0] == {
        "ref": "counter-operator",
        "name": "Counter operator",
        "permissions": ["cashman.operate_pos"],
    }
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


@pytest.mark.django_db
def test_apply_is_idempotent():
    descriptor = load_descriptor(DECLARED)
    first = apply_to_database(descriptor)
    snapshot = project_from_database(descriptor)
    with CaptureQueriesContext(connection) as queries:
        second = apply_to_database(descriptor)
    assert first["shop_created"] is True
    assert first["channels_created"] == 1
    assert first["personas_created"] == 1
    assert second == {
        "instance": "counter-minimal",
        "shop_created": False,
        "channels_created": 0,
        "rules_created": 0,
        "personas_created": 0,
        "templates_created": 0,
    }
    statements = [query["sql"].lstrip().upper() for query in queries.captured_queries]
    assert not any(statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
    assert project_from_database(descriptor) == snapshot


@pytest.mark.django_db
def test_apply_rolls_back_everything_on_late_failure():
    descriptor = load_descriptor(DECLARED)
    descriptor["bootstrap"]["rbac_personas"][0]["permissions"] = ["missing.permission"]
    with pytest.raises(ValueError, match="unknown permission"):
        apply_to_database(descriptor)
    assert Shop.objects.count() == 0
    assert Channel.objects.count() == 0
    assert Group.objects.count() == 0


@pytest.mark.django_db
def test_apply_rejects_unowned_nonempty_section():
    descriptor = load_descriptor(DECLARED)
    descriptor["bootstrap"]["units"] = [{"ref": "each", "symbol": "un"}]
    with pytest.raises(UnsupportedInstanceSection, match="units"):
        apply_to_database(descriptor)


@pytest.mark.django_db
def test_apply_round_trips_operational_templates():
    descriptor = load_descriptor(DECLARED)
    descriptor["bootstrap"]["templates"] = [{
        "ref": "opening",
        "enabled": True,
        "config": {
            "title": "Opening",
            "description": "Start the shift",
            "moment": "opening",
            "sort_order": 10,
            "tasks": [{
                "ref": "open-register",
                "title": "Open register",
                "description": "Count the float",
                "moment": "opening",
                "area": "cash",
                "evidence_required": "number",
                "expected_role": "counter-operator",
                "required": True,
                "enabled": True,
                "system": False,
                "task_sort_order": 5,
                "sort_order": 20,
                "config": {"minimum": 0},
            }],
        },
    }]

    apply_to_database(descriptor)

    projected = project_from_database(descriptor)
    assert projected["bootstrap"]["templates"] == descriptor["bootstrap"]["templates"]
    assert OperationChecklistTemplate.objects.count() == 1
    assert OperationTaskTemplate.objects.get().sort_order == 5
    assert OperationChecklistTemplateTask.objects.get().sort_order == 20


@pytest.mark.django_db
def test_nelson_descriptor_materializes_all_database_owned_configuration():
    descriptor = load_descriptor(NELSON)

    apply_to_database(descriptor)

    assert project_from_database(descriptor) == descriptor


@pytest.mark.django_db
def test_nelson_descriptor_rbac_matches_the_release_group_contract():
    descriptor = load_descriptor(NELSON)
    call_command("setup_groups", verbosity=0)

    projected = project_from_database(descriptor)

    assert projected["bootstrap"]["rbac_personas"] == descriptor["bootstrap"]["rbac_personas"]


@pytest.mark.django_db
def test_nelson_seed_refuses_a_different_instance_descriptor():
    from config.management.commands.seed import Command

    command = Command(stdout=StringIO())
    with pytest.raises(CommandError, match="exige instance.ref='nelson'"):
        command._materialize_instance(DECLARED)
    assert Shop.objects.count() == 0


@pytest.mark.django_db
def test_apply_command_requires_exact_instance_confirmation():
    stdout = StringIO()
    with pytest.raises(CommandError, match="--confirm-instance counter-minimal"):
        call_command("instance_descriptor", "apply", descriptor=DECLARED, stdout=stdout)
    assert Shop.objects.count() == 0
    call_command(
        "instance_descriptor",
        "apply",
        descriptor=DECLARED,
        confirm_instance="counter-minimal",
        stdout=stdout,
    )
    assert Shop.objects.get().name == "Counter minimal"
