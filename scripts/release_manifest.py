#!/usr/bin/env python
"""Manifesto da release e papel do app na DigitalOcean (WP-RELEASE-01 R2).

Três perguntas, nenhuma lista manual nova (os componentes e as tags saem de
``scripts/release_inventory.py`` e ``scripts/deploy_components.py``):

``release-set --manifest published.json``
    Completa o manifesto do run do Deploy Images com o **release set**: os
    quatro componentes (`web`, `storefront-nuxt`, `operator-floor`,
    `operator-office`) com digest, tag imutável e commit de origem, inclusive os
    que este run NÃO construiu (o deploy é seletivo). Quem diz o digest de um
    componente que não foi construído é o registry, pela tag móvel do alpha, que
    é exatamente o que o deployment do alpha vai puxar. Quem diz o commit é a
    LABEL OCI que a R1 grava na imagem; imagem anterior à R1 cai na tag imutável
    com o mesmo digest.

    Não reprova o run: falha de registry vira ``release_set_error`` no manifesto,
    e a promoção recusa esse release (falha fechada lá, onde importa, sem
    derrubar o alpha por instabilidade da API).

``validate --manifest release-manifest.json``
    O manifesto serve de base para promoção? Saída 0 = sim; 1 = não, com cada
    motivo numa linha.

``app-role --spec spec.json``
    O app é alpha (tags móveis), produção (tags ``-prod``) ou está misturado?

Uso no CI: ``.github/workflows/deploy-images.yml`` (job ``manifest``) e
``.github/workflows/promote-release.yml``. Contrato:
``docs/reference/release-contract.md``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # @dataclass procura o módulo em sys.modules
    spec.loader.exec_module(module)
    return module


_RI = _load("release_manifest_release_inventory", "release_inventory.py")
DC = _RI.DC

#: Os componentes do release set, na ordem do contrato (fonte: release_inventory).
RELEASE_COMPONENTS: tuple[str, ...] = _RI.RELEASE_COMPONENTS

SCHEMA_VERSION = 2

#: Sufixo das tags de produção. Só o `promote-release.yml` escreve nelas; o
#: Deploy Images nunca (há teste que lê o workflow e cobra isso).
PRODUCTION_SUFFIX = "-prod"

#: Modos em que o manifesto prova que o alpha rodou este release set. Fora
#: deles (`production_pinned`: o app é produção e o push não implantou nada) o
#: release não esteve no alpha e não pode ser promovido.
ALPHA_DEPLOY_MODES = frozenset({"single_deployment", "deploy_on_push", "nothing_published"})

REGISTRY = "nelsonboulangerie"
REPOSITORY = "shopman"
API = "https://api.digitalocean.com/v2"
DISTRIBUTION = "https://registry.digitalocean.com/v2"
# ⚠️ Cloudflare na frente do registry responde 403 ao agente padrão do urllib
# (medido em 22/09/2026, ver scripts/check_registry_drift.py).
USER_AGENT = "shopman-release-manifest/1"
#: Só manifest de IMAGEM. O App Platform não aceita índice (o buildx com
#: attestation produzia índice em 26/08), e a promoção não tem por que aceitar.
IMAGE_MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
LABEL_REVISION = "org.opencontainers.image.revision"
LABEL_VERSION = "org.opencontainers.image.version"
LABEL_TITLE = "org.opencontainers.image.title"

RELEASE_ID = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{7}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
IMMUTABLE = re.compile(r"^(?P<tag>.+)-(?P<sha>[0-9a-f]{40})$")


def moving_tags() -> dict[str, str]:
    """Componente → tag móvel do alpha. Sai do `build_matrix`, sem segunda lista."""
    groups = DC.load_groups(REPO_ROOT / "surfaces" / "operator-router" / "groups.json")
    return {row["name"]: row["tag"] for row in DC.build_matrix(list(RELEASE_COMPONENTS), groups)}


def production_tag(tag: str) -> str:
    return f"{tag}{PRODUCTION_SUFFIX}"


# ── Registry (API de distribuição do DOCR) ───────────────────────────────────


class RegistryError(RuntimeError):
    """Não deu para perguntar ao registry, ou a resposta não serve."""


class _SemAuthNoRedirect(urllib.request.HTTPRedirectHandler):
    """O blob do DOCR redireciona para o storage, com URL assinada. Levar o
    bearer do registry para outro host é vazar credencial e, de quebra, o
    storage recusa dois mecanismos de auth ao mesmo tempo."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        novo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if novo is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            novo.headers.pop("Authorization", None)
            novo.unredirected_hdrs.pop("Authorization", None)
        return novo


