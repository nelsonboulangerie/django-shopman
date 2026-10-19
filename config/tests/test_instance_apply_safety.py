"""Segurança da Instância: loja singleton, estado operacional e dump allowlist.

Um teste por achado do laudo adversarial de 18/10/2026 (WP-6, A6-1 a A6-3).
"""

from __future__ import annotations

import copy
import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from config.instance_descriptors import (
    InstanceDriftConflict,
    ShopSingletonViolation,
    UnsafeDescriptor,
    apply_to_database,
    load_descriptor,
    project_from_database,
)
from shopman.backstage.models import OperationTaskTemplate
from shopman.shop.models import Channel, InstanceApplyRecord, RuleConfig, Shop

ROOT = Path(__file__).resolve().parents[2]
COUNTER = ROOT / "config/instances/counter-minimal.json"
NELSON = ROOT / "config/instances/nelson.json"

HAPPY_HOUR = {
    "ref": "happy_hour",
    "enabled": True,
    "config": {
        "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
        "label": "Happy hour",
        "params": {"discount_percent": 25, "start": "17:30", "end": "18:00"},
        "channels": ["counter"],
        "priority": 10,
    },
}

ACTIVATION = {
    "by": "Maria",
    "approved_by": "Pablo",
    "reason": "Forno parado",
    "at": "2026-10-18T09:00:00-03:00",
}


def _counter_with_rule() -> dict:
    descriptor = load_descriptor(COUNTER)
    descriptor["bootstrap"]["rule_configs"] = [copy.deepcopy(HAPPY_HOUR)]
    return descriptor


def _operator_switches_counter_off() -> None:
    channel = Channel.objects.get(ref="counter")
    config = copy.deepcopy(channel.config)
    config["activation"] = dict(ACTIVATION)
    channel.is_active = False
    channel.config = config
    channel.save(update_fields=["is_active", "config"])


# ── A6-1 · a loja é uma só ────────────────────────────────────────────────


@pytest.mark.django_db
def test_seed_flush_over_a_used_database_keeps_one_shop_that_the_channels_point_to():
    from config.management.commands.seed import Command

    command = Command(stdout=StringIO())
    command._materialize_instance(NELSON)
    command._seed_shop()
    first_pk = Shop.objects.get().pk

    # O banco "já teve loja": o flush apaga a Shop sem reiniciar a sequência.
    command._flush()
    command._materialize_instance(NELSON)
    command._seed_shop()

    shop = Shop.objects.get()
    assert shop.pk != first_pk  # a sequência andou, e isso não importa mais
    assert shop.name == "Nelson Boulangerie"
    assert shop.brand_name == "Nelson Boulangerie"
    assert Shop.load().pk == shop.pk
    assert set(Channel.objects.values_list("shop_id", flat=True)) == {shop.pk}


@pytest.mark.django_db
def test_apply_and_dump_refuse_two_shops_naming_them():
    Shop.objects.create(name="Primeira")
    Shop.objects.create(name="Sobra")
    descriptor = load_descriptor(COUNTER)

    with pytest.raises(ShopSingletonViolation, match="há 2 lojas"):
        apply_to_database(descriptor, actor="test")
    with pytest.raises(ShopSingletonViolation, match="há 2 lojas"):
        project_from_database(descriptor)
    assert Channel.objects.count() == 0


@pytest.mark.django_db
def test_seed_shop_refuses_two_shops_instead_of_picking_one():
    from config.management.commands.seed import Command

    Shop.objects.create(name="Primeira")
    Shop.objects.create(name="Sobra")
    command = Command(stdout=StringIO())

    with pytest.raises(CommandError, match="a Shop é singleton"):
        command._seed_shop()


# ── A6-2 · configuração declarada × estado operacional ────────────────────


@pytest.mark.django_db
def test_apply_never_touches_operational_state():
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="test")
    _operator_switches_counter_off()

    result = apply_to_database(descriptor, actor="test")

    channel = Channel.objects.get(ref="counter")
    assert channel.is_active is False
    assert channel.config["activation"] == ACTIVATION
    assert result["changes"] == []


@pytest.mark.django_db
def test_apply_refuses_to_overwrite_what_the_operator_changed():
    descriptor = _counter_with_rule()
    apply_to_database(descriptor, actor="test")
    channel = Channel.objects.get(ref="counter")
    channel.config["stock"]["safety_margin"] = 5
    channel.save(update_fields=["config"])
    RuleConfig.objects.filter(ref="happy_hour").update(
        params={"discount_percent": 99, "start": "17:30", "end": "18:00"}
    )

    with pytest.raises(InstanceDriftConflict) as caught:
        apply_to_database(descriptor, actor="test")

    paths = {change["path"] for change in caught.value.conflicts}
    assert paths == {
        "/bootstrap/channels/counter/config/overrides/stock/safety_margin",
        "/bootstrap/rule_configs/happy_hour/config/params/discount_percent",
    }
    assert Channel.objects.get(ref="counter").config["stock"]["safety_margin"] == 5
    assert RuleConfig.objects.get(ref="happy_hour").params["discount_percent"] == 99
    assert InstanceApplyRecord.objects.count() == 1


