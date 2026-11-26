#!/usr/bin/env python3
"""CI local-first: o que a CI vai reprovar, visto ANTES do push.

Plano DEV-2026-098 (docs/plans/CI-DX-LOCAL-FIRST-PLAN.md). Quatro níveis, a
mesma classificação de escopo da CI (``scripts/ci_scope.py``) e os mesmos
comandos dos workflows, lidos do YAML, sem lista copiada:

``fast``       a cada edição: origem dos imports, ruff nos arquivos tocados,
               colisão de número de migração, os testes do que mudou e o unit
               dos apps Nuxt tocados.
``impact``     paridade com o PR: tudo o que o ``pull_request`` roda para este
               diff (jobs "Quality + deploy contract", "Gate da meia-correção",
               "Versões das superfícies", "Contrato canônico", Admin/Unfold,
               ``test-cores``/``test-storefront``/``test-counter-agent`` e o leve
               de cada app tocado).
``preflight``  antes de promover o PR: ``impact`` + o pesado da fila que este
               diff alcança (shop/backstage por domínio, as fases de navegador
               dos apps tocados, os testes que leem o repositório inteiro ou a
               documentação). Diff só de ferramenta de CI (``QUEUE_NEUTRAL``)
               não paga as suítes da fila, que não mudam de resultado com ele:
               prova só que a invocação resolve (``make -n``) e deixa a fila
               rodá-las. Grava a evidência que ``ready`` exige.
``full``       ``make ci-local``: tudo o que é executável nesta máquina, como
               se o diff fosse de infraestrutura.

Vagas da máquina: ``preflight``/``full`` disputam as vagas ``cpu`` (2 nesta
máquina); ``fast``/``impact`` têm a vaga ``quick`` própria, com metade dos
workers, para a iteração não esperar atrás de um passo de 17 min. A evidência
separa a espera por vaga (``wait_seconds``) da execução (``seconds``).

O que só a CI executa (retrato de pixel preso ao navegador da CI, PostgreSQL +
Redis reais, imagem Docker, E2E da loja, Browser QA, cobertura agregada) sai
listado como ``remoto`` — nunca como verde.

Garantias que a CI não pode dar e esta ferramenta dá:

* **origem dos imports** — numa worktree, a ``.venv`` da raiz resolve
  ``shopman.*`` para a árvore principal; o executor põe a worktree no
  ``PYTHONPATH`` e reprova se qualquer pacote vier de fora dela;
* **isolamento** — ``DATABASE_URL``/``REDIS_URL`` vazios (SQLite em memória por
  worker, como no job de testes da CI); portas e navegador sob trava global;
* **CPU** — trava de máquina (``flock``) com N vagas e ``-n`` por vaga, para
  duas worktrees não brigarem por 8 núcleos;
* **evidência pelo conteúdo** — a chave é o hash da ÁRVORE testada (inclui o
  que ainda não foi commitado). Depois do commit, ``HEAD^{tree}`` bate com ela;
  qualquer byte a mais invalida.

    python3 scripts/local_ci.py plan
    python3 scripts/local_ci.py run fast|impact|preflight|full
    python3 scripts/local_ci.py ready <PR> [--sem-preflight "motivo"]
    python3 scripts/local_ci.py evidence <commit|tree>
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_SLUG = "nelsonboulangerie/django-shopman"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from ci_scope import classify, is_doc  # noqa: E402  (a MESMA classificação da CI)

LEVELS = ("fast", "impact", "preflight", "full")
#: Níveis que contam como evidência para promover o PR.
PROMOTABLE = {"preflight", "full"}
QUICK_LEVELS = {"fast", "impact"}  # vaga própria ("quick"), fora da disputa do preflight


# ── Ambiente ──────────────────────────────────────────────────────────────


def git(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel"))


def main_root(root: Path) -> Path:
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root))
    return common.parent


def venv_python(root: Path) -> Path:
    for candidate in (root / ".venv/bin/python", main_root(root) / ".venv/bin/python"):
        if candidate.exists():
            return candidate
    raise SystemExit("Sem .venv nesta worktree nem na raiz: rode `make install` no checkout principal.")


def package_paths(root: Path) -> list[Path]:
    return sorted(p for p in (root / "packages").iterdir() if (p / "pyproject.toml").exists())


def state_dir() -> Path:
    base = Path(os.environ.get("SHOPMAN_LOCAL_CI_HOME") or Path.home() / "Library/Caches/shopman-local-ci")
    (base / "evidence").mkdir(parents=True, exist_ok=True)
    (base / "locks").mkdir(parents=True, exist_ok=True)
    return base


def machine_budget() -> tuple[int, int]:
    """(vagas, workers por vaga). 8 núcleos e 8 GB → 2 vagas de 4."""
    cpus = os.cpu_count() or 4
    try:
        mem_gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) // 2**30
    except ValueError:
        mem_gb = 8
    slots = int(os.environ.get("SHOPMAN_LOCAL_CI_SLOTS") or max(1, min(cpus // 4, mem_gb // 4)))
    workers = int(os.environ.get("SHOPMAN_LOCAL_CI_WORKERS") or max(1, cpus // slots))
    return slots, workers


@contextlib.contextmanager
def machine_slot(kind: str, slots: int):
    """Vaga de máquina compartilhada por TODAS as worktrees (``flock``)."""
    if kind == "none":
        yield {"seconds": 0.0}
        return
    locks = state_dir() / "locks"
    count = slots if kind == "cpu" else 1
    handles = [open(locks / f"{kind}-{i}.lock", "w") for i in range(count)]
    wait = {"seconds": 0.0}
    try:
        waited = time.monotonic()
        announced = False
        while True:
            for handle in handles:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                wait["seconds"] = round(time.monotonic() - waited, 1)
                if announced:
                    print(f"   vaga {kind} liberada após {wait['seconds']:.0f}s", flush=True)
                handle.write(f"{os.getpid()} {repo_root()}\n")
                handle.flush()
                try:
                    yield wait
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                return
            if not announced:
                print(f"   ⏳ esperando vaga {kind} (outras worktrees usando a máquina)", flush=True)
                announced = True
            time.sleep(2)
    finally:
        for handle in handles:
            handle.close()


# ── O que mudou ───────────────────────────────────────────────────────────


@dataclass
class Diff:
    base_ref: str
    merge_base: str
    files: list[str]
    deleted: list[str]
    tree: str


def working_tree_hash(root: Path) -> str:
    """Hash da árvore como ela está no disco (tracked + não ignorados).

    Índice temporário: não toca o índice, o stash nem refs de ninguém.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git("read-tree", "HEAD", cwd=root, env=env)
        git("add", "-A", ".", cwd=root, env=env)
        return git("write-tree", cwd=root, env=env)


