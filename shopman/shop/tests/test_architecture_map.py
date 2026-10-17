"""Executable inventory for the canonical architecture map."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_architecture_map_matches_kernel_directories():
    architecture = _load(REPO_ROOT / "docs" / "architecture-map.json")
    declared = set(architecture["kernel"]["domain_packages"])
    declared.update(architecture["kernel"]["shared_capabilities"])
    physical = {path.name for path in (REPO_ROOT / "packages").iterdir() if path.is_dir()}

    assert declared == physical
    assert len(architecture["kernel"]["domain_packages"]) == 10
    assert len(physical) == 13


def test_architecture_map_matches_surface_registry_and_support_directories():
    architecture = _load(REPO_ROOT / "docs" / "architecture-map.json")
    registry = _load(REPO_ROOT / architecture["surfaces"]["registry"])
    registry_surfaces = registry["surfaces"]
    expected_by_role = {
        "product": {
            app
            for app, surface in registry_surfaces.items()
            if surface["kind"] in {"customer", "operator"} and surface.get("deployment") != "external"
        },
        "internal": {app for app, surface in registry_surfaces.items() if surface["kind"] == "internal"},
        "external": {app for app, surface in registry_surfaces.items() if surface.get("deployment") == "external"},
    }

    for role, expected in expected_by_role.items():
        assert set(architecture["surfaces"][role]) == expected
    assert len(architecture["surfaces"]["product"]) == 9
    assert registry_surfaces["kitchensink"]["kind"] == "internal"
    assert registry_surfaces["kitchensink"]["uses_operator_kit"] is True
    assert registry["surfaces"]["kitchensink"]["deployment"] == "preview"
    assert registry["surfaces"]["status"]["deployment"] == "external"
    for support in (
        *architecture["surfaces"]["shared_layer"],
        *architecture["surfaces"]["deploy_infrastructure"],
    ):
        assert (REPO_ROOT / "surfaces" / support).is_dir()


def test_architecture_map_declares_delivery_split_and_transversal_instance():
    architecture = _load(REPO_ROOT / "docs" / "architecture-map.json")

    assert architecture["layers"] == ["kernel", "orchestrator", "query_read_side", "surfaces"]
    assert architecture["transversal"] == "instance"
    assert architecture["delivery_boundary"]["query"] == ["GET", "SSE"]
    assert set(architecture["delivery_boundary"]["command_ingress"]) == {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "intent",
    }