_OPENER = urllib.request.build_opener(_SemAuthNoRedirect)


class Manifest(NamedTuple):
    body: bytes
    media_type: str
    digest: str


class Registry:
    """Cliente mínimo: HEAD/GET/PUT de MANIFEST e GET de blob de config.

    ⚠️ Não existe aqui caminho para subir camada (upload de blob). Promover é
    escrever, sob outro nome, os MESMOS bytes de um manifest que já está no
    registry; uma imagem nova não tem como nascer por este cliente. Há teste que
    cobra a ausência.
    """

    def __init__(self, token: str, *, push: bool = False, registry: str = REGISTRY, repository: str = REPOSITORY):
        if not token:
            raise RegistryError("sem token da DigitalOcean para o registry")
        self.registry = registry
        self.repository = repository
        self._do_token = token
        self._push = push
        self._bearer: str | None = None

    # A troca de token é a do `docker login` do DOCR: Basic com o token da DO.
    def _bearer_token(self) -> str:
        if self._bearer:
            return self._bearer
        acoes = "pull,push" if self._push else "pull"
        scope = f"repository:{self.registry}/{self.repository}:{acoes}"
        url = f"{API}/registry/auth?service=registry.digitalocean.com&scope={urllib.parse.quote(scope, safe='')}"
        basic = base64.b64encode(f"{self._do_token}:{self._do_token}".encode()).decode()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}", "User-Agent": USER_AGENT})
        try:
            with _OPENER.open(req, timeout=30) as resp:
                payload = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise RegistryError(f"auth do registry ({scope}): {exc}") from exc
        bearer = payload.get("token") if isinstance(payload, dict) else None
        if not bearer:
            raise RegistryError("auth do registry respondeu sem `token`")
        self._bearer = bearer
        return bearer

    def _request(self, method: str, path: str, *, data: bytes | None = None, headers: dict | None = None):
        url = f"{DISTRIBUTION}/{self.registry}/{self.repository}/{path}"
        h = {"Authorization": f"Bearer {self._bearer_token()}", "User-Agent": USER_AGENT}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            return _OPENER.open(req, timeout=60)
        except urllib.error.HTTPError as exc:
            raise RegistryError(f"{method} {url}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise RegistryError(f"{method} {url}: {exc}") from exc

    def head_digest(self, reference: str) -> str | None:
        """Digest para onde a tag/digest aponta; None se não existe (404)."""
        try:
            with self._request("HEAD", f"manifests/{reference}", headers={"Accept": ", ".join(IMAGE_MANIFEST_TYPES)}) as resp:
                digest = resp.headers.get("Docker-Content-Digest") or ""
        except RegistryError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        if not DIGEST.match(digest):
            raise RegistryError(f"HEAD manifests/{reference}: sem Docker-Content-Digest")
        return digest

    def get_manifest(self, digest: str) -> Manifest:
        """Bytes EXATOS do manifest, conferidos contra o digest pedido."""
        with self._request("GET", f"manifests/{digest}", headers={"Accept": ", ".join(IMAGE_MANIFEST_TYPES)}) as resp:
            body = resp.read()
            media_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
        return check_manifest(body, media_type, digest)

    def put_manifest(self, tag: str, manifest: Manifest) -> str:
        """Escreve os mesmos bytes sob `tag`. Devolve o digest que o registry diz."""
        if not self._push:
            raise RegistryError("cliente aberto só para leitura")
        with self._request("PUT", f"manifests/{tag}", data=manifest.body, headers={"Content-Type": manifest.media_type}) as resp:
            return resp.headers.get("Docker-Content-Digest") or ""

    def get_config_labels(self, manifest: Manifest) -> dict[str, str]:
        config = (json.loads(manifest.body).get("config") or {}).get("digest") or ""
        if not DIGEST.match(config):
            raise RegistryError("manifest sem config digest")
        with self._request("GET", f"blobs/{config}") as resp:
            blob = json.loads(resp.read())
        return dict(((blob.get("config") or {}).get("Labels")) or {})

    def list_tags(self) -> list[dict]:
        """Listagem da API da DO (tag → manifest_digest). Só para imagem pré-R1."""
        tags: list[dict] = []
        url = f"{API}/registry/{self.registry}/repositories/{self.repository}/tags?per_page=200"
        while url:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._do_token}", "User-Agent": USER_AGENT})
            try:
                with _OPENER.open(req, timeout=30) as resp:
                    payload = json.load(resp)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise RegistryError(f"GET {url}: {exc}") from exc
            tags.extend(payload.get("tags") or [])
            url = ((payload.get("links") or {}).get("pages") or {}).get("next") or ""
        return tags