def compute_diff(root: Path, base_ref: str) -> Diff:
    merge_base = git("merge-base", "HEAD", base_ref, cwd=root)
    files: set[str] = set()
    deleted: set[str] = set()
    # Contra a base comum, incluindo o que ainda não foi commitado.
    for line in git("diff", "--name-status", "-M", merge_base, cwd=root).splitlines():
        status, *paths = line.split("\t")
        files.update(paths)  # renomeação: os DOIS lados
        if status.startswith("D"):
            deleted.update(paths)
        if status.startswith("R"):
            deleted.add(paths[0])
    files.update(git("ls-files", "--others", "--exclude-standard", cwd=root).splitlines())
    return Diff(base_ref, merge_base, sorted(f for f in files if f), sorted(deleted), working_tree_hash(root))


# ── Passos ────────────────────────────────────────────────────────────────


@dataclass
class Step:
    name: str
    cmd: str
    cwd: str = "."
    slot: str = "none"  # none | cpu | browser
    env: dict = field(default_factory=dict)
    origin: str = ""  # de onde veio (workflow/job ou regra local)


@dataclass
class Plan:
    level: str
    scope: dict
    steps: list[Step]
    remote: list[str]
    notes: list[str]


def load_workflow(root: Path, name: str) -> dict:
    import yaml  # só existe na .venv; o executor roda nela (ver main)

    return yaml.safe_load((root / ".github/workflows" / name).read_text())


SKIP_STEP_NAMES = {"Create virtualenv", "Install dependencies"}


def mirror_job(root: Path, py: Path, workflow: str, job_id: str, remote: list[str]) -> list[Step]:
    """Os passos ``run:`` do job, como a CI os escreve, adaptados à máquina.

    Adaptação mínima e declarada: ``.venv/bin/`` e ``python`` viram a .venv
    canônica; ``make`` recebe ``PYTHON=``; ``pip install`` some (a .venv já
    tem); ``$GITHUB_STEP_SUMMARY`` vai para /dev/null. Passo com ``if:`` de
    evento ou expressão ``${{ }}`` não é imitável aqui e sai como remoto.
    """
    doc = load_workflow(root, workflow)
    job = doc["jobs"][job_id]
    job_name = job.get("name", job_id)
    # Como o Actions: workflow → job → passo, o mais interno vence.
    inherited = {k: str(v) for k, v in {**(doc.get("env") or {}), **(job.get("env") or {})}.items()}
    inherited = {k: v for k, v in inherited.items() if "${{" not in v}
    venv_bin = py.parent
    steps: list[Step] = []
    for raw in job.get("steps", []):
        run = raw.get("run")
        name = raw.get("name") or (run.splitlines()[0][:60] if run else raw.get("uses", "?"))
        if not run or name in SKIP_STEP_NAMES:
            continue
        env = {**inherited, **{k: str(v) for k, v in (raw.get("env") or {}).items()}}
        cond = str(raw.get("if", ""))
        if "${{" in run or any("${{" in v for v in env.values()) or (cond and "always()" not in cond):
            remote.append(f"{job_name} › {name} (depende do evento/contexto da CI)")
            continue
        if any(v.startswith(("postgres://", "redis://")) for v in env.values()):
            remote.append(f"{job_name} › {name} (PostgreSQL/Redis reais)")
            continue
        lines = []
        for line in run.splitlines():
            if re.search(r"\bpip install\b", line):
                continue
            # `fetch --depth` numa clonagem COMPLETA a deixa rasa — e o .git é
            # o mesmo de todas as worktrees. Busca inteira, que é inofensiva.
            line = re.sub(r"\s--depth[= ]\d+", "", line)
            line = line.replace(".venv/bin/", f"{venv_bin}/")
            line = re.sub(r"(^|\s|&&\s*)python3?\s", lambda m: f"{m.group(1)}{py} ", line)
            line = re.sub(r"(^|\s)make\s", lambda m: f"{m.group(1)}make PYTHON={py} ", line)
            lines.append(line)
        cmd = "set -eo pipefail\n" + "\n".join(lines)
        slot = "cpu" if "pytest" in cmd or "make " in cmd else "none"
        steps.append(Step(f"{job_name} › {name}", cmd, slot=slot, env=env, origin=f"{workflow}#{job_id}"))
    return steps


def surface_matrix(root: Path, heavy: bool, surfaces: str) -> list[dict]:
    env = {**os.environ, "CI_HEAVY": "true" if heavy else "false", "CI_SURFACES": surfaces}
    out = subprocess.run(
        ["node", "scripts/surface_contract.mjs", "matrix", "quality"],
        cwd=root, env=env, check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)["include"]


LIGHT_PHASES = ("unit", "component", "lint", "typecheck")
BROWSER_PHASES = ("geometry", "browser", "a11y", "security", "browserSuite")


def surface_steps(
    root: Path, entries: list[dict], phases: tuple[str, ...], remote: list[str],
    touched: set[str], install: bool,
) -> list[Step]:
    """Fases do contrato para cada app da matriz.

    App que o diff TOCOU e não tem ``node_modules`` ganha ``npm ci`` (como na
    CI); app que só entrou por escopo incerto (diff de infraestrutura) e não
    tem dependências instaladas fica para a CI, declarado. ``install=True``
    (``full``) instala todos.
    """
    steps: list[Step] = []
    skipped: list[str] = []
    installed: set[str] = set()

    def npm_ci(directory: str) -> None:
        if directory in installed or (root / "surfaces" / directory / "node_modules").exists():
            return
        installed.add(directory)
        steps.append(Step(f"{directory} › npm ci", "npm ci --no-audit --no-fund", cwd=f"surfaces/{directory}", slot="cpu", origin="surfaces-gate.yml#quality"))

    for e in entries:
        if e.get("skip"):
            continue
        app_dir = root / "surfaces" / e["dir"]
        if not (app_dir / "node_modules").exists() and e["dir"] not in installed:
            if not (install or e["dir"] in touched):
                skipped.append(e["dir"])
                continue
            if e.get("install_layer") and e["dir"] != "operator-kit":
                npm_ci("operator-kit")
            npm_ci(e["dir"])
        concurrent = (e.get("concurrent") or "").split()
        together = [p for p in phases if p in concurrent]
        if len(together) >= 2:
            # Como a fila (concurrentPhases no contracts.json): juntas, num passo só.
            steps.append(Step(
                f"{e['dir']} › {' + '.join(together)} (juntas)",
                f"node ../../scripts/surface_contract.mjs run-many {shlex.quote(e['id'])} {' '.join(together)}",
                cwd=f"surfaces/{e['dir']}", slot="browser", origin="surfaces-gate.yml#quality (concurrentPhases)",
            ))
        for phase in phases:
            if len(together) >= 2 and phase in together:
                continue
            enabled = {
                "unit": True, "lint": True, "typecheck": True,
                "component": e.get("component"),
                "geometry": e.get("geometry"),
                "browser": e.get("browser") and not e.get("browser_suite"),
                "a11y": e.get("a11y") and not e.get("browser_suite"),
                "security": e.get("security"),
                "browserSuite": e.get("browser_suite"),
            }[phase]
            if not enabled:
                continue
            slot = "browser" if phase in BROWSER_PHASES else "cpu"
            steps.append(Step(
                f"{e['dir']} › {phase}",
                f"node ../../scripts/surface_contract.mjs run {shlex.quote(e['id'])} {phase}",
                cwd=f"surfaces/{e['dir']}", slot=slot, origin="surfaces-gate.yml#quality",
            ))
        if e.get("visual"):
            remote.append(f"{e['dir']} › visual (retrato só vale no navegador da CI)")
    if skipped:
        remote.append(f"superfícies sem node_modules nesta worktree, fora do diff: {', '.join(skipped)}")
    return steps


