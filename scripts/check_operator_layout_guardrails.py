#!/usr/bin/env python3
"""Bloqueia novas cópias de layouts e tokens estruturais canônicos."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS = ROOT / "docs/reference/operator-layout-exceptions.json"
APPS = ("hub", "pos", "kds", "orders", "production", "marketing", "purchase", "bi")
LOCAL_LAYOUT = re.compile(r"(?:Shell|Layout|Sidebar|Splitter|Dashboard)\.vue$", re.IGNORECASE)
TOKEN_DECLARATION = re.compile(r"--op-(?:rail|header|action-bar|pane|page|region|control|splitter|safe|layer)[\w-]*\s*:")


def main() -> int:
    entries = json.loads(EXCEPTIONS.read_text(encoding="utf-8")).get("exceptions") or []
    by_path = {entry.get("path"): entry for entry in entries}
    errors: list[str] = []
    layouts: set[str] = set()
    for app in APPS:
        root = ROOT / "surfaces" / f"{app}-nuxt" / "app"
        components = root / "components"
        if components.exists():
            layouts.update(
                path.relative_to(ROOT).as_posix()
                for path in components.rglob("*.vue")
                if LOCAL_LAYOUT.search(path.name)
            )
        for path in (*root.rglob("*.vue"), *root.rglob("*.css")):
            if TOKEN_DECLARATION.search(path.read_text(encoding="utf-8")):
                errors.append(f"token estrutural duplicado fora do operator-kit: {path.relative_to(ROOT)}")
    for path in sorted(layouts - set(by_path)):
        errors.append(f"layout local novo sem decisão canônica: {path}")
    for path in sorted(set(by_path) - layouts):
        errors.append(f"exceção de layout obsoleta: {path}")
    for path in sorted(layouts & set(by_path)):
        entry = by_path[path]
        if not all(entry.get(key) for key in ("reason", "owner", "test")):
            errors.append(f"{path}: exceção incompleta (reason, owner e test)")
        elif not list(ROOT.glob(entry["test"])):
            errors.append(f"{path}: teste declarado não existe ({entry['test']})")
    for error in errors:
        print(f"[ERRO] {error}", file=sys.stderr)
    if not errors:
        print(f"operator layouts: OK ({len(layouts)} exceções legadas, zero fonte paralela nova)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