def check_manifest(body: bytes, media_type: str, digest: str) -> Manifest:
    """O sha256 dos bytes TEM de ser o digest. É o que impede escrever outra coisa."""
    real = "sha256:" + hashlib.sha256(body).hexdigest()
    if real != digest:
        raise RegistryError(f"bytes do manifest têm {real}, não {digest}")
    if media_type not in IMAGE_MANIFEST_TYPES:
        raise RegistryError(f"{digest} é {media_type or 'tipo desconhecido'}, não manifest de imagem")
    return Manifest(body, media_type, digest)


# ── Release set ──────────────────────────────────────────────────────────────


def migration_graph_hash(root: Path = REPO_ROOT) -> str:
    """sha256 sobre (caminho, sha256 do conteúdo) de toda migration versionada.

    Igual entre dois releases = mesmo grafo de schema. A R3 usa para recusar
    rollback por cima de migration que o release anterior não conhece.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*/migrations/*.py"],
        cwd=root, capture_output=True, check=True,
    )
    paths = sorted(p for p in result.stdout.decode().split("\0") if p)
    h = hashlib.sha256()
    for path in paths:
        h.update(path.encode() + b"\0")
        h.update(hashlib.sha256((root / path).read_bytes()).hexdigest().encode() + b"\n")
    return "sha256:" + h.hexdigest()


def _from_published(entry: dict, sha: str) -> dict:
    return {
        "tag": entry["tag"],
        "digest": entry["digest"],
        "immutable_tag": entry["immutable_tag"],
        "build_sha": sha,
        "release_id": entry.get("release_id") or "",
        "built_in_this_run": True,
    }


def resolve_from_registry(registry: Registry, component: str, tag: str, tags_listing: list[dict] | None) -> dict:
    """O que o alpha vai puxar para um componente que este run não construiu."""
    digest = registry.head_digest(tag)
    if not digest:
        raise RegistryError(f"a tag móvel `{tag}` não existe no registry")
    manifest = registry.get_manifest(digest)
    labels = registry.get_config_labels(manifest)
    build_sha = labels.get(LABEL_REVISION, "")
    release_id = labels.get(LABEL_VERSION, "")
    if SHA.match(build_sha):
        title = labels.get(LABEL_TITLE, "")
        if title and title != component:
            raise RegistryError(f"`{tag}` aponta para imagem de `{title}`, não de `{component}`")
        immutable = f"{tag}-{build_sha}"
        if registry.head_digest(immutable) != digest:
            raise RegistryError(f"`{immutable}` não aponta para {digest}: candidato adulterado ou apagado")
    else:
        # Imagem anterior à R1: sem label, o commit sai da tag imutável irmã.
        listing = tags_listing if tags_listing is not None else registry.list_tags()
        shas = sorted(
            (t.get("updated_at") or "", m.group("sha"))
            for t in listing
            if t.get("manifest_digest") == digest
            and (m := IMMUTABLE.match(t.get("tag") or ""))
            and m.group("tag") == tag
        )
        if not shas:
            raise RegistryError(f"`{tag}` ({digest}) não tem label de commit nem tag imutável irmã")
        build_sha = shas[0][1]
        immutable = f"{tag}-{build_sha}"
        release_id = ""
    return {
        "tag": tag,
        "digest": digest,
        "immutable_tag": immutable,
        "build_sha": build_sha,
        "release_id": release_id if RELEASE_ID.match(release_id) else "",
        "built_in_this_run": False,
    }


def compose_release_set(manifest: dict, registry: Registry | None) -> dict[str, dict]:
    """Os quatro componentes. Os construídos vêm do run; os outros, do registry."""
    tags = moving_tags()
    built = {c["name"]: c for c in manifest.get("components") or []}
    release_set: dict[str, dict] = {}
    for component in RELEASE_COMPONENTS:
        if component in built:
            release_set[component] = _from_published(built[component], manifest["git_sha"])
            continue
        if registry is None:
            raise RegistryError(f"{component} não foi construído neste run e não há registry para perguntar")
        release_set[component] = resolve_from_registry(registry, component, tags[component], None)
    return release_set


def complete_manifest(manifest: dict, registry: Registry | None, root: Path = REPO_ROOT, attempts: int = 3) -> dict:
    """Acrescenta release set e hash de migrations. Erro vira campo, não exceção."""
    manifest = dict(manifest)
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["migration_graph_hash"] = migration_graph_hash(root)
    build_result = manifest.get("build_result")
    if build_result not in ("success", "skipped"):
        manifest["release_set_error"] = (
            f"build_result={build_result}: parte do que este commit pedia não foi publicada, "
            "e as tags móveis guardam a versão anterior desses componentes."
        )
        return manifest
    ultimo = ""
    for tentativa in range(1, attempts + 1):
        try:
            manifest["release_set"] = compose_release_set(manifest, registry)
            manifest.pop("release_set_error", None)
            return manifest
        except RegistryError as exc:
            ultimo = str(exc)
            if tentativa < attempts:
                time.sleep(10 * tentativa)
    manifest["release_set_error"] = ultimo
    return manifest


# ── Validação para promoção ──────────────────────────────────────────────────


def validate(manifest: dict) -> list[str]:
    """Tudo o que impede promover este manifesto. Vazio = serve."""
    erros: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifesto não é objeto JSON"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        erros.append(f"schema_version={manifest.get('schema_version')!r}, esperado {SCHEMA_VERSION}")
    release_id = manifest.get("release_id") or ""
    git_sha = manifest.get("git_sha") or ""
    if not RELEASE_ID.match(release_id):
        erros.append(f"release_id fora do formato: {release_id!r}")
    if not SHA.match(git_sha):
        erros.append(f"git_sha fora do formato: {git_sha!r}")
    elif RELEASE_ID.match(release_id) and not release_id.endswith(git_sha[:7]):
        erros.append(f"release_id {release_id} não é do commit {git_sha[:7]}")
    if manifest.get("release_set_error"):
        erros.append(f"release set incompleto no build: {manifest['release_set_error']}")
    mode = manifest.get("deploy_mode")
    if mode not in ALPHA_DEPLOY_MODES:
        erros.append(f"deploy_mode={mode!r}: o alpha não rodou este release set")
    release_set = manifest.get("release_set")
    if not isinstance(release_set, dict):
        erros.append("manifesto sem release_set")
        return erros
    faltando = [c for c in RELEASE_COMPONENTS if c not in release_set]
    sobrando = [c for c in release_set if c not in RELEASE_COMPONENTS]
    if faltando:
        erros.append(f"componentes faltando: {faltando}")
    if sobrando:
        erros.append(f"componentes desconhecidos: {sobrando}")
    tags = moving_tags()
    for component in RELEASE_COMPONENTS:
        entry = release_set.get(component)
        if not isinstance(entry, dict):
            continue
        if entry.get("tag") != tags[component]:
            erros.append(f"{component}: tag {entry.get('tag')!r}, esperado {tags[component]!r}")
        if not DIGEST.match(entry.get("digest") or ""):
            erros.append(f"{component}: digest ilegível {entry.get('digest')!r}")
        build_sha = entry.get("build_sha") or ""
        if not SHA.match(build_sha):
            erros.append(f"{component}: build_sha ilegível {build_sha!r}")
        elif entry.get("immutable_tag") != f"{tags[component]}-{build_sha}":
            erros.append(f"{component}: immutable_tag {entry.get('immutable_tag')!r} não é do build {build_sha[:7]}")
    return erros


# ── Papel do app na DigitalOcean ─────────────────────────────────────────────


class AppRole(NamedTuple):
    role: str  # "alpha" | "production" | "mixed" | "none"
    alpha: list[str]
    production: list[str]
    other: list[str]
    deploy_on_push: list[str]


def app_role(spec: dict) -> AppRole:
    """Lê os componentes de imagem do spec vivo e diz que papel o app tem.

    `alpha`: todo componente nas tags móveis do alpha (`web`, `storefront`...).
    `production`: todo componente nas tags `-prod`. É a separação estrutural
    que torna o push no `main` incapaz de mexer na produção: o Deploy Images só
    escreve tag móvel e imutável, nunca `-prod`.
    `mixed`: qualquer outra combinação, inclusive tag imutável fixada à mão.
    """
    alpha_tags = set(moving_tags().values())
    prod_tags = {production_tag(t) for t in alpha_tags}
    alpha, production, other, on_push = [], [], [], []
    for kind in ("services", "workers", "jobs"):
        for comp in spec.get(kind) or []:
            image = comp.get("image")
            if not image or image.get("repository") != REPOSITORY:
                continue
            name, tag = comp.get("name", "?"), image.get("tag") or ""
            if tag in alpha_tags:
                alpha.append(name)
            elif tag in prod_tags:
                production.append(name)
            else:
                other.append(f"{name}:{tag or '<sem tag>'}")
            if (image.get("deploy_on_push") or {}).get("enabled"):
                on_push.append(name)
    if other or (alpha and production):
        role = "mixed"
    elif production:
        role = "production"
    elif alpha:
        role = "alpha"
    else:
        role = "none"
    return AppRole(role, alpha, production, other, on_push)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cmd_release_set(args) -> int:
    path = Path(args.manifest)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    token = os.environ.get("DO_TOKEN", "")
    try:
        registry = Registry(token) if token else None
    except RegistryError:
        registry = None
    completo = complete_manifest(manifest, registry)
    path.write_text(json.dumps(completo, indent=2), encoding="utf-8")
    if completo.get("release_set_error"):
        print(
            f"::warning::release set do {completo.get('release_id')} ficou incompleto: "
            f"{completo['release_set_error']}. O alpha segue; este release NÃO é promovível.",
            file=sys.stderr,
        )
    else:
        for component, entry in completo["release_set"].items():
            origem = "este run" if entry["built_in_this_run"] else f"registry ({entry['build_sha'][:7]})"
            print(f"{component:16} {entry['digest']}  {origem}")
    return 0


def _cmd_validate(args) -> int:
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"::error::manifesto ilegível: {exc}", file=sys.stderr)
        return 1
    erros = validate(manifest)
    for erro in erros:
        print(f"::error::{erro}", file=sys.stderr)
    if not erros:
        print(f"manifesto do {manifest['release_id']} serve para promoção.")
    return 1 if erros else 0


def _cmd_app_role(args) -> int:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    spec = spec.get("spec", spec)
    print(json.dumps(app_role(spec)._asdict(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("release-set")
    p.add_argument("--manifest", required=True)
    p.set_defaults(fn=_cmd_release_set)
    p = sub.add_parser("validate")
    p.add_argument("--manifest", required=True)
    p.set_defaults(fn=_cmd_validate)
    p = sub.add_parser("app-role")
    p.add_argument("--spec", required=True)
    p.set_defaults(fn=_cmd_app_role)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