def tests_reading(root: Path, pattern: str) -> list[str]:
    """Arquivos de teste do framework que casam ``pattern`` (lê o repo/docs)."""
    hits = subprocess.run(
        ["git", "grep", "-l", "-E", pattern, "--", "shopman/*/tests/*.py", "shopman/*/tests/**/*.py"],
        cwd=root, capture_output=True, text=True,
    ).stdout.split()
    return sorted(h for h in hits if Path(h).name.startswith("test_"))


def focused_tests(root: Path, files: list[str]) -> dict[str, list[str]]:
    """Testes do que mudou. Devolve {diretório de execução: [alvos]}.

    * pacote do Core (``packages/<pkg>``): a suíte INTEIRA do pacote, rodada de
      dentro dele (cada um tem settings próprio). É barata (a de ``utils`` leva
      menos de 1 s) e o nome não diz quem testa o quê: medido em 25/11, quebrar
      ``utils.monetary.format_money`` só reprova em ``test_money_field.py``;
    * ``shopman/``, ``tools/``, ``config/``: o próprio arquivo de teste, os
      ``test_<módulo>*`` do app e os testes que importam o módulo pelo nome
      pontilhado;
    * ``scripts/``: ``scripts/tests/test_<script>*``.
    """
    out: dict[str, set[str]] = {}
    for path in files:
        p = Path(path)
        if p.suffix != ".py" or not (root / p).exists():
            continue
        if p.parts[0] == "packages" and len(p.parts) > 2:
            out.setdefault(f"packages/{p.parts[1]}", set()).add(".")
            continue
        if p.parts[0] not in ("shopman", "tools", "config", "scripts"):
            continue
        if p.name.startswith("test_"):
            out.setdefault(".", set()).add(str(p))
            continue
        if p.name in ("__init__.py", "apps.py", "conftest.py") or "migrations" in p.parts:
            continue
        if p.parts[0] == "scripts":
            top = root / "scripts" / "tests"
        elif p.parts[0] == "shopman" and len(p.parts) > 2:
            top = root / "shopman" / p.parts[1]
        else:
            top = root / p.parts[0]
        hits = {str(t.relative_to(root)) for t in top.rglob(f"test_{p.stem}*.py")}
        if p.parts[0] == "shopman":
            dotted = ".".join(p.with_suffix("").parts)
            grep = subprocess.run(
                ["git", "grep", "-l", "-F", dotted, "--", "shopman/*test_*.py"],
                cwd=root, capture_output=True, text=True,
            ).stdout.split()
            hits.update(g for g in grep if (root / g).exists())
        out.setdefault(".", set()).update(hits)
    return {k: sorted(v) for k, v in out.items() if v}


#: O que não muda o resultado das suítes Python da fila (backstage, shop): workflow,
#: scripts de CI, Makefile, registro/contratos das superfícies, deploy e documentação.
#: O PR trata isso como alcance desconhecido e roda todo o leve; o preflight não
#: precisa pagar ~26 min das suítes da fila por isso (medido 26/11, #3635).
QUEUE_NEUTRAL = (".github/", "scripts/", "surfaces/", ".do/", ".claude/", ".codex/", "Dockerfile", "Makefile")


def queue_neutral(path: str) -> bool:
    return is_doc(path) or path.startswith(QUEUE_NEUTRAL)


def queue_domains(level: str, files: list[str]) -> set[str]:
    """Quais suítes da fila o diff alcança. Arquivo desconhecido liga as duas."""
    if level == "full":
        return {"shop", "backstage"}
    domains: set[str] = set()
    for f in files:
        if f.startswith("shopman/backstage/"):
            domains.add("backstage")
        elif f.startswith(("shopman/storefront/", "tools/")) or queue_neutral(f):
            continue  # storefront tem suíte própria no PR; o neutro não muda o resultado
        else:  # shop, packages, config, locale, manage.py, constraints, pyproject, conftest…
            domains.update({"shop", "backstage"})
    return domains


