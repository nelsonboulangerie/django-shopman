#!/usr/bin/env python3
"""Impede listeners globais e colisões de atalhos fora da infraestrutura canônica."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS = ROOT / "docs/reference/operator-global-shortcut-exceptions.json"
REGISTRY = ROOT / "surfaces/registry.json"
LISTENER = re.compile(
    r"(?:window|document)\.addEventListener\(\s*['\"]keydown['\"]|"
    r"useEventListener\([^;]{0,300}?['\"]keydown['\"]",
    re.DOTALL,
)
CANONICAL = {
    "surfaces/operator-kit/app/composables/useOperatorShortcutMap.ts",
}


def listeners() -> set[str]:
    found: set[str] = set()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    directories = [
        surface["dir"]
        for surface in registry["surfaces"].values()
        if surface["kind"] == "operator"
    ] + ["operator-kit"]
    for directory in directories:
        app = ROOT / "surfaces" / directory / "app"
        for suffix in ("*.vue", "*.ts", "*.js", "*.mjs"):
            for path in app.rglob(suffix):
                if LISTENER.search(path.read_text(encoding="utf-8")):
                    found.add(path.relative_to(ROOT).as_posix())
    return found - CANONICAL


def main() -> int:
    data = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    entries = data.get("exceptions") or []
    by_path = {entry.get("path"): entry for entry in entries}
    errors: list[str] = []
    if len(by_path) != len(entries):
        errors.append("exceções: path repetido")
    actual = listeners()
    for path in sorted(actual - set(by_path)):
        errors.append(f"listener global fora da infraestrutura: {path}")
    for path in sorted(set(by_path) - actual):
        errors.append(f"exceção obsoleta, remova do inventário: {path}")
    for path in sorted(actual & set(by_path)):
        entry = by_path[path]
        required = ("kind", "reason", "owner", "test")
        if not all(entry.get(key) for key in required):
            errors.append(f"{path}: exceção incompleta ({', '.join(required)})")
        if entry.get("kind") == "legacy-command" and not entry.get("decision_owner"):
            errors.append(f"{path}: comando legado sem decision_owner")
        test_pattern = entry.get("test")
        if test_pattern and not list(ROOT.glob(test_pattern)):
            errors.append(f"{path}: teste declarado não existe ({test_pattern})")
    for error in errors:
        print(f"[ERRO] {error}", file=sys.stderr)
    if not errors:
        kinds: dict[str, int] = {}
        for entry in entries:
            kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
        print(f"operator shortcuts: OK ({len(actual)} exceções inventariadas: {kinds})")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
