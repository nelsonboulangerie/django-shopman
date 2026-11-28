#!/usr/bin/env python
"""Inventário de release e classe de risco de um diff (WP-RELEASE-01 R0).

Duas perguntas, nenhuma lista manual nova:

``inventory``
    Quais componentes deployáveis existem e que superfície mora em cada um.
    Sai de ``scripts/deploy_components.py`` (a tabela que decide o que construir)
    e de ``surfaces/operator-router/groups.json`` (a lista do launcher), e é
    confrontado com ``surfaces/registry.json`` (o campo ``service`` de cada
    superfície). Divergiu, sai com 1 e diz onde. O teste
    ``shopman/shop/tests/test_release_inventory.py`` roda a mesma conferência.

``risk --base <ref> --head <ref>``
    Quais componentes o diff publica e em que classe da matriz de risco
    (docs/reference/release-contract.md, §Classes de risco) cada arquivo cai, com o
    caminho mínimo da classe mais alta. Saída em Markdown, para colar no PR.

Uso:

    python scripts/release_inventory.py inventory [--format json|markdown]
    python scripts/release_inventory.py risk --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_JSON = REPO_ROOT / "surfaces" / "registry.json"


def _deploy_components():
    spec = importlib.util.spec_from_file_location(
        "release_inventory_deploy_components", REPO_ROOT / "scripts" / "deploy_components.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


DC = _deploy_components()

#: Os componentes do release set, na ordem do contrato. É o que o manifesto da
#: release e a sonda `release_identity` enumeram. Não é lista manual de
#: superfície: as superfícies de cada um saem de groups.json/registry.json.
RELEASE_COMPONENTS = ("web", "storefront-nuxt", "operator-floor", "operator-office")


def inventory(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Componente → superfícies (diretórios em surfaces/) que ele serve."""

    groups = DC.load_groups(root / "surfaces" / "operator-router" / "groups.json")
    result: dict[str, list[str]] = {"web": [], "storefront-nuxt": ["storefront-nuxt"]}
    for group, members in groups.items():
        result[group] = list(members)
    return result


def inventory_errors(root: Path = REPO_ROOT) -> list[str]:
    """Tudo em que registry, grupos e deploy discordam. Vazio = coerente."""

    errors: list[str] = []
    inv = inventory(root)
    if tuple(inv) != RELEASE_COMPONENTS:
        errors.append(f"componentes {tuple(inv)} != contrato {RELEASE_COMPONENTS}")

    groups = DC.load_groups(root / "surfaces" / "operator-router" / "groups.json")
    paths = DC.component_paths(groups)
    for component in RELEASE_COMPONENTS:
        if component not in paths:
            errors.append(f"{component}: sem tabela de caminhos em scripts/deploy_components.py")
    matrix = {row["name"]: row for row in DC.build_matrix(list(RELEASE_COMPONENTS), groups)}
    for component in RELEASE_COMPONENTS:
        if component not in matrix:
            errors.append(f"{component}: deploy_components.build_matrix não o constrói")

    registry = json.loads((root / "surfaces" / "registry.json").read_text(encoding="utf-8"))["surfaces"]
    served_by = {surface: component for component, surfaces in inv.items() for surface in surfaces}
    for app_id, entry in registry.items():
        surface = entry.get("dir")
        if entry.get("deployment") != "digitalocean":
            if surface in served_by:
                errors.append(f"{app_id}: fora da DigitalOcean no registry, mas o componente {served_by[surface]} o serve")
            continue
        service = entry.get("service")
        if surface not in served_by:
            errors.append(f"{app_id}: no registry com deployment=digitalocean, mas em nenhum componente")
        elif served_by[surface] != service:
            errors.append(f"{app_id}: registry diz service={service}, o deploy o põe em {served_by[surface]}")
    registered = {e.get("dir") for e in registry.values() if e.get("deployment") == "digitalocean"}
    for surface, component in served_by.items():
        if surface not in registered:
            errors.append(f"{surface}: servido por {component}, ausente do registry como digitalocean")
    return errors


# ── Classe de risco ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskClass:
    key: str
    label: str
    path: str
    rollback: str