def build_plan(root: Path, py: Path, level: str, diff: Diff, workers: int) -> Plan:
    files = diff.files
    pr = classify("pull_request", files)
    full = level == "full" or pr["full"] == "true"
    python = full or pr["python"] == "true"
    code = full or pr["code"] == "true"
    surfaces = "all" if full else pr["surfaces"]
    steps: list[Step] = []
    remote: list[str] = []
    notes: list[str] = []
    q = shlex.quote
    touched = {f.split("/")[1] for f in files if f.startswith("surfaces/") and f.count("/") > 1}
    if touched:
        touched.add("operator-kit")  # os guardrails do kit leem os apps irmãos (ci_scope)

    steps.append(Step("pinos da .venv = constraints.txt", f"{q(str(py))} {q(str(SCRIPTS / 'local_ci.py'))} pins", origin="Makefile#install"))
    steps.append(Step("origem dos imports", f"{q(str(py))} {q(str(SCRIPTS / 'local_ci.py'))} origin", origin="local"))
    steps.append(Step("colisão de número de migração", f"{q(str(py))} {q(str(SCRIPTS / 'local_ci.py'))} migrations", origin="CLAUDE.md"))

    if level == "fast":
        py_files = [f for f in files if f.endswith(".py") and (root / f).exists()]
        if py_files:
            steps.append(Step("ruff (arquivos tocados)", f"{q(str(py.parent / 'ruff'))} check " + " ".join(map(q, py_files)), origin="runtime-gate.yml#quality"))
        for cwd, targets in focused_tests(root, files).items():
            pytest = f"{q(str(py))} -m pytest -q -p no:cacheprovider"
            scripts_only = [t for t in targets if t.startswith("scripts/")]
            others = [t for t in targets if not t.startswith("scripts/")]
            if scripts_only:
                steps.append(Step(
                    "testes do que mudou (scripts)",
                    f"PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 {pytest} -p no:django -W ignore::pytest.PytestConfigWarning " + " ".join(map(q, scripts_only)),
                    slot="cpu", origin="local",
                ))
            if others:
                xdist = " -n auto" if cwd == "." and len(others) > 3 else ""
                steps.append(Step(f"testes do que mudou ({cwd})", f"{pytest}{xdist} " + " ".join(map(q, others)), cwd=cwd, slot="cpu", origin="local"))
        if any(f.endswith(".md") for f in files):
            # Plano novo sem índice, link morto, ADR fora do padrão: reprovam no
            # `quality` e custam segundos aqui (25/11: o plano desta frente).
            steps.append(Step(
                "governança documental (ADR, links, índice de planos)",
                f"{q(str(py))} scripts/check_adr_governance.py && {q(str(py))} scripts/check_docs_governance.py",
                origin="runtime-gate.yml#quality",
            ))
        if touched:
            entries = surface_matrix(root, heavy=False, surfaces=json.dumps(sorted(touched)))
            steps += surface_steps(root, entries, ("unit",), remote, touched, install=False)
        if not files:
            notes.append("nenhuma mudança contra a base: nada focado para rodar")
        return Plan(level, pr, steps, remote, notes)

    # ── impact: paridade com o pull_request ──────────────────────────────
    steps += mirror_job(root, py, "runtime-gate.yml", "quality", remote)
    steps += mirror_job(root, py, "runtime-gate.yml", "silent-swallow-gate", remote)
    steps.append(Step("Contrato canônico das superfícies › validar", "node scripts/surface_contract.mjs validate", origin="surfaces-gate.yml#surface-contract"))
    steps += mirror_job(root, py, "surfaces-gate.yml", "surface-versions", remote)
    remote.append("Ficou de fora declarado / Compromissos (corpo do PR): conferidos no `make ready`")
    if python:
        steps += mirror_job(root, py, "runtime-gate.yml", "admin-gate", remote)
        for suite in ("test-cores", "test-storefront", "test-counter-agent"):
            steps.append(Step(f"Testes ({suite})", f"make PYTHON={q(str(py))} {suite}", slot="cpu", origin="runtime-gate.yml#tests"))
    if code:
        remote.append("Production Contract, Security Gate (CodeQL): rodam na CI")
    if surfaces != "[]":
        entries = surface_matrix(root, heavy=False, surfaces=surfaces)
        steps += surface_steps(root, entries, LIGHT_PHASES, remote, touched, install=level == "full")

    if level == "impact":
        steps += surface_readers_step(root, py, steps)
        return Plan(level, pr, steps, remote, notes)

    # ── preflight/full: o pesado da fila que este diff alcança ──────────
    domains = queue_domains(level, files)
    for d in sorted(domains):
        steps.append(Step(f"Testes (test-{d}) — fila", f"make PYTHON={q(str(py))} test-{d}", slot="cpu", origin="runtime-gate.yml#tests-*-shards"))
    if full and level != "full" and domains != {"shop", "backstage"}:
        # Diff de ferramenta de CI: o PR roda todo o leve (escopo desconhecido), mas as
        # suítes da fila não mudam de resultado; a fila as roda de qualquer forma. Aqui
        # fica só a prova de que a invocação delas ainda resolve.
        skipped = sorted({"shop", "backstage"} - domains)
        steps.append(Step(
            "invocação das suítes da fila (make -n)",
            "make -n " + " ".join(f"test-{d}" for d in skipped) + " >/dev/null",
            origin="local: diff de ferramenta de CI",
        ))
        notes.append(
            "suítes da fila " + ", ".join(f"test-{d}" for d in skipped) + " ficam para a fila: o diff só "
            "toca ferramenta de CI (" + ", ".join(sorted({f for f in files if queue_neutral(f)})[:4]) + "…)"
        )
    covered = {f"shopman/{d}/" for d in domains} | {"shopman/storefront/"} if python else {f"shopman/{d}/" for d in domains}
    readers: list[str] = []
    if code:
        readers += tests_reading(root, r"rglob\(|os\.walk\(|git ls-files")
    if any(is_doc(f) for f in files):
        readers += tests_reading(root, r"docs/")
    readers = sorted({r for r in readers if not r.startswith(tuple(covered))})
    if readers:
        steps.append(Step(
            "testes que leem o repositório/documentação",
            f"{q(str(py))} -m pytest -q -n auto " + " ".join(map(q, readers)),
            slot="cpu", origin="ci-escopo.md › teste que lê documentação",
        ))
    if surfaces != "[]":
        entries = surface_matrix(root, heavy=True, surfaces=surfaces)
        steps += surface_steps(root, entries, BROWSER_PHASES, remote, touched, install=level == "full")
    steps += surface_readers_step(root, py, steps)
    if python:
        remote += [
            "PostgreSQL + Redis runtime stress gate (`make up` + `make test-runtime` reproduz)",
            "Docker deploy image",
            "Browser QA / Storefront E2E (`make storefront-e2e` reproduz, pesado)",
            "Coverage Gate (agrega seis artefatos de cobertura da CI)",
        ]
    remote.append("PWA e Supply chain das superfícies: rodam na fila")
    return Plan(level, pr, steps, remote, notes)


# ── Evidência por passo ───────────────────────────────────────────────────
# Um re-preflight depois de consertar UM app não precisa refazer o que não mudou
# (#3635, 26/11). Cada passo caro tem uma chave: o comando, o ambiente dele e o
# hash das ENTRADAS que ele lê, tirado da árvore exata da rodada (o write-tree que
# já inclui o que não foi commitado). Passo verde com a mesma chave é reaproveitado.
#
# Entradas, medidas e não supostas:
# - passo de superfície: a pasta do app, o operator-kit, os arquivos da raiz de
#   surfaces/, o surface_contract.mjs e o major do Node (o kit lê os irmãos: surfaces/ inteiro);
# - suíte Python ("Testes (test-*)"): a árvore SEM surfaces/, mais o que o código de
#   produção lê de lá (PY_SURFACE_READERS: contratos gerados, registry, documentos
#   legais). Os 32 testes que leem surfaces/ por caminho (~135 s de CPU) viram o
#   passo SURFACE_READERS, que roda sempre que alguma suíte foi reaproveitada;
# - qualquer outro passo caro: a árvore inteira (reaproveita só re-rodada idêntica).
# Passo barato (slot "none") e `npm ci` (estado de disco, não de árvore) sempre rodam.

