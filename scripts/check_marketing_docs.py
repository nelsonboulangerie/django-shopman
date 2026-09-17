#!/usr/bin/env python
"""Fail when Marketing docs or deploy probes drift from the current routes."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/reference/marketing-surface-contract.md"
README = ROOT / "surfaces/marketing-nuxt/README.md"
PAGES = ROOT / "surfaces/marketing-nuxt/app/pages"
URLS = ROOT / "shopman/backstage/api/urls.py"
DEPLOY_SPECS = (
    ROOT / ".do/app.alpha-subdomains.yaml",
    ROOT / ".do/app.subdomains.yaml",
)


def _marked_routes(text: str, marker: str) -> set[str]:
    pattern = re.compile(
        rf"<!-- {re.escape(marker)}:start -->(.*?)<!-- {re.escape(marker)}:end -->",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"bloco {marker!r} ausente")
    return set(re.findall(r"^- `([^`]+)`$", match.group(1), re.MULTILINE))


def _page_route(path: Path) -> str:
    relative = path.relative_to(PAGES).with_suffix("")
    parts: list[str] = []
    for part in relative.parts:
        if part == "index" and not parts:
            continue
        catch_all = re.fullmatch(r"\[\.\.\.(.+)]", part)
        dynamic = re.fullmatch(r"\[(.+)]", part)
        if catch_all:
            parts.append(f"*{catch_all.group(1)}")
        elif dynamic:
            parts.append(f":{dynamic.group(1)}")
        elif part != "index":
            parts.append(part)
    return "/" + "/".join(parts)


def _django_routes() -> set[str]:
    tree = ast.parse(URLS.read_text(encoding="utf-8"))
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "path"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith("marketing/")
        ):
            continue
        route = node.args[0].value

        def replace_parameter(match: re.Match[str]) -> str:
            name = match.group(1)
            return ":id" if name == "pk" else f":{name}"

        route = re.sub(r"<(?:[^:>]+:)?([^>]+)>", replace_parameter, route)
        routes.add(f"/api/v1/backstage/{route}")
    return routes


def _assert_equal(label: str, documented: set[str], actual: set[str]) -> list[str]:
    if documented == actual:
        return []
    messages = [f"{label} divergiu do HEAD."]
    missing = sorted(actual - documented)
    stale = sorted(documented - actual)
    if missing:
        messages.append("  ausentes na documentação: " + ", ".join(missing))
    if stale:
        messages.append("  sem rota correspondente: " + ", ".join(stale))
    return messages


def _marketing_service_name(payload: dict) -> str | None:
    """O service que o ingress do host `mkt.` alcança.

    Desde a ADR-030 o Marketing mora no service de grupo `operator-office`, e o
    nome do service deixou de ser o nome do app. Quem responde pelo `mkt.` é
    quem o ingress diz — perguntar pelo nome fixo faria o gate conferir um
    service que não existe mais, ou um que não serve o Marketing.
    """
    for rule in (payload.get("ingress") or {}).get("rules") or []:
        authority = ((rule.get("match") or {}).get("authority") or {}).get("exact") or ""
        if authority.startswith("mkt."):
            return (rule.get("component") or {}).get("name")
    return None


def _deploy_errors(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = payload.get("services", []) if isinstance(payload, dict) else []
    name = _marketing_service_name(payload) if isinstance(payload, dict) else None
    if name is None:
        return [f"{path.relative_to(ROOT)}: nenhuma regra de ingress para o host mkt."]
    marketing = next(
        (service for service in services if service.get("name") == name),
        None,
    )
    if marketing is None:
        return [f"{path.relative_to(ROOT)}: serviço {name} (host mkt.) ausente"]
    expected = {
        # O health check da plataforma NÃO consulta o Django: `/health/ready` é
        # do smoke e do diagnóstico (WP-PERFORMANCE P1).
        "health_check": "/health/live",
        "liveness_health_check": "/health/live",
    }
    errors: list[str] = []
    for key, route in expected.items():
        current = (marketing.get(key) or {}).get("http_path")
        if current != route:
            errors.append(
                f"{path.relative_to(ROOT)}: {key}.http_path={current!r}; esperado {route!r}"
            )
    return errors


def main() -> int:
    errors: list[str] = []
    contract = CONTRACT.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    for label, text in (("contrato", contract), ("README", readme)):
        if "**Última verificação:**" not in text or "**Verificado contra:**" not in text:
            errors.append(f"{label}: metadados de verificação ausentes")

    pages = {_page_route(path) for path in PAGES.rglob("*.vue")}
    errors.extend(
        _assert_equal(
            "rotas Nuxt no contrato",
            _marked_routes(contract, "marketing-ui-routes"),
            pages,
        )
    )
    errors.extend(
        _assert_equal(
            "rotas Nuxt no README",
            _marked_routes(readme, "marketing-ui-routes"),
            pages,
        )
    )
    errors.extend(
        _assert_equal(
            "rotas Django no contrato",
            _marked_routes(contract, "marketing-api-routes"),
            _django_routes(),
        )
    )
    for spec in DEPLOY_SPECS:
        errors.extend(_deploy_errors(spec))

    if errors:
        print("Marketing documentation drift detected:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"Marketing docs match HEAD: {len(pages)} Nuxt routes, "
        f"{len(_django_routes())} Django routes, 2 deploy specs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
