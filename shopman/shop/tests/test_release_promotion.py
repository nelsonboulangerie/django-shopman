"""WP-RELEASE-01 R2: candidato e produção separados, promoção direto do `main`.

Não há alpha depois do go-live (decisão do dono, 10/11/2026): a promoção não
consulta smoke de alpha nenhum; o ensaio é o `plan` e a prova é o smoke de
produção depois do deployment.

Os quatro gates de aceite da R2, cada um com o seu bloco de teste:

1. **Digest no alpha = digest promovido** — o retag escreve os MESMOS bytes e
   relê a tag; um registry falso que calcula o digest dos bytes, como o real,
   prova a igualdade.
2. **Rebuild na promoção é impossível** — o workflow não tem passo de build nem
   Dockerfile no runner, e o cliente de registry não tem caminho de upload.
3. **Manifesto ausente, componente faltando ou smoke vermelho param** — o
   plano recusa antes de escrever, e o smoke recusa depois.
4. **Push no `main` não altera produção** — o Deploy Images nunca escreve tag
   `-prod`, não implanta app que está nas tags `-prod`, e a promoção só nasce
   de dispatch manual com environment protegido.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RM = _load("release_manifest_under_test", "release_manifest.py")
PR = _load("promote_release_under_test", "promote_release.py")
COMPONENTS = RM.RELEASE_COMPONENTS
TAGS = RM.moving_tags()


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML lê a chave `on` como True.
    data["on"] = data.pop(True, data.get("on"))
    return data


# ── registry falso, com a aritmética do real ─────────────────────────────────

MEDIA = "application/vnd.oci.image.manifest.v1+json"


def _manifest_bytes(seed: str) -> bytes:
    config = "sha256:" + hashlib.sha256(f"config-{seed}".encode()).hexdigest()
    return json.dumps(
        {"schemaVersion": 2, "mediaType": MEDIA, "config": {"digest": config}, "layers": [{"digest": f"sha256:{seed}"}]},
        sort_keys=True,
    ).encode()


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


class FakeRegistry:
    """Guarda manifests por digest e tags → digest. O digest é SEMPRE o sha256
    dos bytes, como no registry de verdade: escrever outros bytes sob uma tag
    muda o digest dela, e o teste vê."""

    def __init__(self):
        self.blobs: dict[str, tuple[bytes, str]] = {}
        self.tags: dict[str, str] = {}
        self.labels: dict[str, dict] = {}
        self.listing: list[dict] = []
        self.puts: list[str] = []
        self.fail = False

    def push(self, tag: str, seed: str, labels: dict | None = None, media: str = MEDIA) -> str:
        body = _manifest_bytes(seed)
        digest = _digest(body)
        self.blobs[digest] = (body, media)
        self.tags[tag] = digest
        self.labels[digest] = labels or {}
        return digest

    def head_digest(self, reference: str):
        if self.fail:
            raise RM.RegistryError("registry fora")
        if reference.startswith("sha256:"):
            return reference if reference in self.blobs else None
        return self.tags.get(reference)

    def get_manifest(self, digest: str):
        body, media = self.blobs[digest]
        return RM.check_manifest(body, media, digest)

    def put_manifest(self, tag: str, manifest) -> str:
        digest = _digest(manifest.body)
        self.blobs[digest] = (manifest.body, manifest.media_type)
        self.tags[tag] = digest
        self.puts.append(tag)
        return digest

    def get_config_labels(self, manifest) -> dict:
        return self.labels[manifest.digest]

    def list_tags(self) -> list[dict]:
        return self.listing


SHA_A = "a" * 40
SHA_B = "b" * 40


def _labels(component: str, sha: str, release_id: str = "20261101-1200-aaaaaaa") -> dict:
    return {RM.LABEL_REVISION: sha, RM.LABEL_VERSION: release_id, RM.LABEL_TITLE: component}


def _alpha_registry() -> FakeRegistry:
    """O alpha como fica depois de um run que construiu só `web` no commit B."""
    reg = FakeRegistry()
    for component in COMPONENTS:
        tag = TAGS[component]
        d = reg.push(tag, f"{component}-{SHA_A}", _labels(component, SHA_A))
        reg.tags[f"{tag}-{SHA_A}"] = d
    d = reg.push("web", f"web-{SHA_B}", _labels("web", SHA_B))
    reg.tags[f"web-{SHA_B}"] = d
    return reg


def _run_manifest(reg: FakeRegistry, built: tuple[str, ...] = ("web",), sha: str = SHA_B, **extra) -> dict:
    return {
        "sha": sha,
        "release_id": f"20261109-1200-{sha[:7]}",
        "git_sha": sha,
        "source_run": 42,
        "build_result": "success",
        "deploy_mode": "single_deployment",
        "components": [
            {
                "name": c,
                "tag": TAGS[c],
                "immutable_tag": f"{TAGS[c]}-{sha}",
                "digest": reg.tags[f"{TAGS[c]}-{sha}"],
                "release_id": f"20261109-1200-{sha[:7]}",
            }
            for c in built
        ],
        **extra,
    }


# ── candidato: o manifesto diz o release set inteiro ─────────────────────────


def test_build_seletivo_compoe_os_quatro_componentes_pelo_registry():
    reg = _alpha_registry()
    completo = RM.complete_manifest(_run_manifest(reg), reg)

    assert "release_set_error" not in completo
    assert list(completo["release_set"]) == list(COMPONENTS)
    web = completo["release_set"]["web"]
    assert web["built_in_this_run"] is True
    assert web["build_sha"] == SHA_B
    assert web["digest"] == reg.tags["web"]
    for component in COMPONENTS[1:]:
        entry = completo["release_set"][component]
        assert entry["built_in_this_run"] is False
        assert entry["build_sha"] == SHA_A
        assert entry["digest"] == reg.tags[TAGS[component]]
        assert entry["immutable_tag"] == f"{TAGS[component]}-{SHA_A}"
    assert completo["schema_version"] == RM.SCHEMA_VERSION
    assert completo["migration_graph_hash"].startswith("sha256:")


def test_build_completo_nao_precisa_do_registry():
    reg = _alpha_registry()
    for component in COMPONENTS:
        d = reg.push(TAGS[component], f"{component}-{SHA_B}", _labels(component, SHA_B))
        reg.tags[f"{TAGS[component]}-{SHA_B}"] = d
    completo = RM.complete_manifest(_run_manifest(reg, built=COMPONENTS), None)
    assert all(e["built_in_this_run"] for e in completo["release_set"].values())
    assert RM.validate(completo) == []


def test_imagem_anterior_a_r1_tira_o_commit_da_tag_imutavel_irma():
    reg = _alpha_registry()
    d = reg.push("operator-office", "office-pre-r1", labels={})
    reg.listing = [
        {"tag": "operator-office", "manifest_digest": d, "updated_at": "2026-10-01T00:00:00Z"},
        {"tag": f"operator-office-{'c' * 40}", "manifest_digest": d, "updated_at": "2026-10-01T00:00:00Z"},
    ]
    reg.tags[f"operator-office-{'c' * 40}"] = d
    completo = RM.complete_manifest(_run_manifest(reg), reg)
    office = completo["release_set"]["operator-office"]
    assert office["build_sha"] == "c" * 40
    assert office["release_id"] == ""


def test_tag_imutavel_que_nao_bate_com_a_movel_nao_vira_candidato():
    reg = _alpha_registry()
    reg.tags[f"storefront-{SHA_A}"] = reg.tags["web"]  # adulterada
    completo = RM.complete_manifest(_run_manifest(reg), reg, attempts=1)
    assert "storefront" in completo["release_set_error"]
    assert any("release set incompleto" in e for e in RM.validate(completo))


def test_registry_fora_vira_erro_no_manifesto_e_nao_derruba_o_alpha():
    reg = _alpha_registry()
    reg.fail = True
    completo = RM.complete_manifest(_run_manifest(reg), reg, attempts=1)
    assert completo["release_set_error"]
    assert "release_set" not in completo


def test_build_vermelho_nao_produz_candidato():
    reg = _alpha_registry()
    completo = RM.complete_manifest(_run_manifest(reg, build_result="failure"), reg)
    assert "build_result=failure" in completo["release_set_error"]


# ── gate 3: manifesto ausente, componente faltando, smoke vermelho ───────────


def _manifesto_valido() -> dict:
    reg = _alpha_registry()
    return RM.complete_manifest(_run_manifest(reg), reg)


def test_manifesto_valido_serve():
    assert RM.validate(_manifesto_valido()) == []


@pytest.mark.parametrize(
    "estragar, motivo",
    [
        (lambda m: m["release_set"].pop("operator-floor"), "componentes faltando"),
        (lambda m: m["release_set"]["web"].update(digest="sha256:abc"), "digest ilegível"),
        (lambda m: m["release_set"]["web"].update(immutable_tag="web"), "immutable_tag"),
        (lambda m: m.update(deploy_mode="cancelled"), "não fechou este manifesto"),
        (lambda m: m.pop("deploy_mode"), "não fechou este manifesto"),
        (lambda m: m.update(release_id="20261109-1200-fffffff"), "não é do commit"),
        (lambda m: m.pop("release_set"), "sem release_set"),
        (lambda m: m.update(schema_version=1), "schema_version"),
    ],
)
def test_manifesto_estragado_e_recusado(estragar, motivo):
    m = _manifesto_valido()
    estragar(m)
    assert any(motivo in e for e in RM.validate(m)), RM.validate(m)


def test_manifesto_de_app_ja_em_producao_e_promovivel():
    """Sem alpha, o push com o app nas tags `-prod` só constrói, e é ESSE
    candidato que vai à produção."""
    m = _manifesto_valido()
    m["deploy_mode"] = "production_pinned"
    assert RM.validate(m) == []


def test_cli_validate_falha_fechado_sem_manifesto(tmp_path):
    assert RM.main(["validate", "--manifest", str(tmp_path / "nao-existe.json")]) == 1


def test_workflow_para_sem_manifesto_do_release():
    plan = _workflow("promote-release.yml")["jobs"]["plan"]
    nomes = [s.get("name") for s in plan["steps"]]
    download = plan["steps"][nomes.index("Baixar o manifesto do release")]
    assert "--name release-manifest" in download["run"]
    assert "continue-on-error" not in download


# ── repositório git de verdade para ancestralidade e Release ID ──────────────


def _git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("a")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "a", date="2026-11-01T12:00:00+00:00")
    a = _git(r, "rev-parse", "HEAD")
    (r / "b.txt").write_text("b")
    _git(r, "add", "b.txt")
    _git(r, "commit", "-q", "-m", "b", date="2026-11-09T12:00:00+00:00")
    b = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-q", "-b", "lateral", a)
    (r / "c.txt").write_text("c")
    _git(r, "add", "c.txt")
    _git(r, "commit", "-q", "-m", "c", date="2026-11-09T13:00:00+00:00")
    c = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-q", "main")
    return {"root": r, "a": a, "b": b, "c": c}


def _cenario(repo, *, protegido=True):
    reg = _alpha_registry()
    # As imagens do cenário nascem dos commits reais do repositório de teste.
    a, b = repo["a"], repo["b"]
    reg2 = FakeRegistry()
    for component in COMPONENTS:
        tag = TAGS[component]
        d = reg2.push(tag, f"{component}-{a}", _labels(component, a))
        reg2.tags[f"{tag}-{a}"] = d
    d = reg2.push("web", f"web-{b}", _labels("web", b))
    reg2.tags[f"web-{b}"] = d
    del reg
    manifest = RM.complete_manifest(_run_manifest(reg2, sha=b), reg2)
    manifest["release_id"] = PR.release_id_of(b, repo["root"])
    deploy_run = {"id": 42, "head_sha": b, "updated_at": "2026-11-09T12:10:00Z"}
    respostas = {
        "environments/production": {
            "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}],
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
        } if protegido else None,
    }

    def gh(path):
        gh.paths.append(path)
        for chave, valor in respostas.items():
            if chave in path:
                if valor is None:
                    raise PR.Recusa("HTTP 404")
                return valor
        raise AssertionError(path)

    gh.paths = []
    return reg2, manifest, deploy_run, gh


def _plan(repo, reg, manifest, deploy_run, gh, **kw):
    return PR.build_plan(
        release_id=manifest["release_id"], manifest=manifest, repo="o/r", deploy_run=deploy_run,
        main_ref="main", registry=reg, gh=gh, root=repo["root"], **kw,
    )


def test_release_id_e_recalculado_pelo_commit(repo):
    assert PR.release_id_of(repo["b"], repo["root"]) == f"20261109-1200-{repo['b'][:7]}"
    assert PR.resolve_sha(f"20261109-1200-{repo['b'][:7]}", "main", repo["root"]) == repo["b"]
    with pytest.raises(PR.Recusa, match="não é o Release ID"):
        PR.resolve_sha(f"20261109-1300-{repo['b'][:7]}", "main", repo["root"])


def test_release_fora_do_main_e_recusado(repo):
    with pytest.raises(PR.Recusa, match="não está no main"):
        PR.resolve_sha(PR.release_id_of(repo["c"], repo["root"]), "main", repo["root"])


def test_plano_verde_lista_o_retag_de_cada_componente(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh, require_protection=True)
    assert plan["git_sha"] == repo["b"]
    assert plan["environment_protection_gaps"] == []
    for component in COMPONENTS:
        linha = plan["components"][component]
        assert linha["digest"] == manifest["release_set"][component]["digest"]
        assert linha["production_tag"] == f"{TAGS[component]}-prod"
        assert linha["action"] == "retag"


def test_componente_faltando_para_antes_de_escrever(repo):
    reg, manifest, run, gh = _cenario(repo)
    manifest["release_set"].pop("operator-office")
    with pytest.raises(PR.Recusa, match="componentes faltando"):
        _plan(repo, reg, manifest, run, gh)
    assert reg.puts == []


def test_promocao_sai_do_main_sem_consultar_alpha(repo):
    """O plano não pergunta por smoke de alpha: ele não existe depois do go-live,
    e o smoke que roda contra o app vivo prova o release ANTERIOR, não este."""
    reg, manifest, run, gh = _cenario(repo)
    manifest["deploy_mode"] = "production_pinned"
    plan = _plan(repo, reg, manifest, run, gh, require_protection=True)
    assert "alpha_smoke_run" not in plan
    assert not any("alpha-smoke" in p for p in gh.paths), gh.paths
    assert "alpha_green" not in vars(PR)


def test_componente_de_commit_fora_da_linha_do_release_e_recusado(repo):
    reg, manifest, run, gh = _cenario(repo)
    c = repo["c"]
    entry = manifest["release_set"]["operator-floor"]
    entry.update(build_sha=c, immutable_tag=f"operator-floor-{c}")
    with pytest.raises(PR.Recusa, match="não é ancestral"):
        _plan(repo, reg, manifest, run, gh)


def test_manifesto_de_outro_run_e_recusado(repo):
    reg, manifest, run, gh = _cenario(repo)
    run["id"] = 99
    with pytest.raises(PR.Recusa, match="veio do run"):
        _plan(repo, reg, manifest, run, gh)


def test_candidato_apagado_do_registry_e_recusado(repo):
    reg, manifest, run, gh = _cenario(repo)
    del reg.tags[manifest["release_set"]["storefront-nuxt"]["immutable_tag"]]
    with pytest.raises(PR.Recusa, match="não aponta mais"):
        _plan(repo, reg, manifest, run, gh)


def test_environment_sem_protecao_so_passa_no_dry_run(repo):
    reg, manifest, run, gh = _cenario(repo, protegido=False)
    plan = _plan(repo, reg, manifest, run, gh)
    assert plan["environment_protection_gaps"]
    with pytest.raises(PR.Recusa, match="não existe"):
        _plan(repo, reg, manifest, run, gh, require_protection=True)


# ── gate 1: o digest promovido é o do alpha ──────────────────────────────────


def test_retag_escreve_os_mesmos_bytes_e_o_digest_de_producao_e_o_do_alpha(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh)
    alpha = {c: reg.tags[TAGS[c]] for c in COMPONENTS}
    bytes_alpha = {c: reg.blobs[alpha[c]][0] for c in COMPONENTS}

    PR.retag(plan, reg)

    for component in COMPONENTS:
        prod = reg.tags[f"{TAGS[component]}-prod"]
        assert prod == alpha[component] == manifest["release_set"][component]["digest"]
        assert reg.blobs[prod][0] == bytes_alpha[component]
    assert sorted(reg.puts) == sorted(f"{TAGS[c]}-prod" for c in COMPONENTS)


def test_retag_le_pelo_digest_e_nao_pela_tag_movel_que_o_proximo_push_mexeu(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh)
    reg.push("web", "web-de-um-push-depois")  # o main andou entre o plano e o retag
    PR.retag(plan, reg)
    assert reg.tags["web-prod"] == manifest["release_set"]["web"]["digest"]


def test_retag_e_idempotente(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh)
    PR.retag(plan, reg)
    reg.puts.clear()
    assert all("já aponta" in linha for linha in PR.retag(plan, reg))
    assert reg.puts == []


def test_retag_recusa_quando_a_tag_relida_nao_e_o_digest(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh)
    original = reg.put_manifest

    def put_que_converte(tag, manifest):
        original(tag, manifest)
        reg.tags[tag] = reg.push("x", "registry-que-converteu")
        return reg.tags[tag]

    reg.put_manifest = put_que_converte
    with pytest.raises(PR.Recusa, match="ficou em"):
        PR.retag(plan, reg)


def test_bytes_que_nao_batem_com_o_digest_nunca_sao_escritos():
    body = _manifest_bytes("x")
    with pytest.raises(RM.RegistryError, match="bytes do manifest"):
        RM.check_manifest(body + b" ", MEDIA, _digest(body))


def test_indice_de_attestation_nao_e_promovivel():
    body = _manifest_bytes("x")
    with pytest.raises(RM.RegistryError, match="não manifest de imagem"):
        RM.check_manifest(body, "application/vnd.oci.image.index.v1+json", _digest(body))


def test_no_ar_tem_de_estar_o_commit_promovido(repo):
    reg, manifest, run, gh = _cenario(repo)
    plan = _plan(repo, reg, manifest, run, gh)
    certo = {c: {"component": c, "build_sha": plan["components"][c]["build_sha"]} for c in COMPONENTS}
    assert PR.identity_mismatches(plan, certo) == []
    errado = {**certo, "web": {"component": "web", "build_sha": repo["a"]}}
    assert any("web: no ar" in e for e in PR.identity_mismatches(plan, errado))
    sem_url = {c: v for c, v in certo.items() if c != "operator-office"}
    assert any("sem endereço" in e for e in PR.identity_mismatches(plan, sem_url))

    def get(url):
        component = url.split("//")[1].split(".")[0]
        return 200, json.dumps(errado[component]).encode()

    urls = {c: f"https://{c}.x/health/release" for c in COMPONENTS}
    with pytest.raises(PR.Recusa, match="não é o que foi promovido"):
        PR.verify(plan, urls, attempts=1, interval=0, get=get)


# ── gate 3 (continuação): smoke vermelho para ────────────────────────────────

MENU = json.dumps({"catalog": {"items": [
    {"sku": f"S{i}", "availability": "available", "can_add_to_cart": True} for i in range(40)
]}}).encode()
CHECKOUT_403 = (403, json.dumps({"error_code": "authentication_required"}).encode())


def _get(ready=200, home=b"<html>Nelson" + b"x" * 30000):
    def get(url):
        if url.endswith("/ready/"):
            return ready, b""
        if "/menu/" in url:
            return 200, MENU
        return 200, home
    return get


def test_smoke_verde_passa():
    PR.smoke("https://api.x", "https://www.x", get=_get(), post=lambda url: CHECKOUT_403)


@pytest.mark.parametrize(
    "get, post, motivo",
    [
        (_get(ready=503), lambda url: CHECKOUT_403, "/ready/ respondeu 503"),
        (_get(), lambda url: (500, b""), "checkout anônimo"),
        (_get(home=b"<html></html>"), lambda url: CHECKOUT_403, "não renderizou"),
    ],
)
def test_smoke_vermelho_para_a_promocao(get, post, motivo):
    with pytest.raises(PR.Recusa, match=motivo):
        PR.smoke("https://api.x", "https://www.x", get=get, post=post)


def test_smoke_vermelho_fecha_o_deployment_como_falha():
    promote = _workflow("promote-release.yml")["jobs"]["promote"]
    fechar = next(s for s in promote["steps"] if s.get("name") == "Fechar o GitHub Deployment")
    assert fechar["if"].startswith("always()")
    assert "estado=failure" in fechar["run"]
    smoke = next(s for s in promote["steps"] if s.get("name") == "Smoke de produção")
    assert "continue-on-error" not in smoke


# ── a ordem do contrato ──────────────────────────────────────────────────────


def test_a_ordem_do_workflow_e_a_do_contrato():
    wf = _workflow("promote-release.yml")
    assert wf["jobs"]["promote"]["needs"] == "plan"
    nomes = [s.get("name") for s in wf["jobs"]["promote"]["steps"]]
    ordem = [
        "O app de produção está nas tags -prod",
        "Retag dos mesmos manifests para produção",
        "Registrar o GitHub Deployment",
        "Deployment na produção (espera ACTIVE)",
        "O que está no ar é o que foi promovido",
        "Smoke de produção",
    ]
    assert [nomes.index(n) for n in ordem] == sorted(nomes.index(n) for n in ordem)
    plan_runs = " ".join(s.get("run") or "" for s in wf["jobs"]["plan"]["steps"])
    assert "promote_release.py locate" in plan_runs and "promote_release.py plan" in plan_runs
    assert "retag" not in plan_runs  # o plano não escreve


def test_teto_do_job_cabe_a_espera_a_prova_e_o_smoke():
    promote = _workflow("promote-release.yml")["jobs"]["promote"]
    espera = int(promote["env"]["DEPLOY_WAIT_MAX_SECONDS"])
    assert promote["timeout-minutes"] * 60 >= espera + 10 * 30 + 300


# ── gate 2: rebuild impossível ───────────────────────────────────────────────


def test_promocao_nao_tem_passo_de_build():
    wf = _workflow("promote-release.yml")
    proibido = ("docker", "buildx", "build-push", "setup-qemu", "kaniko", "buildah", "podman")
    for job_name, job in wf["jobs"].items():
        for step in job["steps"]:
            uses = (step.get("uses") or "").lower()
            run = (step.get("run") or "").lower()
            for palavra in proibido:
                assert palavra not in uses, f"{job_name}: {step.get('name')} usa {uses}"
                assert palavra not in run, f"{job_name}: {step.get('name')} roda {palavra}"


def test_o_job_que_escreve_nao_recebe_dockerfile_nem_codigo_do_app():
    promote = _workflow("promote-release.yml")["jobs"]["promote"]
    checkout = next(s for s in promote["steps"] if (s.get("uses") or "").startswith("actions/checkout"))
    caminhos = checkout["with"]["sparse-checkout"].split()
    assert checkout["with"]["sparse-checkout-cone-mode"] is False
    assert all(not Path(c).name.startswith("Dockerfile") for c in caminhos)
    assert all(c.startswith("scripts/") or c.startswith("surfaces/") and c.endswith(".json") for c in caminhos)
    for step in promote["steps"]:
        run = step.get("run") or ""
        for linha in run.splitlines():
            if "python3 " in linha:
                assert "scripts/promote_release.py" in linha, linha


def test_cliente_de_registry_nao_tem_caminho_de_upload_de_camada():
    fonte = (ROOT / "scripts" / "release_manifest.py").read_text(encoding="utf-8")
    assert "blobs/uploads" not in fonte
    assert "POST" not in fonte.split("class Registry", 1)[1].split("def check_manifest", 1)[0]
    metodos = {m for m in vars(RM.Registry) if not m.startswith("__")}
    assert not {m for m in metodos if "upload" in m or "blob" in m and "get" not in m}
    assert set(dir(PR)) & {"build", "docker_build"} == set()


def test_cliente_de_leitura_nao_escreve():
    reg = RM.Registry("token-falso")
    manifest = RM.Manifest(b"{}", MEDIA, _digest(b"{}"))
    with pytest.raises(RM.RegistryError, match="só para leitura"):
        reg.put_manifest("web-prod", manifest)


# ── gate 4: push no main não altera produção ─────────────────────────────────


def test_promocao_so_nasce_de_dispatch_manual_no_main_com_environment():
    wf = _workflow("promote-release.yml")
    assert set(wf["on"]) == {"workflow_dispatch"}
    assert wf["permissions"] == {}
    assert wf["jobs"]["promote"]["environment"]["name"] == "production"
    for job in wf["jobs"].values():
        assert "github.ref == 'refs/heads/main'" in job["if"]
    assert wf["on"]["workflow_dispatch"]["inputs"]["mode"]["default"] == "dry-run"


def test_deploy_images_nunca_escreve_tag_de_producao():
    wf = _workflow("deploy-images.yml")
    tags = wf["jobs"]["build-push"]["steps"]
    build = next(s for s in tags if s.get("id") == "build")
    for tag in build["with"]["tags"].split():
        assert not tag.endswith(RM.PRODUCTION_SUFFIX)
        assert RM.PRODUCTION_SUFFIX not in tag
    texto = json.dumps(wf)
    assert "put_manifest" not in texto and "promote_release" not in texto


def test_deploy_images_nao_implanta_app_que_esta_nas_tags_de_producao():
    wf = _workflow("deploy-images.yml")
    passo = next(s for s in wf["jobs"]["manifest"]["steps"] if s.get("name") == "Um deployment para o run inteiro")
    run = passo["run"]
    assert run.index('papel.role == "production"') < run.index('"POST", f"/apps/{app_id}/deployments"')
    assert 'gravar(deploy_mode="production_pinned")' in run


def _spec(tag_suffix: str = "", deploy_on_push: bool = False, extra: dict | None = None) -> dict:
    def img(tag):
        return {"registry_type": "DOCR", "repository": "shopman", "tag": f"{tag}{tag_suffix}",
                "deploy_on_push": {"enabled": deploy_on_push}}
    spec = {
        "services": [
            {"name": "web-operator", "image": img("web")},
            {"name": "storefront-nuxt", "image": img("storefront")},
            {"name": "operator-floor", "image": img("operator-floor")},
            {"name": "operator-office", "image": img("operator-office")},
        ],
        "workers": [{"name": "directive-worker", "image": img("web")}],
        "jobs": [{"name": "release", "image": img("web")}],
    }
    for kind, comps in (extra or {}).items():
        spec[kind].extend(comps)
    return spec


def test_papel_do_app_pelas_tags():
    assert RM.app_role(_spec()).role == "alpha"
    assert RM.app_role(_spec("-prod")).role == "production"
    misturado = _spec("-prod", extra={"workers": [{"name": "x", "image": {"repository": "shopman", "tag": "web"}}]})
    assert RM.app_role(misturado).role == "mixed"
    fixado = _spec(extra={"workers": [{"name": "x", "image": {"repository": "shopman", "tag": f"web-{SHA_A}"}}]})
    assert RM.app_role(fixado).role == "mixed"


def test_spec_versionado_do_app_vivo_e_alpha_hoje():
    """Enquanto a proposta de spec do runbook não for aplicada, o app vivo
    segue nas tags móveis: o push implanta nele, como sempre."""
    spec = yaml.safe_load((ROOT / ".do" / "app.alpha-subdomains.yaml").read_text(encoding="utf-8"))
    assert RM.app_role(spec).role == "alpha"


def test_producao_so_aceita_app_nas_tags_prod_e_sem_deploy_on_push():
    apps = [{"id": "p", "spec": {"name": "prod", **_spec("-prod")}}]
    assert PR.check_app(apps, "prod") == "p"
    with pytest.raises(PR.Recusa, match="deploy_on_push"):
        PR.check_app([{"id": "p", "spec": {"name": "prod", **_spec("-prod", deploy_on_push=True)}}], "prod")
    with pytest.raises(PR.Recusa, match="papel: alpha"):
        PR.check_app([{"id": "p", "spec": {"name": "prod", **_spec()}}], "prod")
    with pytest.raises(PR.Recusa, match="não existe"):
        PR.check_app(apps, "outro")


def test_tags_de_producao_derivam_das_moveis():
    assert {RM.production_tag(t) for t in TAGS.values()} == {
        "web-prod", "storefront-prod", "operator-floor-prod", "operator-office-prod"
    }