SURFACE_READERS = "testes Python que leem as superfícies"
#: Como um arquivo Python lê ``surfaces/`` (caminho entre aspas): o mesmo padrão acha
#: os testes do passo SURFACE_READERS e o código de produção que a chave cobre.
SURFACE_PATH_RE = r"""["']surfaces["'/]"""
#: Código de produção que lê surfaces/, e o que ele lê (entra na chave das suítes
#: Python). O teste ``test_leitores_de_surfaces_em_producao_estao_na_chave`` reprova
#: leitor novo que não esteja aqui: sem isso a suíte seria reaproveitada sem ter visto
#: a mudança que lê.
PY_SURFACE_READERS = {
    "config/management/commands/apply_material_skus.py": "surfaces/purchase-nuxt/tests/purchase.test.ts",
    "shopman/backstage/management/commands/export_bi_schema.py": "surfaces/bi-nuxt/app/generated",
    "shopman/backstage/management/commands/export_kds_schema.py": "surfaces/kds-nuxt/app/generated",
    "shopman/backstage/management/commands/export_marketing_client.py": "surfaces/marketing-nuxt/app/generated",
    "shopman/backstage/management/commands/export_orders_schema.py": "surfaces/orders-nuxt/app/generated",
    "shopman/backstage/management/commands/export_production_schema.py": "surfaces/production-nuxt/app/generated",
    "shopman/backstage/management/commands/export_recipe_book_schema.py": "surfaces/production-nuxt/app/generated",
    "shopman/shop/checks.py": "surfaces/registry.json",
    "shopman/shop/management/commands/export_pos_schema.py": "surfaces/pos-nuxt/app/generated",
    "shopman/shop/services/data_retention.py": "surfaces/storefront-nuxt/public/documentos-legais",
}


def surface_readers_step(root: Path, py: Path, steps: list) -> list:
    if not any(s.name.startswith("Testes (test-") for s in steps):
        return []
    readers = tests_reading(root, SURFACE_PATH_RE)
    if not readers:
        return []
    return [Step(
        SURFACE_READERS,
        f"{shlex.quote(str(py))} -m pytest -q -n auto " + " ".join(map(shlex.quote, readers)),
        slot="cpu", origin="local: evidência por passo (roda se alguma suíte foi reaproveitada)",
    )]


def _object(root: Path, tree: str, path: str) -> str:
    out = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{tree}:{path}"], cwd=root, capture_output=True, text=True)
    return out.stdout.strip() or "ausente"


def _blobs_at(root: Path, tree: str, path: str) -> list[str]:
    """Os arquivos (não as pastas) direto em ``path``, com hash: a raiz de surfaces/."""
    out = subprocess.run(["git", "ls-tree", f"{tree}:{path}"], cwd=root, capture_output=True, text=True).stdout
    return sorted(line for line in out.splitlines() if " blob " in line)


def _tree_without(root: Path, tree: str, top: str) -> list[str]:
    out = subprocess.run(["git", "ls-tree", tree], cwd=root, capture_output=True, text=True).stdout
    return sorted(line for line in out.splitlines() if not line.endswith(f"\t{top}"))


def step_key(root: Path, step: Step, tree: str, node: str, py: Path) -> str | None:
    """A chave das entradas do passo, ou None para o que sempre roda."""
    if step.slot not in ("cpu", "browser") or step.name.endswith("npm ci"):
        return None
    if step.cwd.startswith("surfaces/"):
        app = step.cwd.split("/")[1]
        if app == "operator-kit":
            inputs = [_object(root, tree, "surfaces")]
        else:
            inputs = [
                _object(root, tree, f"surfaces/{app}"),
                _object(root, tree, "surfaces/operator-kit"),
                *_blobs_at(root, tree, "surfaces"),
                _object(root, tree, "scripts/surface_contract.mjs"),
            ]
        inputs.append(f"node {node}")
    elif step.name.startswith("Testes (test-"):
        inputs = [
            *_tree_without(root, tree, "surfaces"),
            *_blobs_at(root, tree, "surfaces"),  # registry.json, contracts.json
            *(f"{path} {_object(root, tree, path)}" for path in sorted(set(PY_SURFACE_READERS.values()))),
        ]
    else:
        inputs = [tree]
    material = json.dumps(
        {"cmd": step.cmd, "cwd": step.cwd, "env": sorted(step.env.items()), "python": str(py), "inputs": inputs},
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def reusable(key: str | None) -> dict | None:
    if not key:
        return None
    path = state_dir() / "steps" / f"{key}.json"
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if record.get("status") == "pass" else None


def remember(key: str, record: dict) -> None:
    folder = state_dir() / "steps"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False))


# ── Node da CI ────────────────────────────────────────────────────────────
# A CI roda as superfícies no Node do `setup-node` (22); a máquina pode ter outro
# no PATH (26, medido em 26/11, sem `localStorage` global: o `usePwaInstall` da loja
# reprovava no preflight de todos e empurrava sessões para o `sem_preflight`).
# O preflight usa o MESMO major da CI, achado nos gerenciadores comuns; sem ele,
# falha dizendo o que instalar, em vez de reprovar teste por diferença de runtime.

NODE_HOMES = (
    "/opt/homebrew/opt/node@{m}/bin",
    "/usr/local/opt/node@{m}/bin",
    "~/.nvm/versions/node/v{m}.*/bin",
    "~/.volta/tools/image/node/{m}.*/bin",
    "~/.local/share/fnm/node-versions/v{m}.*/installation/bin",
    "~/Library/Application Support/fnm/node-versions/v{m}.*/installation/bin",
)


def ci_node_major(root: Path) -> str:
    """O major do `node-version` dos workflows; mais de um é erro de configuração."""
    majors = {
        m for wf in sorted((root / ".github" / "workflows").glob("*.y*ml"))
        for m in re.findall(r"node-version:\s*[\"']?(\d+)", wf.read_text())
    }
    if len(majors) != 1:
        raise SystemExit(f"❌ os workflows pedem Node {sorted(majors) or 'nenhum'}: deveria ser um major só")
    return majors.pop()


