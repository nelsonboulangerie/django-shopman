#!/usr/bin/env python3
"""Bloqueia novas cópias de layouts e tokens estruturais canônicos."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS = ROOT / "docs/reference/operator-layout-exceptions.json"
TOKEN_EXCEPTIONS = ROOT / "docs/reference/operator-token-exceptions.json"
REGISTRY = ROOT / "surfaces/registry.json"
LOCAL_LAYOUT = re.compile(r"(?:Shell|Layout|Sidebar|Splitter|Dashboard)\.vue$", re.IGNORECASE)
TOKEN_DECLARATION = re.compile(r"--op-(?:rail|header|action-bar|pane|page|region|control|splitter|safe|layer)[\w-]*\s*:")
CUSTOM_PROPERTY = re.compile(r"(?P<name>--[a-z][a-z0-9-]*)\s*:")


def operator_directories() -> list[str]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [
        surface["dir"]
        for surface in registry["surfaces"].values()
        if surface["kind"] == "operator"
    ]


def validate_exception(entry: dict, path: str, errors: list[str]) -> None:
    required = (
        "app", "surface", "use_case", "canonical_limitation",
        "rejected_alternatives", "justification", "owner", "test",
    )
    if not all(entry.get(key) for key in required):
        errors.append(f"{path}: exceção incompleta ({', '.join(required)})")
    if not isinstance(entry.get("rejected_alternatives"), list) or not entry.get("rejected_alternatives"):
        errors.append(f"{path}: rejected_alternatives precisa ser lista não vazia")
    test = entry.get("test")
    if test and not list(ROOT.glob(test)):
        errors.append(f"{path}: teste declarado não existe ({test})")


def main() -> int:
    entries = json.loads(EXCEPTIONS.read_text(encoding="utf-8")).get("exceptions") or []
    by_path = {entry.get("path"): entry for entry in entries}
    token_entries = json.loads(TOKEN_EXCEPTIONS.read_text(encoding="utf-8")).get("exceptions") or []
    tokens_by_path = {entry.get("path"): entry for entry in token_entries}
    errors: list[str] = []
    layouts: set[str] = set()
    custom_properties: dict[str, set[str]] = {}
    for directory in operator_directories():
        root = ROOT / "surfaces" / directory / "app"
        components = root / "components"
        if components.exists():
            layouts.update(
                path.relative_to(ROOT).as_posix()
                for path in components.rglob("*.vue")
                if LOCAL_LAYOUT.search(path.name)
            )
        for path in (*root.rglob("*.vue"), *root.rglob("*.css")):
            source = path.read_text(encoding="utf-8")
            if TOKEN_DECLARATION.search(source):
                errors.append(f"token estrutural duplicado fora do operator-kit: {path.relative_to(ROOT)}")
            names = set(CUSTOM_PROPERTY.findall(source))
            if names:
                custom_properties[path.relative_to(ROOT).as_posix()] = names
    for path in sorted(layouts - set(by_path)):
        errors.append(f"layout local novo sem decisão canônica: {path}")
    for path in sorted(set(by_path) - layouts):
        errors.append(f"exceção de layout obsoleta: {path}")
    for path in sorted(layouts & set(by_path)):
        entry = by_path[path]
        validate_exception(entry, path, errors)
    for path in sorted(set(custom_properties) - set(tokens_by_path)):
        errors.append(f"tokens locais sem exceção funcional: {path} ({sorted(custom_properties[path])})")
    for path in sorted(set(tokens_by_path) - set(custom_properties)):
        errors.append(f"exceção de token obsoleta: {path}")
    for path in sorted(set(custom_properties) & set(tokens_by_path)):
        entry = tokens_by_path[path]
        validate_exception(entry, path, errors)
        declared = set(entry.get("tokens") or [])
        if declared != custom_properties[path]:
            errors.append(
                f"{path}: tokens divergentes; esperado={sorted(declared)} atual={sorted(custom_properties[path])}"
            )
    for error in errors:
        print(f"[ERRO] {error}", file=sys.stderr)
    if not errors:
        print(
            f"operator layouts/tokens: OK ({len(layouts)} layouts legados, "
            f"{len(custom_properties)} exceções funcionais de token)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