@pytest.mark.django_db
def test_keep_drift_preserves_and_reports_and_overwrite_drift_restores():
    descriptor = _counter_with_rule()
    apply_to_database(descriptor, actor="test")
    RuleConfig.objects.filter(ref="happy_hour").update(
        params={"discount_percent": 99, "start": "17:30", "end": "18:00"}
    )

    kept = apply_to_database(descriptor, actor="test", on_drift="keep")
    assert RuleConfig.objects.get(ref="happy_hour").params["discount_percent"] == 99
    assert kept["summary"] == {"kept": 1}

    overwritten = apply_to_database(descriptor, actor="gestor", on_drift="overwrite")
    assert RuleConfig.objects.get(ref="happy_hour").params["discount_percent"] == 25
    assert overwritten["changes"] == [{
        "action": "overwritten",
        "path": "/bootstrap/rule_configs/happy_hour/config/params/discount_percent",
        "declared": 25,
        "database": 99,
    }]
    last = InstanceApplyRecord.objects.order_by("-pk").first()
    assert last.actor == "gestor"
    assert last.changes == overwritten["changes"]


@pytest.mark.django_db
def test_descriptor_upgrade_updates_what_nobody_touched_and_reports_it():
    declared = load_descriptor(COUNTER)
    apply_to_database(declared, actor="test")
    _operator_switches_counter_off()
    upgraded = copy.deepcopy(declared)
    stock = upgraded["bootstrap"]["channels"][0]["config"]["overrides"]["stock"]
    stock["safety_margin"] = 3
    del stock["allow_untracked"]

    result = apply_to_database(upgraded, actor="test")

    assert result["summary"] == {"remove": 1, "update": 1}
    channel = Channel.objects.get(ref="counter")
    assert channel.config["stock"]["safety_margin"] == 3
    assert "allow_untracked" not in channel.config["stock"]
    assert channel.is_active is False
    assert channel.config["activation"] == ACTIVATION


@pytest.mark.django_db
def test_dry_run_reports_without_writing():
    descriptor = load_descriptor(COUNTER)

    result = apply_to_database(descriptor, actor="test", dry_run=True)

    assert result["dry_run"] is True
    assert result["summary"] == {"create": 3}
    assert Shop.objects.count() == 0
    assert Channel.objects.count() == 0
    assert InstanceApplyRecord.objects.count() == 0


@pytest.mark.django_db
def test_every_apply_that_changes_leaves_a_trail_and_a_noop_does_not():
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="cli:pablo")
    apply_to_database(descriptor, actor="cli:pablo")

    record = InstanceApplyRecord.objects.get()
    assert record.instance_ref == "counter-minimal"
    assert record.actor == "cli:pablo"
    assert len(record.descriptor_sha256) == 64
    assert record.descriptor == descriptor
    assert {change["action"] for change in record.changes} == {"create"}
    assert record.applied_at is not None


@pytest.mark.django_db
def test_apply_requires_an_actor():
    with pytest.raises(ValueError, match="actor"):
        apply_to_database(load_descriptor(COUNTER), actor=" ")


@pytest.mark.django_db
def test_a_descriptor_cannot_declare_operational_state():
    descriptor = load_descriptor(COUNTER)
    descriptor["bootstrap"]["channels"][0]["config"]["overrides"]["activation"] = ACTIVATION
    with pytest.raises(ValueError, match="estado operacional não se declara"):
        apply_to_database(descriptor, actor="test")


@pytest.mark.django_db
def test_apply_command_is_a_dry_run_by_default_and_fails_on_conflict():
    stdout = StringIO()
    call_command("instance_descriptor", "apply", descriptor=COUNTER, stdout=stdout, stderr=StringIO())
    assert json.loads(stdout.getvalue())["dry_run"] is True
    assert Shop.objects.count() == 0

    call_command(
        "instance_descriptor", "apply", descriptor=COUNTER, commit=True,
        confirm_instance="counter-minimal", actor="cli:test", stdout=StringIO(),
    )
    channel = Channel.objects.get(ref="counter")
    channel.config["stock"]["safety_margin"] = 5
    channel.save(update_fields=["config"])

    with pytest.raises(CommandError, match="divergem"):
        call_command(
            "instance_descriptor", "apply", descriptor=COUNTER,
            stdout=StringIO(), stderr=StringIO(),
        )
    with pytest.raises(CommandError, match="--keep-drift"):
        call_command(
            "instance_descriptor", "apply", descriptor=COUNTER, commit=True,
            confirm_instance="counter-minimal", stdout=StringIO(),
        )
    assert Channel.objects.get(ref="counter").config["stock"]["safety_margin"] == 5


