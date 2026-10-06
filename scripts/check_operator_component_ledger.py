#!/usr/bin/env python3
"""Confere cobertura, evidências e não-divergência dos WP-UX-8/13.

O ledger nomeia cada tela/subtela das oito superfícies de operador. Durante a
migração, os números legados funcionam como teto: podem cair, nunca subir. Ao
fim do WP, os tetos de árvores Ui e imports diretos serão zero.

Uso:

    python scripts/check_operator_component_ledger.py
    python scripts/check_operator_component_ledger.py --json
    python scripts/check_operator_component_ledger.py --require-complete
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
CANONICAL_STRUCTURE = re.compile(
    r"<(?:U|NuxtU)(?:App|DashboardGroup|DashboardSidebar|DashboardPanel|DashboardNavbar|"
    r"DashboardToolbar|Sidebar|NavigationMenu|Page|PageHeader|PageBody|PageAside|Main|Container|Splitter)\b|"
    r"<Nuxt(?:App|DashboardGroup|DashboardSidebar|DashboardPanel|DashboardNavbar|DashboardToolbar|"
    r"Sidebar|NavigationMenu|PageHeader|PageBody|PageAside|Main|Container|Splitter)\b"
)


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


def route_for_source(source: str) -> str:
    if source == "app/app.vue":
        return "/"
    prefix = "app/pages/"
    if not source.startswith(prefix) or not source.endswith(".vue"):
        raise ValueError(f"fonte não é rota Nuxt: {source}")
    parts = source[len(prefix) : -4].split("/")
    route: list[str] = []
    for part in parts:
        if part == "index" or (part.startswith("(") and part.endswith(")")):
            continue
        catch_all = re.fullmatch(r"\[\.\.\.(.+)]", part)
        optional_catch_all = re.fullmatch(r"\[\[\.\.\.(.+)]]", part)
        dynamic = re.fullmatch(r"\[(.+)]", part)
        if optional_catch_all:
            route.append(f":{optional_catch_all.group(1)}(.*)*")
        elif catch_all:
            route.append(f":{catch_all.group(1)}(.*)")
        elif dynamic:
            route.append(f":{dynamic.group(1)}")
        else:
            route.append(part)
    return "/" + "/".join(route)


def base_route(route: str) -> str:
    return route.split("?", 1)[0].split("#", 1)[0] or "/"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(
    *,
    require_complete: bool = False,
    evidence_root: Path | None = None,
    selected_app: str | None = None,
) -> tuple[list[str], list[str], dict[str, object]]:
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
    audit = ledger.get("audit") or {}
    viewports = audit.get("viewports") or []
    viewport_ids = {viewport.get("id") for viewport in viewports}
    states = set(audit.get("states") or [])
    if len(viewport_ids) != len(viewports) or None in viewport_ids:
        errors.append("ledger: viewports ausentes ou repetidos")
    if not states:
        errors.append("ledger: estados de auditoria ausentes")
    for key in ("owner", "browser_lock", "runner", "evidence_root", "closure_gate"):
        if not audit.get(key):
            errors.append(f"ledger: audit.{key} ausente")
        elif key in {"browser_lock", "runner"} and not (ROOT / audit[key]).is_file():
            errors.append(f"ledger: audit.{key} aponta para arquivo inexistente {audit[key]}")
    rows = []
    surface_ids: set[str] = set()
    pending: list[str] = []
    for app_id, directory in sorted(registered.items()):
        if selected_app and app_id != selected_app:
            continue
        entry = by_id.get(app_id)
        if not entry:
            continue
        if entry.get("directory") != directory:
            errors.append(
                f"{app_id}: directory {entry.get('directory')!r}, esperado {directory!r}"
            )
        if not entry.get("owner"):
            errors.append(f"{app_id}: responsável ausente")
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
            if status == "pending":
                pending.append(surface_id)
                if require_complete:
                    errors.append(f"{surface_id}: ledger pending")
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
            exceptions = surface.get("exceptions") or []
            for index, exception in enumerate(exceptions):
                if not all(exception.get(key) for key in ("kind", "reason", "owner", "test")):
                    errors.append(f"{surface_id}: exceção {index + 1} incompleta (kind, reason, owner e test)")

            if status and status != "pending":
                declared_states = set(surface.get("states") or [])
                declared_viewports = set(surface.get("viewports") or [])
                evidence = surface.get("evidence") or []
                if not declared_states:
                    errors.append(f"{surface_id}: estados aplicáveis ausentes")
                if declared_states - states:
                    errors.append(f"{surface_id}: estados desconhecidos {sorted(declared_states - states)}")
                if not declared_viewports:
                    errors.append(f"{surface_id}: viewports aplicáveis ausentes")
                if declared_viewports - viewport_ids:
                    errors.append(f"{surface_id}: viewports desconhecidos {sorted(declared_viewports - viewport_ids)}")
                if not evidence:
                    errors.append(f"{surface_id}: captura/evidência ausente")
                visited_routes = {base_route(item.get("route", "")) for item in evidence if item.get("visited") is True}
                expected_routes = {base_route(route) for route in surface.get("routes") or []}
                if expected_routes - visited_routes:
                    errors.append(f"{surface_id}: tela não visitada {sorted(expected_routes - visited_routes)}")
                evidence_scenarios = {item.get("scenario") for item in evidence}
                missing_scenarios = set(surface.get("variants") or []) - evidence_scenarios
                if missing_scenarios:
                    errors.append(f"{surface_id}: cenários sem evidência {sorted(missing_scenarios)}")
                evidence_viewports = {item.get("viewport") for item in evidence}
                if declared_viewports - evidence_viewports:
                    errors.append(f"{surface_id}: viewports sem captura {sorted(declared_viewports - evidence_viewports)}")
                for item in evidence:
                    capture = item.get("capture")
                    if not capture:
                        errors.append(f"{surface_id}: evidência sem capture")
                    elif evidence_root and not (evidence_root / capture).is_file():
                        errors.append(f"{surface_id}: captura ausente no disco {capture}")
                    if item.get("state") not in states:
                        errors.append(f"{surface_id}: evidência com estado inválido {item.get('state')!r}")
                    if item.get("viewport") not in viewport_ids:
                        errors.append(f"{surface_id}: evidência com viewport inválido {item.get('viewport')!r}")
            for source in surface.get("source_files") or []:
                covered.add(source)
                if not (app_root / source).is_file():
                    errors.append(f"{surface_id}: source inexistente {source}")
                else:
                    expected_route = route_for_source(source)
                    declared_routes = {base_route(route) for route in surface.get("routes") or []}
                    if expected_route not in declared_routes:
                        errors.append(
                            f"{surface_id}: rota automática {expected_route!r} ausente; "
                            f"declaradas={sorted(declared_routes)}"
                        )

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
        direct_structures = [
            path
            for path in vue_and_ts(app_root / "app")
            if CANONICAL_STRUCTURE.search(path.read_text(encoding="utf-8"))
        ]
        if direct_structures:
            errors.append(
                f"{app_id}: layout Nuxt UI canônico usado fora do operator-kit: "
                + ", ".join(path.relative_to(ROOT).as_posix() for path in direct_structures)
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
        "pending": len(pending),
        "rows": rows,
    }
    return errors, notices, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--app")
    args = parser.parse_args()
    errors, notices, summary = check(
        require_complete=args.require_complete,
        evidence_root=args.evidence_root,
        selected_app=args.app,
    )
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "notices": notices, **summary}, indent=2))
    else:
        for notice in notices:
            print(f"[transição] {notice}")
        if summary["pending"]:
            print(
                f"[transição] {summary['pending']} tela(s) pending; "
                "o fechamento reprova com --require-complete"
            )
        for error in errors:
            print(f"[ERRO] {error}", file=sys.stderr)
        if not errors:
            print(
                "operator component ledger: OK "
                f"({summary['apps']} apps, {summary['surfaces']} telas, "
                f"{summary['variants']} variantes/subtelas, {summary['pending']} pending)"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
