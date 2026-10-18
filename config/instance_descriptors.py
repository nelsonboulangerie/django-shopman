"""Read-only projection and diff for versioned Instance descriptors."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils.text import slugify

SECRET_KEY_RE = re.compile(
    r"(?:secret|password|passwd|token|credential|api[_-]?key|private[_-]?key)",
    re.I,
)
SECRET_VALUE_RES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\b(?:postgres(?:ql)?|redis)://[^\s/@:]+:[^\s/@]+@", re.I),
)


class UnsafeDescriptor(ValueError):
    """The projection contains material that must never be emitted."""


class UnsupportedInstanceSection(ValueError):
    """A descriptor asks to mutate configuration without a proven DB owner."""


def load_descriptor(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _config_item(ref: str, *, enabled: bool | None = None, config: dict | None = None) -> dict:
    item: dict = {"ref": ref}
    if enabled is not None:
        item["enabled"] = enabled
    if config:
        item["config"] = config
    return item


def _project_templates() -> list[dict]:
    from shopman.backstage.models import OperationChecklistTemplate

    projected = []
    templates = OperationChecklistTemplate.objects.prefetch_related(
        "task_links__task_template"
    ).order_by("ref")
    for template in templates:
        tasks = []
        for link in template.task_links.all().order_by("sort_order", "task_template__ref"):
            task = link.task_template
            tasks.append({
                "ref": task.ref,
                "title": task.title,
                "description": task.description,
                "moment": task.moment,
                "area": task.area,
                "evidence_required": task.evidence_required,
                "expected_role": task.expected_role,
                "required": link.effective_required,
                "enabled": task.is_active,
                "system": task.is_system,
                "task_sort_order": task.sort_order,
                "sort_order": link.sort_order,
                "config": task.config,
            })
        projected.append(_config_item(
            template.ref,
            enabled=template.is_active,
            config={
                "title": template.title,
                "description": template.description,
                "moment": template.moment,
                "sort_order": template.sort_order,
                "tasks": tasks,
            },
        ))
    return projected


def project_from_database(template: dict) -> dict:
    """Return the deterministic DB projection; never mutate the template or DB."""
    from shopman.shop.models import Channel, RuleConfig, Shop

    descriptor = {
        "schema_version": template["schema_version"],
        "instance": copy.deepcopy(template["instance"]),
        "ownership": copy.deepcopy(template["ownership"]),
        "bootstrap": {section: [] for section in template["bootstrap"]},
    }
    shop = Shop.objects.order_by("pk").first()
    if shop is not None:
        descriptor["instance"]["display_name"] = shop.name

    descriptor["bootstrap"]["channels"] = [
        _config_item(
            channel.ref,
            enabled=channel.is_active,
            config={
                "name": channel.name,
                "commerce_policy": channel.commerce_policy,
                "display_order": channel.display_order,
                "overrides": channel.config,
            },
        )
        for channel in Channel.objects.order_by("ref")
    ]
    descriptor["bootstrap"]["rule_configs"] = [
        _config_item(
            rule.ref,
            enabled=rule.enabled,
            config={
                "rule_path": rule.rule_path,
                "label": rule.label,
                "params": rule.params,
                "channels": sorted(rule.channels.values_list("ref", flat=True)),
                "priority": rule.priority,
            },
        )
        for rule in RuleConfig.objects.prefetch_related("channels").order_by("ref")
    ]
    descriptor["bootstrap"]["rbac_personas"] = [
        {
            "ref": slugify(group.name),
            "permissions": sorted(
                f"{app_label}.{codename}"
                for app_label, codename in group.permissions.values_list(
                    "content_type__app_label", "codename"
                )
            ),
        }
        for group in Group.objects.prefetch_related("permissions__content_type").order_by("name")
    ]
    refs = [item["ref"] for item in descriptor["bootstrap"]["rbac_personas"]]
    if len(refs) != len(set(refs)):
        raise ValueError("group names produce duplicate persona refs")
    descriptor["bootstrap"]["templates"] = _project_templates()
    assert_export_safe(descriptor["bootstrap"])
    return descriptor


def assert_export_safe(value, path: str = "bootstrap") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(key):
                raise UnsafeDescriptor(f"secret-like key at {path}.{key}")
            assert_export_safe(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_export_safe(child, f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_VALUE_RES):
        raise UnsafeDescriptor(f"secret-like value at {path}")


def descriptor_diff(expected, actual, path: str = "") -> list[dict]:
    """Return stable JSON-pointer changes from versioned descriptor to DB projection."""
    if type(expected) is not type(actual):
        return [{"path": path or "/", "declared": expected, "database": actual}]
    if isinstance(expected, dict):
        changes = []
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in expected:
                changes.append({"path": child_path, "declared": None, "database": actual[key]})
            elif key not in actual:
                changes.append({"path": child_path, "declared": expected[key], "database": None})
            else:
                changes.extend(descriptor_diff(expected[key], actual[key], child_path))
        return changes
    if isinstance(expected, list):
        if expected == actual:
            return []
        return [{"path": path or "/", "declared": expected, "database": actual}]
    if expected != actual:
        return [{"path": path or "/", "declared": expected, "database": actual}]
    return []


def _permission(permission_ref: str) -> Permission:
    app_label, codename = permission_ref.split(".", 1)
    try:
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )
    except Permission.DoesNotExist as exc:
        raise ValueError(f"unknown permission: {permission_ref}") from exc


def _get_or_update(model, *, lookup: dict, defaults: dict):
    obj, created = model.objects.get_or_create(**lookup, defaults=defaults)
    if created:
        return obj, True

    changed_fields = [
        field
        for field, value in defaults.items()
        if getattr(obj, field) != value
    ]
    if changed_fields:
        for field in changed_fields:
            setattr(obj, field, defaults[field])
        obj.save(update_fields=changed_fields)
    return obj, False


def _apply_channels(items: list[dict]) -> int:
    from shopman.shop.models import Channel, Shop

    shop = Shop.objects.order_by("pk").first()
    changed = 0
    for item in items:
        config = item.get("config", {})
        _object, created = _get_or_update(
            Channel,
            lookup={"ref": item["ref"]},
            defaults={
                "shop": shop,
                "name": config.get("name", ""),
                "commerce_policy": config.get("commerce_policy", "order"),
                "display_order": config.get("display_order", 0),
                "config": config.get("overrides", {}),
                "is_active": item.get("enabled", True),
            },
        )
        changed += int(created)
    return changed


def _apply_rules(items: list[dict]) -> int:
    from shopman.shop.models import Channel, RuleConfig

    changed = 0
    for item in items:
        config = item.get("config", {})
        required = {"rule_path", "label", "params", "channels", "priority"}
        if set(config) != required:
            raise ValueError(f"rule {item['ref']} requires {sorted(required)}")
        rule, created = _get_or_update(
            RuleConfig,
            lookup={"ref": item["ref"]},
            defaults={
                "rule_path": config["rule_path"],
                "label": config["label"],
                "enabled": item.get("enabled", True),
                "params": config["params"],
                "priority": config["priority"],
            },
        )
        channel_refs = config["channels"]
        channels = list(Channel.objects.filter(ref__in=channel_refs).order_by("ref"))
        if [channel.ref for channel in channels] != sorted(channel_refs):
            raise ValueError(f"rule {item['ref']} references unknown channel")
        current_channel_ids = set(rule.channels.values_list("pk", flat=True))
        desired_channel_ids = {channel.pk for channel in channels}
        if current_channel_ids != desired_channel_ids:
            rule.channels.set(channels)
        changed += int(created)
    return changed


def _apply_personas(items: list[dict]) -> int:
    changed = 0
    for item in items:
        group, created = Group.objects.get_or_create(name=item["ref"])
        permissions = [_permission(ref) for ref in item["permissions"]]
        current_permission_ids = set(group.permissions.values_list("pk", flat=True))
        desired_permission_ids = {permission.pk for permission in permissions}
        if current_permission_ids != desired_permission_ids:
            group.permissions.set(permissions)
        changed += int(created)
    return changed


def _apply_templates(items: list[dict]) -> int:
    from shopman.backstage.models import (
        OperationChecklistTemplate,
        OperationChecklistTemplateTask,
        OperationTaskTemplate,
    )

    changed = 0
    for item in items:
        config = item.get("config", {})
        required = {"title", "description", "moment", "sort_order", "tasks"}
        if set(config) != required:
            raise ValueError(f"template {item['ref']} requires {sorted(required)}")
        template, created = _get_or_update(
            OperationChecklistTemplate,
            lookup={"ref": item["ref"]},
            defaults={
                "title": config["title"],
                "description": config["description"],
                "moment": config["moment"],
                "is_active": item.get("enabled", True),
                "sort_order": config["sort_order"],
            },
        )
        changed += int(created)
        for task_data in config["tasks"]:
            task, task_created = _get_or_update(
                OperationTaskTemplate,
                lookup={"ref": task_data["ref"]},
                defaults={
                    "title": task_data["title"],
                    "description": task_data["description"],
                    "moment": task_data["moment"],
                    "area": task_data["area"],
                    "evidence_required": task_data["evidence_required"],
                    "expected_role": task_data["expected_role"],
                    "is_required": task_data["required"],
                    "is_active": task_data["enabled"],
                    "is_system": task_data["system"],
                    "sort_order": task_data["task_sort_order"],
                    "config": task_data["config"],
                },
            )
            _get_or_update(
                OperationChecklistTemplateTask,
                lookup={
                    "checklist_template": template,
                    "task_template": task,
                },
                defaults={
                    "sort_order": task_data["sort_order"],
                    "is_required_override": task_data["required"],
                },
            )
            changed += int(task_created)
    return changed


@transaction.atomic
def apply_to_database(descriptor: dict) -> dict:
    """Apply supported bootstrap configuration atomically and idempotently."""
    from shopman.shop.models import Shop

    bootstrap = descriptor["bootstrap"]
    assert_export_safe(bootstrap)
    unsupported = {
        section: bootstrap[section]
        for section in ("pipelines", "pricing_policies", "units", "fiscal_profiles")
        if bootstrap[section]
    }
    if unsupported:
        raise UnsupportedInstanceSection(
            f"no proven DB owner for: {', '.join(sorted(unsupported))}"
        )

    shop = Shop.objects.order_by("pk").first()
    shop_created = False
    if shop is None:
        shop = Shop.objects.create(name=descriptor["instance"]["display_name"])
        shop_created = True
    elif shop.name != descriptor["instance"]["display_name"]:
        shop.name = descriptor["instance"]["display_name"]
        shop.save(update_fields=["name"])

    return {
        "instance": descriptor["instance"]["ref"],
        "shop_created": shop_created,
        "channels_created": _apply_channels(bootstrap["channels"]),
        "rules_created": _apply_rules(bootstrap["rule_configs"]),
        "personas_created": _apply_personas(bootstrap["rbac_personas"]),
        "templates_created": _apply_templates(bootstrap["templates"]),
    }
