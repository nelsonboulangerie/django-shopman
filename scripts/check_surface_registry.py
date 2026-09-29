#!/usr/bin/env python
"""Todo lugar que enumera superfícies concorda com `surfaces/registry.json`?

## Por que este guard existe

Uma superfície Nuxt nova precisa entrar em mais de dez lugares do repositório, e
faltar em um não acusa nada. O `purchase-nuxt` nasceu fora do Dependabot e ficou
16 pacotes atrás dos irmãos antes que alguém percebesse; o Marketing e o B.I.
ficaram fora das origens de dev do CSRF até 24/09/2026. Nenhum dos dois quebrou
teste: faltar é silencioso por natureza.

O `surfaces/registry.json` é a tabela única (id, diretório, tipo, porta, serviço,
subdomínio, env da URL, tile do Shopman Apps). Este script confere cada lugar
inventariado contra ela e, quando algo diverge, diz QUAL ARQUIVO e O QUE falta.
O inventário que originou a lista está no PR #1111.

## O que fica de fora, de propósito

- **O QA de navegador do Omotenashi** (`omotenashi-gate.yml`) roda um recorte de
  cinco apps por escolha, não por esquecimento.
- **O hostname.** O registro anota o subdomínio que existe; o guard só confere que
  os dois specs de `.do/` dizem o mesmo. Escolher hostname é DNS e é do dono.

## Uso

    python scripts/check_surface_registry.py           # falha se houver divergência
    python scripts/check_surface_registry.py --json    # saída para máquina

Precisa de PyYAML (specs da DigitalOcean e workflows são YAML).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = Path("surfaces/registry.json")
KINDS = {"customer", "operator"}
FIELDS = {"dir", "kind", "dev_port", "service", "subdomain", "base_url_env", "hub_tile"}
OPTIONAL_FIELDS = {"ready_path"}
DEPLOY_SPECS = (Path(".do/app.subdomains.yaml"), Path(".do/app.alpha-subdomains.yaml"))


@dataclass(frozen=True)
class Surface:
    id: str
    dir: str
    kind: str
    dev_port: int
    service: str
    subdomain: str | None
    base_url_env: str | None
    hub_tile: str | None
    ready_path: str | None = None

    @property
    def is_operator(self) -> bool:
        return self.kind == "operator"


class Registry:
    def __init__(self, root: Path):
        self.root = root
        raw = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
        self.raw = raw
        self.groups: dict[str, str] = raw.get("operator_groups") or {}
        # Campo a mais ou a menos não derruba a leitura: quem acusa é `check_registry_shape`.
        self.surfaces = [
            Surface(id=key, **{f: value.get(f) for f in FIELDS | OPTIONAL_FIELDS})
            for key, value in (raw.get("surfaces") or {}).items()
        ]

    @property
    def operators(self) -> list[Surface]:
        return [s for s in self.surfaces if s.is_operator]

    def read(self, path: Path | str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def yaml(self, path: Path | str):
        return yaml.safe_load(self.read(path))


def _diff(where: str, what: str, expected: set, actual: set) -> list[str]:
    errors = []
    for item in sorted(expected - actual, key=str):
        errors.append(f"{where}: falta {what} {item}")
    for item in sorted(actual - expected, key=str):
        errors.append(f"{where}: {what} {item} não está em {REGISTRY}")
    return errors


# ── o próprio registro ──────────────────────────────────────────────────────


def check_registry_shape(reg: Registry) -> list[str]:
    where = str(REGISTRY)
    errors = []
    for key, value in (reg.raw.get("surfaces") or {}).items():
        missing = FIELDS - set(value)
        extra = set(value) - FIELDS - OPTIONAL_FIELDS
        if missing:
            errors.append(f"{where}: {key} sem {sorted(missing)}")
        if extra:
            errors.append(f"{where}: {key} com campo desconhecido {sorted(extra)}")
    for s in reg.surfaces:
        if s.kind not in KINDS:
            errors.append(f"{where}: {s.id} com kind {s.kind!r} (use {sorted(KINDS)})")
        if s.dir != f"{s.id}-nuxt":
            errors.append(f"{where}: {s.id} mora em {s.dir}; o diretório é sempre <id>-nuxt")
        if s.is_operator and s.service not in reg.groups:
            errors.append(f"{where}: {s.id} é de operador e o serviço {s.service!r} não é um grupo")
        if s.is_operator and not s.subdomain:
            errors.append(f"{where}: {s.id} é de operador e não tem subdomínio")
    for field in ("dev_port", "subdomain", "base_url_env", "hub_tile"):
        values = [getattr(s, field) for s in reg.surfaces if getattr(s, field) is not None]
        for value in sorted({v for v in values if values.count(v) > 1}, key=str):
            errors.append(f"{where}: {field} {value!r} repetido")
    return errors


def check_directories(reg: Registry) -> list[str]:
    on_disk = {p.name for p in (reg.root / "surfaces").iterdir() if p.is_dir() and p.name.endswith("-nuxt")}
    return _diff("surfaces/", "o diretório", {s.dir for s in reg.surfaces}, on_disk)


# ── cadência, teste e comandos ──────────────────────────────────────────────


def check_dependabot(reg: Registry) -> list[str]:
    where = ".github/dependabot.yml"
    dirs: set[str] = set()
    for update in reg.yaml(where).get("updates") or []:
        if update.get("package-ecosystem") != "npm":
            continue
        for d in update.get("directories") or [update.get("directory")]:
            if d and d.startswith("/surfaces/"):
                dirs.add(d.removeprefix("/surfaces/"))
    expected = {s.dir for s in reg.surfaces} | {"operator-kit"}
    actual = {d for d in dirs if d.endswith("-nuxt") or d == "operator-kit"}
    return _diff(where, "o diretório npm", expected, actual)


def check_surfaces_gate(reg: Registry) -> list[str]:
    where = ".github/workflows/surfaces-gate.yml"
    jobs = reg.yaml(where)["jobs"]
    errors = []
    quality = set(jobs["app-quality"]["strategy"]["matrix"]["app"])
    errors += _diff(f"{where} (app-quality)", "o app", {s.dir for s in reg.surfaces} | {"operator-kit"}, quality)
    pwa_matrix = jobs["pwa-quality"]["strategy"]["matrix"]["include"]
    pwa = {(entry["app"], entry["surface"]) for entry in pwa_matrix}
    errors += _diff(f"{where} (pwa-quality)", "a entrada", {(s.id, s.dir) for s in reg.surfaces}, pwa)
    return errors


def check_makefile(reg: Registry) -> list[str]:
    line = next((ln for ln in reg.read("Makefile").splitlines() if ln.startswith("SURFACES :=")), "")
    return _diff("Makefile (SURFACES)", "o app", {s.dir for s in reg.surfaces}, set(line.split(":=", 1)[-1].split()))


def check_dev_ports(reg: Registry) -> list[str]:
    errors = []
    for s in reg.surfaces:
        where = f"surfaces/{s.dir}/package.json"
        path = reg.root / where
        if not path.is_file():
            continue  # check_directories já acusa
        dev = json.loads(path.read_text(encoding="utf-8")).get("scripts", {}).get("dev", "")
        match = re.search(r"--port\s+(\d+)", dev)
        if not match or int(match.group(1)) != s.dev_port:
            errors.append(f"{where}: `npm run dev` deveria usar --port {s.dev_port} (tem {dev!r})")
    return errors


def check_layer(reg: Registry) -> list[str]:
    errors = []
    for s in reg.surfaces:
        where = f"surfaces/{s.dir}/nuxt.config.ts"
        path = reg.root / where
        if not path.is_file():
            continue
        extends = '"../operator-kit"' in path.read_text(encoding="utf-8")
        if s.is_operator and not extends:
            errors.append(f"{where}: app de operador que não estende ../operator-kit")
        if not s.is_operator and extends:
            errors.append(f"{where}: superfície de cliente estendendo ../operator-kit")
    return errors


# ── deploy ──────────────────────────────────────────────────────────────────


def check_operator_groups(reg: Registry) -> list[str]:
    where = "surfaces/operator-router/groups.json"
    groups = json.loads(reg.read(where))
    errors = _diff(where, "o grupo", set(reg.groups), set(groups))
    for name, group in groups.items():
        if name in reg.groups and group.get("description") != reg.groups[name]:
            errors.append(f"{where}: descrição de {name} diverge de {REGISTRY}")
        members = {(app["id"], app["surface"], app.get("readyPath")) for app in group.get("apps") or []}
        expected = {(s.id, s.dir, s.ready_path) for s in reg.operators if s.service == name}
        errors += _diff(f"{where} ({name})", "o app", expected, members)
    return errors


def check_operator_dockerfile(reg: Registry) -> list[str]:
    where = "surfaces/Dockerfile.operator-group"
    source = reg.read(where)
    errors = []
    for s in reg.operators:
        if not re.search(rf"^FROM kit AS {re.escape(s.id)}$", source, re.M):
            errors.append(f"{where}: falta o estágio `FROM kit AS {s.id}`")
        copy = f"COPY --from={s.id} /repo/surfaces/{s.dir}/.output ./apps/{s.dir}/.output"
        if copy not in source:
            errors.append(f"{where}: falta `{copy}` no estágio {s.service}")
    for group in reg.groups:
        if f"FROM runtime AS {group}" not in source:
            errors.append(f"{where}: falta o estágio `FROM runtime AS {group}`")
    return errors


def _env_map(entries) -> dict[str, str]:
    return {e["key"]: str(e.get("value") or "") for e in entries or []}


def check_deploy_spec(reg: Registry, path: Path) -> list[str]:
    where = str(path)
    spec = reg.yaml(path)
    services = {svc["name"]: svc for svc in spec.get("services") or []}
    rules = [r for r in (spec.get("ingress") or {}).get("rules") or [] if r.get("component")]
    by_host = {
        (r.get("match") or {}).get("authority", {}).get("exact"): r["component"]["name"]
        for r in rules
        if (r.get("match") or {}).get("authority")
    }
    envs = _env_map(spec.get("envs"))
    for svc in services.values():
        envs.update(_env_map(svc.get("envs")))
    errors = []

    domain = next((h.split(".", 1)[1] for h in by_host if h and h.startswith("api.")), None)
    if domain is None:
        return [f"{where}: sem host `api.` no ingress; não sei qual é o domínio da loja"]

    for s in reg.surfaces:
        if s.service not in services:
            errors.append(f"{where}: falta o service {s.service} (de {s.id})")
        if s.subdomain:
            host = f"{s.subdomain}.{domain}"
            if by_host.get(host) != s.service:
                errors.append(
                    f"{where}: o ingress de {host} deveria ir para {s.service} (vai para {by_host.get(host)})"
                )
        if s.base_url_env:
            if s.base_url_env not in envs:
                errors.append(f"{where}: falta a env {s.base_url_env}")
            elif s.subdomain and envs[s.base_url_env] != f"https://{s.subdomain}.{domain}":
                errors.append(
                    f"{where}: {s.base_url_env}={envs[s.base_url_env]!r}, e o subdomínio é {s.subdomain}.{domain}"
                )

    for group in reg.groups:
        if group not in services:
            continue
        raw = _env_map(services[group].get("envs")).get("OPERATOR_HOSTS", "")
        declared = {tuple(pair.split("=", 1)) for pair in raw.split(",") if "=" in pair}
        expected = {(s.id, f"{s.subdomain}.{domain}") for s in reg.operators if s.service == group}
        errors += _diff(f"{where} (OPERATOR_HOSTS de {group})", "o par", expected, declared)

    # Host roteado para um grupo que o registro não conhece: app fantasma.
    known = {f"{s.subdomain}.{domain}" for s in reg.operators}
    for host, component in by_host.items():
        if component in reg.groups and host not in known:
            errors.append(f"{where}: {host} vai para {component} e nenhum app do registro tem esse subdomínio")
    return errors


# ── Django ──────────────────────────────────────────────────────────────────


def _dict_block(source: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\b[^=]*=\s*\{{(.*?)^\}}", source, re.M | re.S)
    return match.group(1) if match else ""


def check_django_settings(reg: Registry) -> list[str]:
    where = "config/settings.py"
    source = reg.read(where)
    errors = []
    origins = "".join(re.findall(r"^\s*CSRF_TRUSTED_ORIGINS \+= \[(.*?)^\s*\]", source, re.M | re.S))
    for host in ("localhost", "127.0.0.1"):
        ports = {int(p) for p in re.findall(rf'"http://{re.escape(host)}:(\d+)"', origins)}
        errors += _diff(
            f"{where} (CSRF_TRUSTED_ORIGINS, {host})", "a porta de dev", {s.dev_port for s in reg.surfaces}, ports
        )
    for s in reg.surfaces:
        if s.base_url_env and not re.search(rf"^{s.base_url_env}\s*=", source, re.M):
            errors.append(f"{where}: falta `{s.base_url_env} = ...`")
    block = _dict_block(source, "SHOPMAN_SURFACE_URLS")
    tiles = set(re.findall(r'"(\w+)":\s*(SHOPMAN_\w+_BASE_URL)', block))
    expected = {(s.hub_tile, s.base_url_env) for s in reg.surfaces if s.hub_tile}
    errors += _diff(f"{where} (SHOPMAN_SURFACE_URLS)", "o tile", expected, tiles)
    return errors


def check_hub_projection(reg: Registry) -> list[str]:
    where = "shopman/backstage/projections/hub.py"
    source = reg.read(where)
    block = _dict_block(source, "DEV_SURFACE_URLS")
    urls = {(tile, int(port)) for tile, port in re.findall(r'"(\w+)":\s*"http://127\.0\.0\.1:(\d+)/"', block)}
    errors = _diff(
        f"{where} (DEV_SURFACE_URLS)", "o tile", {(s.hub_tile, s.dev_port) for s in reg.surfaces if s.hub_tile}, urls
    )
    specs = set(re.findall(r'_AppSpec\("(\w+)"', source))
    for s in reg.surfaces:
        if s.hub_tile and s.hub_tile not in specs:
            errors.append(f'{where}: falta o `_AppSpec("{s.hub_tile}", ...)` de {s.id}')
    return errors


# ── operator-kit ────────────────────────────────────────────────────────────


def check_app_identity(reg: Registry) -> list[str]:
    where = "surfaces/operator-kit/app-identity.json"
    apps = set(json.loads(reg.read(where)).get("apps") or {})
    return _diff(where, "a identidade do app", {s.id for s in reg.operators}, apps)


def check_pwa_gate(reg: Registry) -> list[str]:
    where = "tools/pwa-gate/check.mjs"
    match = re.search(r"^const profiles = \{(.*?)^\}", reg.read(where), re.M | re.S)
    profiles = set(re.findall(r"^  (\w+): ", match.group(1) if match else "", re.M))
    return _diff(f"{where} (profiles)", "o perfil", {s.id for s in reg.surfaces}, profiles)


# ── documentação ────────────────────────────────────────────────────────────


def check_docs_tree(reg: Registry) -> list[str]:
    errors = []
    for where in ("CLAUDE.md", "README.md"):
        lines = reg.read(where).splitlines()
        for s in reg.surfaces:
            line = next((ln for ln in lines if re.search(rf"[├└]── {re.escape(s.dir)}/", ln)), None)
            if line is None:
                errors.append(f"{where}: a árvore de surfaces/ não lista {s.dir}/")
            elif f":{s.dev_port}" not in line:
                errors.append(f"{where}: a linha de {s.dir}/ não diz a porta :{s.dev_port}")
    return errors


CHECKS = (
    check_registry_shape,
    check_directories,
    check_dependabot,
    check_surfaces_gate,
    check_makefile,
    check_dev_ports,
    check_layer,
    check_operator_groups,
    check_operator_dockerfile,
    *(lambda reg, p=p: check_deploy_spec(reg, p) for p in DEPLOY_SPECS),
    check_django_settings,
    check_hub_projection,
    check_app_identity,
    check_pwa_gate,
    check_docs_tree,
)


def run(root: Path = ROOT) -> list[str]:
    reg = Registry(root)
    errors: list[str] = []
    for check in CHECKS:
        try:
            errors += check(reg)
        except FileNotFoundError as exc:
            errors.append(f"{Path(exc.filename).relative_to(root) if exc.filename else '?'}: arquivo não existe")
        except (KeyError, TypeError) as exc:
            errors.append(f"{getattr(check, '__name__', 'check')}: estrutura inesperada ({exc!r})")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    errors = run(Path(args.root))
    if args.json:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print(f"✗ {len(errors)} lugar(es) discordam de {REGISTRY}:\n", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print(f"\nA tabela é {REGISTRY}; o que diverge dela é o arquivo apontado.", file=sys.stderr)
    else:
        print(f"✓ todos os lugares concordam com {REGISTRY}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
