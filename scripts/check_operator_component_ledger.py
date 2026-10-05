#!/usr/bin/env python3
"""Confere cobertura e não-divergência do WP-UX-8.

O ledger nomeia cada tela/subtela das oito superfícies de operador. Durante a
migração, os números legados funcionam como teto: podem cair, nunca subir. Ao
fim do WP, os tetos de árvores Ui e imports diretos serão zero.

Uso:

    python scripts/check_operator_component_ledger.py
    python scripts/check_operator_component_ledger.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs/reference/operator-component-ledger.json"
REGISTRY = ROOT / "surfaces/registry.json"
VALID_STATUSES = {"pending", "audited", "migrated", "retained-with-reason"}
MANUAL_OVERLAY = re.compile(
    r"<(?:div|section|aside|dialog)[^>]+\bclass=[\"'][^\"']*\bfixed\s+inset-0\b",
    re.DOTALL,
)
NATIVE_CONTROL = re.compile(r"<(?:button|select|textarea)(?:\s|>)")
REKA_IMPORT = re.compile(r"(?:from\s+|import\s*\()\s*[\"']reka-ui[\"']")
NUXT_UI_IMPORT = re.compile(r"(?:from\s+|import\s*\()\s*[\"']@nuxt/ui[\"']")


@dataclass(frozen=True)
class Counts:
    local_ui_files: int
    direct_reka_import_files: int
    manual_overlay_files: int
    native_control_occurrences: int


def vue_and_ts(root: Path) -> list[Path]:
    return sorted((*root.rglob("*.vue"), *root.rglob("*.ts")))


def count_app(app_root: Path) -> Counts:
    app = app_root / "app"
    component_root = app / "components"
    files = vue_and_ts(app)
    local_ui = [
        path
        for path in component_root.rglob("*.vue")
        if "Ui" in path.relative_to(component_root).parts
    ] if component_root.exists() else []
    reka = [
        path
        for path in files
        if REKA_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    manual = []
    native = 0
    for path in app.rglob("*.vue"):
        text = path.read_text(encoding="utf-8")
        if "components/Ui/" not in path.as_posix() and MANUAL_OVERLAY.search(text):
            manual.append(path)
        native += len(NATIVE_CONTROL.findall(text))
    return Counts(len(local_ui), len(reka), len(manual), native)


def page_sources(app_root: Path) -> set[str]:
    pages = app_root / "app/pages"
    if pages.exists():
        return {
            path.relative_to(app_root).as_posix()
            for path in pages.rglob("*.vue")
        }
    app_vue = app_root / "app/app.vue"
    return {"app/app.vue"} if app_vue.exists() else set()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check() -> tuple[list[str], list[str], dict[str, object]]:
    errors: list[str] = []
    notices: list[str] = []
    ledger = load_json(LEDGER)
    registry = load_json(REGISTRY)
    registered = {
        key: value["dir"]
        for key, value in registry["surfaces"].items()
        if value["kind"] == "operator"
    }
    apps = ledger.get("apps") or []
    by_id = {app.get("id"): app for app in apps}
    if len(by_id) != len(apps):
        errors.append("ledger: ids de app repetidos")
    if set(by_id) != set(registered):
        errors.append(
            "ledger: apps divergentes do registry: "
            f"esperado={sorted(registered)} atual={sorted(by_id)}"
        )

    allowed_families = set(ledger.get("families") or [])
    rows = []
    surface_ids: set[str] = set()
    for app_id, directory in sorted(registered.items()):
        entry = by_id.get(app_id)
        if not entry:
            continue
        if entry.get("directory") != directory:
            errors.append(
                f"{app_id}: directory {entry.get('directory')!r}, esperado {directory!r}"
            )
        app_root = ROOT / "surfaces" / directory
        covered: set[str] = set()
        for surface in entry.get("surfaces") or []:
            surface_id = f"{app_id}:{surface.get('id')}"
            if surface_id in surface_ids:
                errors.append(f"{surface_id}: id repetido")
            surface_ids.add(surface_id)
            status = surface.get("status")
            if status not in VALID_STATUSES:
                errors.append(f"{surface_id}: status inválido {status!r}")
            families = set(surface.get("families") or [])
            if not families:
                errors.append(f"{surface_id}: sem famílias")
            unknown = families - allowed_families
            if unknown:
                errors.append(f"{surface_id}: famílias desconhecidas {sorted(unknown)}")
            if not surface.get("variants"):
                errors.append(f"{surface_id}: sem variantes/subtelas")
            if status == "retained-with-reason" and not all(
                surface.get(key) for key in ("reason", "owner", "tests")
            ):
                errors.append(
                    f"{surface_id}: exceção sem reason, owner e tests"
                )
            for source in surface.get("source_files") or []:
                covered.add(source)
                if not (app_root / source).is_file():
                    errors.append(f"{surface_id}: source inexistente {source}")

        expected_sources = page_sources(app_root)
        missing = expected_sources - covered
        extra = covered - expected_sources
        if missing:
            errors.append(f"{app_id}: telas sem ledger {sorted(missing)}")
        if extra:
            errors.append(f"{app_id}: sources fora de app/pages ou app.vue {sorted(extra)}")

        actual = count_app(app_root)
        baseline = entry.get("baseline") or {}
        for field in Counts.__dataclass_fields__:
            current = getattr(actual, field)
            ceiling = baseline.get(field)
            if not isinstance(ceiling, int):
                errors.append(f"{app_id}: baseline {field} ausente")
            elif current > ceiling:
                errors.append(
                    f"{app_id}: {field} subiu de {ceiling} para {current}"
                )
            elif current:
                notices.append(
                    f"{app_id}: {field}={current} (teto transitório {ceiling})"
                )

        direct_nuxt_ui = [
            path
            for path in vue_and_ts(app_root / "app")
            if NUXT_UI_IMPORT.search(path.read_text(encoding="utf-8"))
        ]
        if direct_nuxt_ui:
            errors.append(
                f"{app_id}: import direto de @nuxt/ui fora do operator-kit: "
                + ", ".join(path.relative_to(ROOT).as_posix() for path in direct_nuxt_ui)
            )
        rows.append(
            {
                "app": app_id,
                "surfaces": len(entry.get("surfaces") or []),
                "variants": sum(
                    len(surface.get("variants") or [])
                    for surface in entry.get("surfaces") or []
                ),
                "counts": actual.__dict__,
            }
        )

    summary = {
        "apps": len(rows),
        "surfaces": sum(row["surfaces"] for row in rows),
        "variants": sum(row["variants"] for row in rows),
        "rows": rows,
    }
    return errors, notices, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors, notices, summary = check()
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "notices": notices, **summary}, indent=2))
    else:
        for notice in notices:
            print(f"[transição] {notice}")
        for error in errors:
            print(f"[ERRO] {error}", file=sys.stderr)
        if not errors:
            print(
                "operator component ledger: OK "
                f"({summary['apps']} apps, {summary['surfaces']} telas, "
                f"{summary['variants']} variantes/subtelas)"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