def node_major(bindir: Path) -> str | None:
    try:
        out = subprocess.run([str(bindir / "node"), "-v"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v(\d+)\.", out.strip())
    return m.group(1) if m else None


def find_ci_node(major: str, path: str, homes: tuple[str, ...] = NODE_HOMES) -> Path | None:
    """O diretório de um `node` do major pedido: o do PATH se já servir, senão o primeiro instalado."""
    on_path = shutil.which("node", path=path)
    candidates = [Path(on_path).parent] if on_path else []
    for pattern in homes:
        expanded = os.path.expanduser(pattern.format(m=major))
        candidates += [Path(p) for p in sorted(glob.glob(expanded), reverse=True)]
    return next((c for c in candidates if node_major(c) == major), None)


# ── Execução e evidência ─────────────────────────────────────────────────


def base_env(root: Path, py: Path, workers: int) -> dict:
    pythonpath = ":".join([str(root), *map(str, package_paths(root))])
    env = {
        **os.environ,
        "PYTHONPATH": pythonpath,
        # CI: o job de testes não tem banco nem Redis → SQLite em memória por
        # worker. Aqui isso é também o isolamento entre worktrees: um `.env`
        # apontando para Postgres faria duas worktrees dividirem test_shopman.
        "DATABASE_URL": "",
        "REDIS_URL": "",
        "PYTEST_XDIST_AUTO_NUM_WORKERS": str(workers),
        "GITHUB_STEP_SUMMARY": "/dev/null",
        "SHOPMAN_LOCAL_CI": "1",
        "PATH": f"{py.parent}:{os.environ.get('PATH', '')}",
    }
    node = find_ci_node(ci_node_major(root), env["PATH"])
    if node:
        env["PATH"] = f"{py.parent}:{node}:{os.environ.get('PATH', '')}"
    return env


def run_plan(root: Path, py: Path, plan: Plan, diff: Diff, keep_going: bool) -> dict:
    slots, workers = machine_budget()
    env = base_env(root, py, workers)
    logs = Path(git("rev-parse", "--git-dir", cwd=root)).resolve() / "shopman-local-ci"
    logs.mkdir(parents=True, exist_ok=True)
    results = []
    started = dt.datetime.now(dt.UTC)
    print(f"▶ {plan.level} · {len(diff.files)} arquivo(s) · árvore {diff.tree[:12]} · base {diff.base_ref}@{diff.merge_base[:9]}")
    print(f"  escopo {plan.scope} · máquina: {slots} vaga(s) × {workers} workers")
    failed = False
    waited_total = 0.0
    reused_suite = False
    to_remember: list[tuple[str, dict]] = []
    major = ci_node_major(root)
    node_ok = node_major(Path(shutil.which("node", path=env["PATH"]) or "/nonexistent").parent) == major
    def needs_node(step: Step) -> bool:
        return step.cwd.startswith("surfaces") or "surface_contract" in step.cmd

    if not node_ok and any(needs_node(s) for s in plan.steps):
        print(f"❌ a CI roda as superfícies no Node {major} e esta máquina não tem um Node {major} instalado.")
        print(f"   Instale (`brew install node@{major}`, ou pelo nvm/volta/fnm) e rode de novo: o preflight acha sozinho.")
        print("   Rodar com outro Node reprova teste por diferença de runtime, não por defeito.")
        failed = True
    for i, step in enumerate(plan.steps, 1):
        if (failed and not keep_going) or (not node_ok and needs_node(step)):
            results.append({**asdict(step), "status": "not-run", "seconds": 0})
            continue
        if step.name == SURFACE_READERS and not reused_suite:
            # Toda suíte rodou de novo nesta árvore: esses testes já rodaram dentro dela.
            results.append({**asdict(step), "status": "covered", "seconds": 0})
            print(f"[{i}/{len(plan.steps)}] {step.name}\n   ↳ coberto: as suítes rodaram inteiras", flush=True)
            continue
        key = step_key(root, step, diff.tree, major, py)
        previous = reusable(key)
        if previous:
            results.append({**asdict(step), "status": "reused", "seconds": 0, "reused_from": previous})
            reused_suite = reused_suite or step.name.startswith("Testes (test-")
            print(f"[{i}/{len(plan.steps)}] {step.name}\n   ↺ reaproveitado: mesmas entradas verdes em "
                  f"{previous['at']} ({previous['seconds']:.0f}s poupados)", flush=True)
            continue
        print(f"[{i}/{len(plan.steps)}] {step.name}", flush=True)
        log = logs / f"{i:02d}-{re.sub(r'[^a-zA-Z0-9]+', '-', step.name)[:60]}.log"
        # A faixa rápida (fast/impact) não espera atrás de um passo de 17 min de
        # preflight: tem vaga própria, com metade dos workers (#3635, 26/11).
        slot = "quick" if plan.level in QUICK_LEVELS and step.slot == "cpu" else step.slot
        step_env = {**env, **step.env}
        if slot == "quick":
            step_env["PYTEST_XDIST_AUTO_NUM_WORKERS"] = str(max(1, workers // 2))
        with machine_slot(slot, slots) as wait, open(log, "w") as fh:
            t0 = time.monotonic()
            proc = subprocess.run(
                ["bash", "-c", step.cmd], cwd=root / step.cwd, env=step_env,
                stdout=fh, stderr=subprocess.STDOUT,
            )
        seconds = round(time.monotonic() - t0, 1)
        waited_total += wait["seconds"]
        status = "pass" if proc.returncode == 0 else "fail"
        mark = "✓" if status == "pass" else "✗"
        print(f"   {mark} {seconds}s" + ("" if status == "pass" else f" — log: {log}"), flush=True)
        if status == "fail":
            failed = True
            tail = log.read_text(errors="replace").splitlines()[-25:]
            print("     " + "\n     ".join(tail))
        results.append({**asdict(step), "status": status, "seconds": seconds, "wait_seconds": wait["seconds"], "log": str(log)})
        if status == "pass" and key:
            to_remember.append((key, {"status": "pass", "seconds": seconds, "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                                      "tree": diff.tree, "worktree": str(root), "log": str(log)}))
    finished = dt.datetime.now(dt.UTC)
    current_tree = working_tree_hash(root)
    evidence = {
        "level": plan.level,
        "status": "fail" if failed else "pass",
        "tree": diff.tree,
        "tree_changed_during_run": current_tree != diff.tree,
        "head": git("rev-parse", "HEAD", cwd=root),
        "base_ref": diff.base_ref,
        "merge_base": diff.merge_base,
        "files": diff.files,
        "scope": plan.scope,
        "steps": results,
        "remote_only": plan.remote,
        "notes": plan.notes,
        "worktree": str(root),
        "python": str(py),
        "wait_seconds": round(waited_total, 1),
        "machine": {"slots": slots, "workers": workers, "node": major if node_ok else "ausente"},
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": round((finished - started).total_seconds(), 1),
    }
    if evidence["tree_changed_during_run"]:
        evidence["status"] = "stale"
    else:  # árvore mudou no meio: o verde de um passo pode ser de outro conteúdo
        for key, record in to_remember:
            remember(key, record)
    saved = sum(r.get("reused_from", {}).get("seconds", 0) for r in results)
    evidence["reused_seconds"] = round(saved, 1)
    path = state_dir() / "evidence" / f"{diff.tree}.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    # Evidência mais forte não é rebaixada por uma rodada mais fraca da mesma árvore.
    if not (previous and previous["status"] == "pass" and LEVELS.index(previous["level"]) > LEVELS.index(plan.level)):
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=1))
    (logs / "last.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1))
    total = sum(r["seconds"] for r in results)
    print(f"\n{'✅' if evidence['status'] == 'pass' else '❌'} {plan.level}: {evidence['status']} em {evidence['seconds']}s (passos somam {total:.0f}s; espera por vaga {waited_total:.0f}s; reaproveitado {saved:.0f}s)")
    if evidence["status"] == "stale":
        print("   ⚠️ a árvore mudou durante a rodada: a evidência não vale para o que está no disco agora")
    if plan.remote:
        print("   Só a CI executa:\n   - " + "\n   - ".join(dict.fromkeys(plan.remote)))
    for note in dict.fromkeys(plan.notes):
        print(f"   ℹ️ {note}")
    return evidence


# ── Subcomandos ───────────────────────────────────────────────────────────


def cmd_origin(root: Path) -> int:
    """Reprova se algum pacote ``shopman*`` vier de fora desta worktree."""
    import importlib

    names = ["config", "shopman.shop", "shopman.storefront", "shopman.backstage", "conversational_commerce"]
    for pkg in package_paths(root):
        for init in (pkg / "shopman").glob("*/__init__.py"):
            names.append(f"shopman.{init.parent.name}")
    bad = []
    for name in sorted(set(names)):
        try:
            mod = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — relatar e seguir
            bad.append(f"{name}: não importa ({exc.__class__.__name__}: {exc})")
            continue
        where = Path(getattr(mod, "__file__", None) or list(mod.__path__)[0]).resolve()
        if root.resolve() not in where.parents:
            bad.append(f"{name} → {where}")
    if bad:
        print("✗ código de FORA desta worktree seria testado:\n  " + "\n  ".join(bad))
        print("  Rode pelo `make check-*`/`make preflight` (põe a worktree no PYTHONPATH).")
        return 1
    print(f"✓ {len(set(names))} pacotes importam desta worktree ({root})")
    return 0


def cmd_migrations(root: Path) -> int:
    """Duas migrações com o mesmo número no mesmo app (CLAUDE.md)."""
    bad = []
    for mig in root.glob("**/migrations"):
        if "node_modules" in mig.parts or ".venv" in mig.parts:
            continue
        nums = [p.name.split("_")[0] for p in mig.glob("[0-9][0-9][0-9][0-9]_*.py")]
        dups = sorted({n for n in nums if nums.count(n) > 1})
        if dups:
            bad.append(f"{mig.relative_to(root)}: {', '.join(dups)}")
    if bad:
        print("✗ numeração de migração repetida:\n  " + "\n  ".join(bad))
        return 1
    print("✓ nenhuma numeração de migração repetida")
    return 0


def cmd_pins(root: Path, fix: bool = False) -> int:
    """A .venv local instala o que o ``constraints.txt`` fixa (paridade com a CI).

    ``--fix`` instala SÓ os pinos divergentes, sob trava de máquina (a .venv é
    uma para todas as worktrees): nada de reinstalar a suíte inteira.
    """
    from importlib import metadata

    def norm(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    installed = {norm(d.metadata["Name"]): d.version for d in metadata.distributions()}
    bad: list[str] = []
    wanted: list[str] = []
    for line in (root / "constraints.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;#]+)", line.strip())
        if not m:
            continue
        name, want = norm(m.group(1)), m.group(3)
        have = installed.get(name)
        if have is not None and have != want:
            bad.append(f"{name}: .venv tem {have}, constraints fixa {want}")
            wanted.append(f"{name}=={want}")
    if bad and fix:
        with machine_slot("venv", 1):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-c", str(root / "constraints.txt"), *wanted], check=True)
        print(f"✓ {len(wanted)} pino(s) alinhado(s) na .venv: {', '.join(wanted)}")
        return cmd_pins(root, fix=False)
    if bad:
        print("✗ a .venv divergiu dos pinos (o local testaria outro conjunto que a CI):\n  " + "\n  ".join(bad))
        print("  Conserte: `make venv-sync` (instala só os pinos divergentes, com trava de máquina).")
        return 1
    print("✓ .venv nos pinos do constraints.txt")
    return 0


def fetch_main(root: Path) -> None:
    """``git fetch origin main`` com nova tentativa: outra worktree buscando ao mesmo
    tempo trava o ref por um instante ("cannot lock ref"), e o `ready` abortava (26/11)."""
    for attempt in range(4):
        try:
            git("fetch", "-q", "origin", "main", cwd=root)
            return
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def find_evidence(tree: str) -> dict | None:
    path = state_dir() / "evidence" / f"{tree}.json"
    return json.loads(path.read_text()) if path.exists() else None


def evidence_line(evidence: dict | None, tree: str) -> str:
    """O que a evidência É. Com a exceção declarada, nunca "verde" se não for (26/11:
    a mensagem antiga dizia "verde" para um preflight 44/45)."""
    if evidence and evidence["status"] == "pass" and evidence["level"] in PROMOTABLE:
        return f"✓ evidência {evidence['level']} verde para a árvore {tree[:12]} ({evidence['seconds']}s, {evidence['started_at']})"
    if evidence:
        return (f"ℹ️ evidência registrada para a árvore {tree[:12]}: {evidence['level']}/{evidence['status']} "
                f"({evidence['started_at']}); promovido pela exceção declarada")
    return f"ℹ️ nenhuma evidência para a árvore {tree[:12]}; promovido pela exceção declarada"


def cmd_ready(root: Path, py: Path, pr: int, sem_preflight: str | None, dry_run: bool) -> int:
    """Promove o PR à fila só com evidência para o HEAD exato."""
    problems: list[str] = []
    status = git("status", "--porcelain", cwd=root)
    if status:
        problems.append("árvore suja (commite ou descarte antes):\n    " + status.replace("\n", "\n    "))
    head = git("rev-parse", "HEAD", cwd=root)
    tree = git("rev-parse", "HEAD^{tree}", cwd=root)
    info = json.loads(gh("pr", "view", str(pr), "-R", REPO_SLUG, "--json", "headRefOid,isDraft,state,baseRefName,body,mergeable"))
    if info["headRefOid"] != head:
        problems.append(f"o PR #{pr} aponta para {info['headRefOid'][:9]}, esta worktree está em {head[:9]} (falta push?)")
    if info["isDraft"]:
        problems.append(f"o PR #{pr} é draft: `gh pr ready {pr}` primeiro")
    if info["mergeable"] == "CONFLICTING":
        problems.append(f"o PR #{pr} conflita com {info['baseRefName']}: atualize o branch")
    evidence = find_evidence(tree)
    if sem_preflight:
        print(f"⚠️ promovendo SEM preflight, por decisão explícita: {sem_preflight}")
        override = {"pr": pr, "head": head, "tree": tree, "reason": sem_preflight, "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "worktree": str(root)}
        with open(state_dir() / "overrides.jsonl", "a") as fh:
            fh.write(json.dumps(override, ensure_ascii=False) + "\n")
    elif not evidence:
        problems.append(f"sem evidência para a árvore {tree[:12]}: rode `make preflight` nesta worktree")
    elif evidence["status"] != "pass" or evidence["level"] not in PROMOTABLE:
        problems.append(f"a evidência da árvore {tree[:12]} é {evidence['level']}/{evidence['status']}: rode `make preflight` até ficar verde")
    # O que só o corpo do PR decide, e que derrubava PR na fila (#3354).
    env = {**os.environ, "PR_BODY": info["body"] or ""}
    for name, cmd in (
        ("Ficou de fora declarado", [str(py), "scripts/check_ficou_de_fora.py", "--pr", str(pr)]),
        ("Compromissos", [str(py), "scripts/check_commitments.py", "--pr-body-env", "--no-fail-overdue", "--with-issues"]),
    ):
        proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        if proc.returncode:
            problems.append(f"{name} reprova o corpo do PR:\n    " + (proc.stdout + proc.stderr).strip().replace("\n", "\n    "))
    fetch_main(root)
    behind = int(git("rev-list", "--count", "HEAD..origin/main", cwd=root) or 0)
    if behind:
        mine = set(git("diff", "--name-only", f"{git('merge-base', 'HEAD', 'origin/main', cwd=root)}", "HEAD", cwd=root).splitlines())
        theirs = set(git("diff", "--name-only", "HEAD...origin/main", cwd=root).splitlines())
        overlap = sorted(mine & theirs)
        msg = f"o main andou {behind} commit(s) desde a sua base"
        print(f"ℹ️ {msg}" + (f"; e mexeu nos MESMOS arquivos: {', '.join(overlap[:8])} — considere atualizar e rodar o preflight de novo" if overlap else " (sem arquivo em comum)"))
    if problems:
        print(f"✗ PR #{pr} não vai para a fila:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(evidence_line(evidence, tree))
    # Sem flag de estratégia: com fila obrigatória, a fila é dona (esteira-stop-hook).
    # --match-head-commit: se alguém empurrar depois desta conferência, o GitHub recusa.
    cmd = ["gh", "pr", "merge", str(pr), "-R", REPO_SLUG, "--auto", "--match-head-commit", head]
    if dry_run:
        print("(dry-run) " + " ".join(cmd))
        return 0
    subprocess.run(cmd, check=True)
    print(f"✓ PR #{pr} com auto-merge no HEAD {head[:9]}; a fila testa a árvore candidata inteira.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("level", nargs="?" if name == "plan" else None, choices=LEVELS, default="preflight")
        p.add_argument("--base", default="origin/main")
        p.add_argument("--keep-going", action="store_true", help="não para na primeira falha")
        p.add_argument("--json", action="store_true")
    sub.add_parser("origin")
    sub.add_parser("migrations")
    p = sub.add_parser("pins")
    p.add_argument("--fix", action="store_true")
    p = sub.add_parser("ready")
    p.add_argument("pr", type=int)
    p.add_argument("--sem-preflight", metavar="MOTIVO")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("evidence")
    p.add_argument("ref", nargs="?", default="HEAD")
    args = parser.parse_args()

    root = repo_root()
    py = venv_python(root)
    # Tudo o que importa Django/yaml roda na .venv canônica, com a worktree na frente.
    if Path(sys.executable).resolve() != py.resolve() and args.command in ("plan", "run", "origin", "pins"):
        env = base_env(root, py, machine_budget()[1])
        os.execve(str(py), [str(py), __file__, *sys.argv[1:]], env)

    if args.command == "origin":
        return cmd_origin(root)
    if args.command == "migrations":
        return cmd_migrations(root)
    if args.command == "pins":
        return cmd_pins(root, fix=args.fix)
    if args.command == "evidence":
        ref = args.ref
        tree = ref if re.fullmatch(r"[0-9a-f]{40}", ref) and find_evidence(ref) else git("rev-parse", f"{ref}^{{tree}}", cwd=root)
        ev = find_evidence(tree)
        print(json.dumps(ev, ensure_ascii=False, indent=1) if ev else f"sem evidência para a árvore {tree}")
        return 0 if ev and ev["status"] == "pass" else 1
    if args.command == "ready":
        return cmd_ready(root, py, args.pr, args.sem_preflight, args.dry_run)

    if args.level != "fast":  # o rápido usa o origin/main que já está aqui
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=root)
    diff = compute_diff(root, args.base)
    _, workers = machine_budget()
    plan = build_plan(root, py, args.level, diff, workers)
    if args.command == "plan":
        if args.json:
            print(json.dumps({"diff": asdict(diff), **asdict(plan)}, ensure_ascii=False, indent=1))
        else:
            print(f"{args.level}: {len(diff.files)} arquivo(s), escopo {plan.scope}")
            for s in plan.steps:
                print(f"  - [{s.slot}] {s.name}  ({s.origin})")
            for r in dict.fromkeys(plan.remote):
                print(f"  · remoto: {r}")
            for n in dict.fromkeys(plan.notes):
                print(f"  ℹ️ {n}")
        return 0
    evidence = run_plan(root, py, plan, diff, keep_going=args.keep_going or args.level in ("preflight", "full"))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
