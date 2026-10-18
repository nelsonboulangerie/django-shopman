"""Read-only projection and diff for versioned Instance descriptors."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from django.contrib.auth.models import Group
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
