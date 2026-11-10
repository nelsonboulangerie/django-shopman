#!/usr/bin/env python
"""Promove um release do ``main`` para produção, sem reconstruir nada.

WP-RELEASE-01 R2. Não há alpha depois do go-live (decisão do dono, 10/11/2026):
o ensaio é o ``plan`` (o dry-run, que roda antes de toda promoção) e a prova é
a verificação depois (``verify`` + ``smoke`` contra a produção).

Quem chama é ``.github/workflows/promote-release.yml``, passo a passo, e a
ordem é o contrato (``docs/reference/release-contract.md``):

``locate --release-id ID``
    Release ID → commit (pelo git, que recalcula o ID) → o run de PUSH do Deploy
    Images daquele commit que terminou bem. Imprime ``sha=`` e ``run_id=`` no
    formato do ``$GITHUB_OUTPUT``.

``plan --release-id ID --manifest release-manifest.json --deploy-run N``
    Valida, sem escrever nada: manifesto completo (os quatro componentes, com
    digest), ancestralidade (o commit está no ``main``; cada componente vem de
    um ancestral dele), os digests presentes no registry com os bytes conferidos, e a proteção do
    GitHub Environment ``production``. Escreve ``plan.json``.

``retag --plan plan.json``
    Para cada componente, lê do registry os bytes do manifest PELO DIGEST, confere
    o sha256 e escreve os MESMOS bytes sob ``<tag>-prod``. Depois relê a tag e
    cobra o mesmo digest. Não há caminho de upload de camada neste código.

``check-app --app-name N``
    O app de produção está com todos os componentes nas tags ``-prod`` e sem
    ``deploy_on_push``? Senão, promover não chegaria nele (ou chegaria sozinho,
    fora deste fluxo).

``deploy --app-id ID``
    Cria UM deployment e espera ACTIVE. A App Platform resolve as tags no
    instante do deployment, e elas acabaram de ser conferidas.

``verify --plan plan.json --url componente=URL ...``
    O ``/health/release`` de cada componente responde o commit de origem que o
    manifesto registra: a prova pelo artefato no ar, já que o deployment da DO
    não carrega digest.

``smoke --api-url U --storefront-url U``
    As asserções do Pre-go-live Smoke contra os endereços de produção.

Saídas: 0 ok; 1 recusa (com o motivo); 2 uso/credencial.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RM = _load("promote_release_manifest", "release_manifest.py")

API = "https://api.digitalocean.com/v2"
ENVIRONMENT = "production"
DEPLOY_WORKFLOW = "deploy-images.yml"
USER_AGENT = "shopman-promote-release/1"

Gh = Callable[[str], object]


class Recusa(RuntimeError):
    """Motivo para NÃO promover. Sempre dito por extenso."""


# ── git ──────────────────────────────────────────────────────────────────────


def _git(*args: str, root: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def release_id_of(sha: str, root: Path = REPO_ROOT) -> str:
    """O mesmo cálculo do passo `Release ID` do Deploy Images."""
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cd", "--date=format-local:%Y%m%d-%H%M", sha],
        cwd=root, capture_output=True, text=True, env={**os.environ, "TZ": "UTC"},
    )
    if result.returncode != 0:
        raise Recusa(f"commit {sha} não existe neste clone")
    return f"{result.stdout.strip()}-{sha[:7]}"


def resolve_sha(release_id: str, main_ref: str, root: Path = REPO_ROOT) -> str:
    if not RM.RELEASE_ID.match(release_id):
        raise Recusa(f"Release ID fora do formato AAAAMMDD-HHMM-<sha7>: {release_id!r}")
    curto = release_id.rsplit("-", 1)[1]
    result = _git("rev-parse", "--verify", "--quiet", f"{curto}^{{commit}}", root=root)
    sha = result.stdout.strip()
    if result.returncode != 0 or not RM.SHA.match(sha):
        raise Recusa(f"o commit {curto} do {release_id} não existe (ou é ambíguo) neste clone")
    if release_id_of(sha, root) != release_id:
        raise Recusa(f"{release_id} não é o Release ID do commit {sha[:7]} ({release_id_of(sha, root)})")
    if _git("merge-base", "--is-ancestor", sha, main_ref, root=root).returncode != 0:
        raise Recusa(f"o commit {sha[:7]} não está no {main_ref}: só release do main é promovível")
    return sha


def check_ancestry(manifest: dict, root: Path = REPO_ROOT) -> list[str]:
    erros = []
    git_sha = manifest["git_sha"]
    for component, entry in manifest["release_set"].items():
        build_sha = entry["build_sha"]
        if build_sha != git_sha and _git("merge-base", "--is-ancestor", build_sha, git_sha, root=root).returncode != 0:
            erros.append(f"{component}: build {build_sha[:7]} não é ancestral do release {git_sha[:7]}")
    return erros


# ── GitHub ───────────────────────────────────────────────────────────────────


def gh_api(path: str) -> object:
    result = subprocess.run(["gh", "api", "-X", "GET", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise Recusa(f"gh api {path}: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout)


def find_deploy_run(repo: str, sha: str, gh: Gh = gh_api) -> dict:
    """O run de PUSH do Deploy Images deste commit que terminou bem.

    Dispatch não serve: publica subconjunto escolhido à mão (a mesma razão de
    ele não virar base no próprio Deploy Images).
    """
    payload = gh(
        f"repos/{repo}/actions/workflows/{DEPLOY_WORKFLOW}/runs?head_sha={sha}&event=push&status=success&per_page=10"
    )
    runs = [r for r in (payload or {}).get("workflow_runs") or [] if r.get("head_sha") == sha]
    if not runs:
        raise Recusa(f"nenhum Deploy Images de push terminou bem para {sha[:7]}")
    return max(runs, key=lambda r: r.get("run_attempt") or 0)


def environment_protection(repo: str, gh: Gh = gh_api) -> list[str]:
    """O que falta no Environment `production` para a promoção ser protegida."""
    try:
        env = gh(f"repos/{repo}/environments/{ENVIRONMENT}")
    except Recusa as exc:
        return [f"o GitHub Environment `{ENVIRONMENT}` não existe ou não pôde ser lido ({exc})"]
    faltas = []
    regras = {r.get("type"): r for r in (env or {}).get("protection_rules") or []}
    revisores = (regras.get("required_reviewers") or {}).get("reviewers") or []
    if not revisores:
        faltas.append(f"`{ENVIRONMENT}` sem revisor obrigatório (required reviewers)")
    politica = (env or {}).get("deployment_branch_policy") or {}
    if not (politica.get("protected_branches") or politica.get("custom_branch_policies")):
        faltas.append(f"`{ENVIRONMENT}` aceita deployment de qualquer branch (restrinja ao main)")
    return faltas


# ── plano ────────────────────────────────────────────────────────────────────


def build_plan(
    *,
    release_id: str,
    manifest: dict,
    repo: str,
    deploy_run: dict,
    main_ref: str = "origin/main",
    registry=None,
    gh: Gh = gh_api,
    require_protection: bool = False,
    root: Path = REPO_ROOT,
) -> dict:
    """Todas as recusas de uma vez: quem lê o run quer a lista, não a primeira."""
    sha = resolve_sha(release_id, main_ref, root)
    erros = RM.validate(manifest)
    if manifest.get("release_id") != release_id:
        erros.append(f"o manifesto é do {manifest.get('release_id')}, não do {release_id}")
    if manifest.get("git_sha") != sha:
        erros.append(f"o manifesto é do commit {str(manifest.get('git_sha'))[:7]}, não do {sha[:7]}")
    if manifest.get("source_run") != deploy_run.get("id"):
        erros.append(f"o manifesto veio do run {manifest.get('source_run')}, não do {deploy_run.get('id')}")
    if erros:
        raise Recusa("; ".join(erros))
    erros = check_ancestry(manifest, root)

    componentes = {}
    for component in RM.RELEASE_COMPONENTS:
        entry = manifest["release_set"][component]
        alvo = RM.production_tag(entry["tag"])
        linha = {
            "tag": entry["tag"],
            "digest": entry["digest"],
            "immutable_tag": entry["immutable_tag"],
            "build_sha": entry["build_sha"],
            "production_tag": alvo,
            "production_digest_before": None,
        }
        if registry is not None:
            try:
                if registry.head_digest(entry["immutable_tag"]) != entry["digest"]:
                    erros.append(f"{component}: `{entry['immutable_tag']}` não aponta mais para {entry['digest']}")
                registry.get_manifest(entry["digest"])  # existe, é imagem e os bytes batem
                linha["production_digest_before"] = registry.head_digest(alvo)
            except RM.RegistryError as exc:
                erros.append(f"{component}: {exc}")
        linha["action"] = "unchanged" if linha["production_digest_before"] == entry["digest"] else "retag"
        componentes[component] = linha

    protecao = environment_protection(repo, gh)
    if require_protection:
        erros.extend(protecao)
    if erros:
        raise Recusa("; ".join(erros))
    return {
        "release_id": release_id,
        "git_sha": sha,
        "source_run": deploy_run.get("id"),
        "migration_graph_hash": manifest.get("migration_graph_hash"),
        "registry_checked": registry is not None,
        "environment_protection_gaps": protecao,
        "components": componentes,
    }


# ── retag ────────────────────────────────────────────────────────────────────


def retag(plan: dict, registry) -> list[str]:
    """Escreve os MESMOS bytes sob a tag de produção e cobra o mesmo digest.

    Lê pelo digest (nunca pela tag móvel, que o próximo push pode ter mexido),
    confere sha256 dos bytes antes de escrever e relê a tag depois.
    """
    feitos = []
    for component, linha in plan["components"].items():
        digest, alvo = linha["digest"], linha["production_tag"]
        if registry.head_digest(alvo) == digest:
            feitos.append(f"{component}: `{alvo}` já aponta para {digest}")
            continue
        manifest = registry.get_manifest(digest)
        registry.put_manifest(alvo, manifest)
        lido = registry.head_digest(alvo)
        if lido != digest:
            raise Recusa(f"{component}: `{alvo}` ficou em {lido}, não em {digest}")
        feitos.append(f"{component}: `{alvo}` → {digest}")
    return feitos


# ── DigitalOcean ─────────────────────────────────────────────────────────────


def _do(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def check_app(apps: list[dict], name: str) -> str:
    app = next((a for a in apps if (a.get("spec") or {}).get("name") == name), None)
    if not app:
        raise Recusa(f"o app de produção `{name}` não existe na conta")
    papel = RM.app_role(app["spec"])
    if papel.role != "production":
        raise Recusa(
            f"o app `{name}` não está nas tags de produção (papel: {papel.role}; "
            f"alpha={papel.alpha} prod={papel.production} outras={papel.other}). "
            "Promover não chegaria nele: aplique antes a proposta de spec do runbook."
        )
    if papel.deploy_on_push:
        raise Recusa(f"`{name}` tem deploy_on_push em {papel.deploy_on_push}: a produção andaria sozinha")
    return app["id"]


def deploy(app_id: str, deploy_token: str, read_token: str, max_seconds: int = 900, interval: int = 15) -> dict:
    criado = _do("POST", f"/apps/{app_id}/deployments", deploy_token, {"force_build": False})["deployment"]
    dep_id, fase = criado["id"], criado.get("phase")
    print(f"deployment {dep_id} criado")
    prazo = time.monotonic() + max_seconds
    while fase not in ("ACTIVE", "ERROR", "CANCELED", "SUPERSEDED") and time.monotonic() < prazo:
        time.sleep(interval)
        fase = _do("GET", f"/apps/{app_id}/deployments/{dep_id}", read_token)["deployment"].get("phase")
        print(f"{time.strftime('%H:%M:%SZ', time.gmtime())}  {fase}")
    if fase != "ACTIVE":
        # SUPERSEDED também recusa: em produção só a promoção cria deployment,
        # e outro por cima deste é alguém agindo fora do fluxo.
        raise Recusa(f"o deployment {dep_id} terminou em {fase}: o release NÃO está no ar")
    return {"id": dep_id, "phase": fase}


# ── prova no ar ──────────────────────────────────────────────────────────────


def _get(url: str, timeout: int = 20) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def identity_mismatches(plan: dict, responses: dict[str, dict]) -> list[str]:
    erros = []
    for component, linha in plan["components"].items():
        corpo = responses.get(component)
        if corpo is None:
            erros.append(f"{component}: sem endereço de /health/release")
            continue
        if corpo.get("component") != component:
            erros.append(f"{component}: o endereço serve `{corpo.get('component')}`")
        elif corpo.get("build_sha") != linha["build_sha"]:
            erros.append(
                f"{component}: no ar {str(corpo.get('build_sha') or '<sem identidade>')[:7]}, "
                f"promovido {linha['build_sha'][:7]}"
            )
    return erros


def verify(plan: dict, urls: dict[str, str], attempts: int = 10, interval: int = 30, get=_get) -> None:
    ultimo: list[str] = []
    for tentativa in range(1, attempts + 1):
        respostas = {}
        for component, url in urls.items():
            status, body = get(url)
            try:
                respostas[component] = json.loads(body) if status == 200 else {"component": f"HTTP {status}"}
            except ValueError:
                respostas[component] = {"component": "resposta não-JSON"}
        ultimo = identity_mismatches(plan, respostas)
        if not ultimo:
            for component in plan["components"]:
                print(f"{component:16} no ar {plan['components'][component]['build_sha'][:7]}  ok")
            return
        print(f"tentativa {tentativa}: {'; '.join(ultimo)}")
        if tentativa < attempts:
            time.sleep(interval)
    raise Recusa("o que está no ar não é o que foi promovido: " + "; ".join(ultimo))


def smoke(api_url: str, storefront_url: str, menu_min: int = 30, get=_get, post=None) -> None:
    """As quatro asserções do Pre-go-live Smoke, contra produção."""
    menu_mod = _load("promote_release_menu_smoke", "check_menu_smoke.py")
    erros = []
    status, _ = get(f"{api_url.rstrip('/')}/ready/")
    if status != 200:
        erros.append(f"/ready/ respondeu {status}")
    status, body = get(f"{api_url.rstrip('/')}/api/v1/storefront/menu/")
    try:
        if status != 200:
            raise ValueError(f"HTTP {status}")
        print(f"cardápio: {menu_mod.check_menu(json.loads(body), minimum_skus=max(1, menu_min))}")
    except ValueError as exc:
        erros.append(f"cardápio: {exc}")
    status, body = (post or _post_json)(f"{storefront_url.rstrip('/')}/api/v1/checkout/")
    try:
        codigo = json.loads(body).get("error_code") if body else None
    except ValueError:
        codigo = None
    if status != 403 or codigo != "authentication_required":
        erros.append(f"checkout anônimo respondeu {status} {codigo!r}, esperado 403 authentication_required")
    status, body = get(f"{storefront_url.rstrip('/')}/")
    if status != 200 or len(body) <= 20000 or b"nelson" not in body.lower():
        erros.append(f"a loja não renderizou (HTTP {status}, {len(body)} bytes)")
    if erros:
        raise Recusa("smoke de produção vermelho: " + "; ".join(erros))
    print("smoke de produção: /ready/, cardápio, checkout e SSR ok")


def _post_json(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url, data=b"{}", method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# ── CLI ──────────────────────────────────────────────────────────────────────


def _out(**campos: object) -> None:
    linhas = "".join(f"{k}={v}\n" for k, v in campos.items())
    destino = os.environ.get("GITHUB_OUTPUT")
    if destino:
        with open(destino, "a", encoding="utf-8") as fh:
            fh.write(linhas)
    print(linhas, end="")


def _token(name: str) -> str:
    valor = os.environ.get(name, "")
    if not valor:
        raise SystemExit(f"::error::{name} ausente")
    return valor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("locate")
    p.add_argument("--release-id", required=True)
    p.add_argument("--main-ref", default="origin/main")
    p = sub.add_parser("plan")
    p.add_argument("--release-id", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--deploy-run", type=int, required=True)
    p.add_argument("--main-ref", default="origin/main")
    p.add_argument("--require-protection", action="store_true")
    p.add_argument("--out", default="plan.json")
    p = sub.add_parser("retag")
    p.add_argument("--plan", required=True)
    p = sub.add_parser("check-app")
    p.add_argument("--app-name", required=True)
    p = sub.add_parser("deploy")
    p.add_argument("--app-id", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--plan", required=True)
    p.add_argument("--url", action="append", default=[], help="componente=https://.../health/release")
    p = sub.add_parser("smoke")
    p.add_argument("--api-url", required=True)
    p.add_argument("--storefront-url", required=True)
    p.add_argument("--menu-min", type=int, default=int(os.environ.get("MENU_MIN_SKUS") or 30))
    args = parser.parse_args(argv)

    try:
        if args.cmd == "locate":
            sha = resolve_sha(args.release_id, args.main_ref)
            run = find_deploy_run(args.repo, sha)
            _out(sha=sha, run_id=run["id"])
        elif args.cmd == "plan":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            run = gh_api(f"repos/{args.repo}/actions/runs/{args.deploy_run}")
            token = os.environ.get("DO_TOKEN", "")
            registry = RM.Registry(token) if token else None
            if registry is None:
                print("::warning::sem DO_TOKEN: digests NÃO conferidos no registry neste plano")
            plan = build_plan(
                release_id=args.release_id, manifest=manifest, repo=args.repo, deploy_run=run,
                main_ref=args.main_ref, registry=registry, require_protection=args.require_protection,
            )
            Path(args.out).write_text(json.dumps(plan, indent=2), encoding="utf-8")
            print(json.dumps(plan, indent=2))
            for falta in plan["environment_protection_gaps"]:
                print(f"::warning::{falta}")
        elif args.cmd == "retag":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            for linha in retag(plan, RM.Registry(_token("DO_TOKEN"), push=True)):
                print(linha)
        elif args.cmd == "check-app":
            apps = _do("GET", "/apps?per_page=200", _token("DO_TOKEN")).get("apps") or []
            _out(app_id=check_app(apps, args.app_name))
        elif args.cmd == "deploy":
            dep = deploy(
                args.app_id, _token("DO_DEPLOY_TOKEN"), _token("DO_TOKEN"),
                max_seconds=int(os.environ.get("DEPLOY_WAIT_MAX_SECONDS") or 900),
            )
            _out(deployment_id=dep["id"])
        elif args.cmd == "verify":
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            urls = dict(item.split("=", 1) for item in args.url if "=" in item and item.split("=", 1)[1])
            verify(plan, urls)
        elif args.cmd == "smoke":
            smoke(args.api_url, args.storefront_url, args.menu_min)
    except (Recusa, RM.RegistryError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