# ── A6-3 · o dump é allowlist e segredo nunca sai ─────────────────────────


@pytest.mark.django_db
def test_dump_does_not_export_operational_state():
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="test")
    _operator_switches_counter_off()
    channel = Channel.objects.get(ref="counter")
    channel.config["display"] = {"paused_skus": ["PAO-01"]}
    channel.save(update_fields=["config"])

    projected = project_from_database(descriptor)

    item = projected["bootstrap"]["channels"][0]
    assert "enabled" not in item
    assert "activation" not in item["config"]["overrides"]
    assert item["config"]["overrides"]["display"] == {}
    assert "Maria" not in json.dumps(projected)


SENSITIVE_VALUE = "valor-sensivel-7f3a9c"

CHANNEL_INJECTIONS = [
    # Nomes que a antiga denylist deixava passar (laudo A6-3).
    ("pix_key",),
    ("chave_pix",),
    ("webhook_hmac",),
    ("authorization",),
    ("signing",),
    ("senha",),
    ("certificado_a1",),
    # Dentro de um aspecto tipado.
    ("payment", "pix_key"),
    ("payment", "efi_client_secret"),
    ("notifications", "manychat_bearer"),
    # Nome inocente: só a allowlist pega, e é isso que prova que ela existe.
    ("merchant_extra",),
    ("stock", "observacao_livre"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", CHANNEL_INJECTIONS, ids=lambda p: ".".join(p))
def test_dump_refuses_any_channel_key_outside_the_allowlist(path):
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="test")
    channel = Channel.objects.get(ref="counter")
    node = channel.config
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = SENSITIVE_VALUE
    channel.save(update_fields=["config"])

    with pytest.raises(UnsafeDescriptor) as caught:
        project_from_database(descriptor)
    assert SENSITIVE_VALUE not in str(caught.value)

    with pytest.raises(CommandError):
        call_command("instance_descriptor", "dump", descriptor=COUNTER, stdout=StringIO())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mapping, value",
    [
        (("lifecycle",), {"pix_key": SENSITIVE_VALUE}),
        (("fulfillment", "stage_goal_minutes"), {"webhook_hmac": 5}),
        (("notifications", "routing"), {"Authorization: Bearer x": "sms"}),
    ],
    ids=["lifecycle", "stage_goal_minutes", "routing"],
)
def test_dump_validates_free_mappings_inside_the_channel_config(mapping, value):
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="test")
    channel = Channel.objects.get(ref="counter")
    node = channel.config
    for key in mapping[:-1]:
        node = node.setdefault(key, {})
    node[mapping[-1]] = value
    channel.save(update_fields=["config"])

    with pytest.raises(UnsafeDescriptor) as caught:
        project_from_database(descriptor)
    assert SENSITIVE_VALUE not in str(caught.value)


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["pix_key", "signing", "unknown_param"])
def test_dump_refuses_rule_params_the_rule_class_does_not_accept(key):
    descriptor = _counter_with_rule()
    apply_to_database(descriptor, actor="test")
    rule = RuleConfig.objects.get(ref="happy_hour")
    rule.params = {**rule.params, key: SENSITIVE_VALUE}
    RuleConfig.objects.filter(pk=rule.pk).update(params=rule.params)

    with pytest.raises(UnsafeDescriptor, match="params") as caught:
        project_from_database(descriptor)
    assert SENSITIVE_VALUE not in str(caught.value)


@pytest.mark.django_db
def test_dump_refuses_unknown_task_config_keys():
    descriptor = load_descriptor(NELSON)
    apply_to_database(descriptor, actor="test")
    task = OperationTaskTemplate.objects.order_by("ref").first()
    task.config = {**task.config, "webhook_url": "https://hooks.example/" + SENSITIVE_VALUE}
    task.save(update_fields=["config"])

    with pytest.raises(UnsafeDescriptor, match="config.webhook_url") as caught:
        project_from_database(descriptor)
    assert SENSITIVE_VALUE not in str(caught.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "value",
    [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl",
        "whsec_abcdefghijklmnop1234",
        "-----BEGIN CERTIFICATE-----",
    ],
    ids=["jwt", "stripe-webhook", "certificate"],
)
def test_dump_refuses_secret_shaped_values_even_under_allowed_keys(value):
    descriptor = load_descriptor(COUNTER)
    apply_to_database(descriptor, actor="test")
    channel = Channel.objects.get(ref="counter")
    channel.config["handle_placeholder"] = value
    channel.save(update_fields=["config"])

    with pytest.raises(UnsafeDescriptor, match="secret-like value") as caught:
        project_from_database(descriptor)
    assert value not in str(caught.value)
