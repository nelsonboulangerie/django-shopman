#!/usr/bin/env python
"""Validate the sovereign boundary between Admin/Unfold and operator surfaces."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs/reference/admin-surface-boundary.json"
SURFACE_REGISTRY_PATH = ROOT / "surfaces/registry.json"
ROUTINE_FREQUENCIES = frozenset({"continuous", "per_shift", "daily"})

# `python scripts/check_admin_surface_boundary.py` puts only `scripts/` on
# `sys.path`; CI intentionally invokes the gate that way through `make admin`.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def registered_model_admins() -> set[str]:
    """Return the live Django Admin registry, not a source-code approximation."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    os.environ.setdefault("DATABASE_URL", "")
    import django

    django.setup()
    from django.contrib import admin

    return {model._meta.label_lower for model in admin.site._registry}


def registered_custom_admin_pages() -> set[str]:
    """Return the concrete custom pages registered by the Unfold surface gate."""
    from scripts.check_unfold_canonical import CANONICAL_ADMIN_SURFACES

    return {
        surface.id
        for surface in CANONICAL_ADMIN_SURFACES
        if surface.kind == "canonical-admin-unfold-page"
    }


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def validate_contract(
    contract: dict[str, Any],
    *,
    root: Path = ROOT,
    runtime_models: set[str] | None = None,
    runtime_custom_pages: set[str] | None = None,
    surface_registry: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    dimensions = contract.get("dimensions", {})
    allowed_frequencies = set(dimensions.get("frequency", ()))
    allowed_audiences = set(dimensions.get("audience", ()))
    allowed_risks = set(dimensions.get("risk", ()))
    allowed_admin_fits = set(dimensions.get("admin_fit", ()))
    routine_frequencies = set(dimensions.get("routine_frequencies", ()))
    if routine_frequencies != ROUTINE_FREQUENCIES:
        errors.append("dimensions.routine_frequencies must be continuous, per_shift and daily")

    def validate_dimensions(entry: dict[str, Any], location: str) -> None:
        for field, allowed in (
            ("frequency", allowed_frequencies),
            ("audience", allowed_audiences),
            ("risk", allowed_risks),
        ):
            if entry.get(field) not in allowed:
                errors.append(f"{location}: invalid or missing {field}={entry.get(field)!r}")

    def validate_admin_fit(entry: dict[str, Any], location: str) -> None:
        if entry.get("admin_fit") not in allowed_admin_fits:
            errors.append(f"{location}: invalid or missing admin_fit={entry.get('admin_fit')!r}")

    groups = contract.get("admin_model_groups", [])
    group_ids = [group.get("id") for group in groups]
    for duplicate in sorted(_duplicates(group_ids)):
        errors.append(f"duplicate admin_model_group id: {duplicate}")

    classified_models: list[str] = []
    for group in groups:
        location = f"admin_model_group {group.get('id')!r}"
        validate_dimensions(group, location)
        validate_admin_fit(group, location)
        models = group.get("models")
        if not isinstance(models, list) or not models:
            errors.append(f"{location}: models must be a non-empty list")
            continue
        classified_models.extend(models)

    for duplicate in sorted(_duplicates(classified_models)):
        errors.append(f"ModelAdmin classified more than once: {duplicate}")
    if runtime_models is not None:
        classified = set(classified_models)
        for model in sorted(runtime_models - classified):
            errors.append(f"unclassified live ModelAdmin: {model}")
        for model in sorted(classified - runtime_models):
            errors.append(f"stale ModelAdmin classification: {model}")

    custom_pages = contract.get("custom_admin_pages", [])
    page_ids = [page.get("id") for page in custom_pages]
    for duplicate in sorted(_duplicates(page_ids)):
        errors.append(f"custom Admin page classified more than once: {duplicate}")
    for page in custom_pages:
        location = f"custom_admin_page {page.get('id')!r}"
        validate_dimensions(page, location)
        validate_admin_fit(page, location)
        controller = page.get("controller", "")
        if not controller or not (root / controller).is_file():
            errors.append(f"{location}: missing controller evidence {controller!r}")
    if runtime_custom_pages is not None:
        classified_pages = set(page_ids)
        for page_id in sorted(runtime_custom_pages - classified_pages):
            errors.append(f"unclassified custom Admin page: {page_id}")
        for page_id in sorted(classified_pages - runtime_custom_pages):
            errors.append(f"stale custom Admin page classification: {page_id}")

    auth_interstitials = contract.get("admin_auth_interstitials", [])
    interstitial_ids = [entry.get("id") for entry in auth_interstitials]
    for duplicate in sorted(_duplicates(interstitial_ids)):
        errors.append(f"Admin auth interstitial classified more than once: {duplicate}")
    for entry in auth_interstitials:
        location = f"admin_auth_interstitial {entry.get('id')!r}"
        validate_dimensions(entry, location)
        validate_admin_fit(entry, location)
        if not entry.get("reason"):
            errors.append(f"{location}: boundary exception requires a reason")
        for field in ("controller", "template", "test", "route_source"):
            evidence = entry.get(field, "")
            if not evidence or not (root / evidence).is_file():
                errors.append(f"{location}: missing {field} evidence {evidence!r}")
        route_source = root / entry.get("route_source", "")
        route = entry.get("route", "")
        if route_source.is_file() and (not route or route not in route_source.read_text(encoding="utf-8")):
            errors.append(f"{location}: route source lacks marker {route!r}")

    if surface_registry is None:
        surface_registry = load_json(root / "surfaces/registry.json")
    surfaces = surface_registry.get("surfaces", {})
    workflows = contract.get("workflows", [])
    workflow_ids = [workflow.get("id") for workflow in workflows]
    for duplicate in sorted(_duplicates(workflow_ids)):
        errors.append(f"duplicate workflow id: {duplicate}")

    locks: list[str] = []
    for workflow in workflows:
        location = f"workflow {workflow.get('id')!r}"
        validate_dimensions(workflow, location)
        frequency = workflow.get("frequency")
        admin_only = workflow.get("admin_only") is True
        if frequency in routine_frequencies and admin_only:
            errors.append(f"{location}: routine work cannot be admin_only")
        if frequency in routine_frequencies:
            surface_id = workflow.get("surface")
            surface = surfaces.get(surface_id)
            if not surface or surface.get("kind") != "operator":
                errors.append(f"{location}: surface {surface_id!r} is not a registered operator surface")
            for field in ("pages", "api", "tests"):
                if not workflow.get(field):
                    errors.append(f"{location}: routine workflow requires {field} evidence")
        elif admin_only and not workflow.get("reason"):
            errors.append(f"{location}: admin_only requires a reason")
        if admin_only:
            validate_admin_fit(workflow, location)

        for page in workflow.get("pages", []):
            if not (root / page).is_file():
                errors.append(f"{location}: missing page evidence {page}")
        for test in workflow.get("tests", []):
            test_path = root / test
            is_test_path = "tests" in test_path.parts and (
                "test" in test_path.name.lower() or ".spec." in test_path.name.lower()
            )
            if not test_path.is_file() or not is_test_path:
                errors.append(f"{location}: invalid test evidence {test}")
        for api in workflow.get("api", []):
            api_path = root / api.get("path", "")
            marker = api.get("contains", "")
            if not api_path.is_file():
                errors.append(f"{location}: missing API evidence {api.get('path')!r}")
            elif not marker or marker not in api_path.read_text(encoding="utf-8"):
                errors.append(f"{location}: API evidence lacks marker {marker!r}")
        locks.extend(workflow.get("locks", []))

    # Cruzamento Admin × workflow (laudo A11-1). A frequência de um grupo Admin
    # mede o uso do Admin; a rotina do mesmo model mora no workflow que o declara.
    # Sem o cruzamento, as duas classificações podiam dizer coisas opostas e
    # nenhuma das duas era conferida contra a outra.
    group_of_model = {
        model: group for group in groups for model in group.get("models") or []
    }
    claimed: list[str] = []
    routine_claimed: set[str] = set()
    for workflow in workflows:
        location = f"workflow {workflow.get('id')!r}"
        admin_models = workflow.get("admin_models")
        if not isinstance(admin_models, list):
            errors.append(f"{location}: admin_models must be a list (empty when no ModelAdmin backs it)")
            continue
        claimed.extend(admin_models)
        is_routine = workflow.get("frequency") in routine_frequencies
        for model in admin_models:
            group = group_of_model.get(model)
            if group is None:
                errors.append(f"{location}: admin_models names an unclassified ModelAdmin {model!r}")
                continue
            if is_routine:
                routine_claimed.add(model)
                if group.get("frequency") in routine_frequencies:
                    errors.append(
                        f"{location}: {model} is routine on the surface and also routine in "
                        f"Admin group {group.get('id')!r}; the Admin cannot be a second place for the routine"
                    )
    for duplicate in sorted(_duplicates(claimed)):
        errors.append(f"ModelAdmin claimed by more than one workflow: {duplicate}")
    for group in groups:
        if group.get("frequency") not in routine_frequencies:
            continue
        for model in group.get("models") or []:
            if model not in routine_claimed:
                errors.append(
                    f"admin_model_group {group.get('id')!r}: {model} is routine in the Admin "
                    "without a routine operator workflow that declares it"
                )

    for duplicate in sorted(_duplicates(locks)):
        errors.append(f"boundary lock assigned more than once: {duplicate}")
    required_locks = contract.get("required_locks", [])
    for duplicate in sorted(_duplicates(required_locks)):
        errors.append(f"required lock declared more than once: {duplicate}")
    missing_locks = set(required_locks) - set(locks)
    stale_locks = set(locks) - set(required_locks)
    for lock in sorted(missing_locks):
        errors.append(f"required boundary lock is not assigned: {lock}")
    for lock in sorted(stale_locks):
        errors.append(f"workflow lock is not declared in required_locks: {lock}")
    return errors


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    errors = validate_contract(
        contract,
        runtime_models=registered_model_admins(),
        runtime_custom_pages=registered_custom_admin_pages(),
    )
    if errors:
        for error in errors:
            print(f"[admin-surface-boundary] {error}", file=sys.stderr)
        return 1
    model_count = sum(len(group["models"]) for group in contract["admin_model_groups"])
    print(
        "[admin-surface-boundary] "
        f"{model_count} ModelAdmins, {len(contract['custom_admin_pages'])} custom pages and "
        f"{len(contract['workflows'])} workflows classified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