#: Da mais alta para a mais baixa. A tabela de prosa é a do plano (§5) e a do
#: contrato; aqui mora só a regra de caminho.
RISK_CLASSES = (
    RiskClass("schema", "Schema (migração)", "ADR-015 expand/contract; staging com dado representativo; contract em release separada", "código anterior; restore se for contract"),
    RiskClass("config", "Config/secret/topologia", "diff do spec vivo + doctl apps propose + revisão humana", "spec vivo anterior preservado"),
    RiskClass("kit_router", "operator-kit/router", "todos os consumers + boot dos dois grupos", "digests dos dois grupos"),
    RiskClass("mutation", "Mutation/efeito externo", "idempotência + receipt/outbox + canário nominal", "kill switch + reconciliação"),
    RiskClass("dependency", "Dependência/runtime", "uma surface/grupo por vez, build e browser matrix", "digest anterior"),
    RiskClass("api", "Projection/API", "backend compatível primeiro, V2 depois", "V1 continua lendo contrato antigo"),
    RiskClass("ui", "UI local", "gates da surface, alpha, coorte", "flag V1/V2"),
    RiskClass("none", "Sem efeito em runtime", "gates normais", "-"),
)
CLASS_BY_KEY = {c.key: c for c in RISK_CLASSES}

_DEPENDENCY_NAMES = {"package.json", "package-lock.json", "constraints.txt", "pyproject.toml"}


def classify(path: str) -> str:
    parts = path.split("/")
    name = parts[-1]
    if "migrations" in parts[:-1] and name.endswith(".py") and name != "__init__.py":
        return "schema"
    if path.startswith((".do/", ".github/workflows/")):
        return "config"
    if path.startswith(("surfaces/operator-kit/", "surfaces/operator-router/")):
        return "kit_router"
    if any(seg in parts for seg in ("handlers", "adapters", "webhooks")) and path.endswith(".py"):
        return "mutation"
    if name in _DEPENDENCY_NAMES or name.startswith("Dockerfile"):
        return "dependency"
    if path.endswith(".py") and any(seg in parts for seg in ("api", "projections", "presentation", "intents")):
        return "api"
    if path.startswith("surfaces/") and "/tests/" not in path:
        return "ui"
    if path.startswith(("shopman/", "packages/", "config/")) and path.endswith(".py") and "/tests/" not in path:
        return "api"
    return "none"


def risk_report(changed: list[str], root: Path = REPO_ROOT) -> dict:
    groups = DC.load_groups(root / "surfaces" / "operator-router" / "groups.json")
    paths = DC.component_paths(groups)
    touched = [c for c in RELEASE_COMPONENTS if any(DC.touches(f, paths[c]) for f in changed)]
    by_class: dict[str, list[str]] = {}
    for path in changed:
        by_class.setdefault(classify(path), []).append(path)
    ordered = [c.key for c in RISK_CLASSES if c.key in by_class]
    return {
        "components": touched,
        "highest": ordered[0] if ordered else "none",
        "classes": {key: by_class[key] for key in ordered},
    }


def render_risk_markdown(report: dict) -> str:
    highest = CLASS_BY_KEY[report["highest"]]
    lines = [
        "### Release: componentes e risco",
        "",
        f"**Componentes publicados:** {', '.join(f'`{c}`' for c in report['components']) or 'nenhum'}",
        f"**Classe mais alta:** {highest.label}",
        f"**Caminho mínimo:** {highest.path}",
        f"**Rollback primário:** {highest.rollback}",
        "",
        "| Classe | Arquivos |",
        "| --- | --- |",
    ]
    for key, files in report["classes"].items():
        sample = ", ".join(f"`{f}`" for f in files[:5]) + (f" e mais {len(files) - 5}" if len(files) > 5 else "")
        lines.append(f"| {CLASS_BY_KEY[key].label} | {sample} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--format", choices=("json", "markdown"), default="markdown")
    risk = sub.add_parser("risk")
    risk.add_argument("--base", required=True)
    risk.add_argument("--head", default="HEAD")
    risk.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    if args.command == "inventory":
        errors = inventory_errors()
        data = inventory()
        if args.format == "json":
            print(json.dumps({"components": data, "errors": errors}, indent=2, ensure_ascii=False))
        else:
            for component, surfaces in data.items():
                print(f"- `{component}`: {', '.join(surfaces) or '(Django, API e workers)'}")
            for error in errors:
                print(f"ERRO: {error}", file=sys.stderr)
        return 1 if errors else 0

    base = DC._git("merge-base", args.base, args.head, cwd=REPO_ROOT).stdout.strip() or args.base
    report = risk_report(DC.changed_files(base, args.head, REPO_ROOT))
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_risk_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
