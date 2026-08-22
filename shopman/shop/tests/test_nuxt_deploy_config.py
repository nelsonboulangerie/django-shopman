"""Nuxt deploy config guardrails for the subdomain topology."""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
SURFACES = (
    "storefront-nuxt",
    "hub-nuxt",
    "pos-nuxt",
    "kds-nuxt",
    "orders-nuxt",
    "production-nuxt",
    "marketing-nuxt",
    "bi-nuxt",
)
NUXT_RUNTIMES = (*SURFACES, "operator-kit")


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")[:3]
    return int(major), int(minor), int(patch)


def test_operator_surfaces_default_to_subdomain_root_base_url():
    for surface in ("pos-nuxt", "kds-nuxt", "hub-nuxt"):
        source = (ROOT / "surfaces" / surface / "nuxt.config.ts").read_text()
        assert 'baseURL: process.env.NUXT_APP_BASE_URL || "/"' in source


def test_nuxt_lockfiles_use_security_patched_runtime():
    for surface in NUXT_RUNTIMES:
        lock = json.loads((ROOT / "surfaces" / surface / "package-lock.json").read_text())
        version = lock["packages"]["node_modules/nuxt"]["version"]
        assert _version_tuple(version) >= (4, 5, 1), f"{surface} pins vulnerable nuxt {version}"


def test_make_surfaces_includes_all_nuxt_apps():
    source = (ROOT / "Makefile").read_text()
    line = next(line for line in source.splitlines() if line.startswith("SURFACES :="))
    for surface in SURFACES:
        assert surface in line
