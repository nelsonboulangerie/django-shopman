#!/usr/bin/env python3
"""Fail closed when canonical go-live documentation drifts from the repo.

The checker is intentionally stdlib-only so the required Runtime Gate can run
it immediately after Python setup. It validates executable contracts (version,
workflow and Make targets), local links, the canonical readiness schema, the
ADR-015 tag state and high-confidence secret/legacy-host regressions.

It also guards the required status checks of `main`: the list lives in
`.github/required-status-checks.json` (mirror of the branch protection) and
every context there must still be produced by a workflow job that runs on
pull_request and merge_group. `--live-required-checks` additionally compares
the mirror with the live protection through `gh api`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DOCS = (
    Path("docs/status.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/plans/GO-LIVE-READINESS-PLAN.md"),
    Path("docs/plans/GO-LIVE-CREDENTIALS-MATRIX.md"),
    Path("docs/runbooks/go-live-preflight.md"),
    Path("docs/runbooks/go-live-cutover.md"),
    Path("docs/runbooks/rollback-de-deploy.md"),
    Path("docs/runbooks/README.md"),
    Path("docs/reference/runtime-dependencies.md"),
    Path("docs/guides/deploy.md"),
    Path("docs/plans/README.md"),
)

EXPECTED_WORKFLOWS = {
    Path(".github/workflows/deploy-images.yml"): "Deploy Images",
    Path(".github/workflows/alpha-smoke.yml"): "Pre-go-live Smoke",
    Path(".github/workflows/runtime-gate.yml"): "Runtime Gate",
    Path(".github/workflows/surfaces-gate.yml"): "Surfaces Gate",
    Path(".github/workflows/omotenashi-gate.yml"): "Omotenashi Gate",
    Path(".github/workflows/security-gate.yml"): "Security Gate",
    Path(".github/workflows/production-contract.yml"): "Production Contract",
    Path(".github/workflows/operator-groups-gate.yml"): "Operator Groups Gate",
}

EXPECTED_TARGETS = {
    "canonical-docs",
    "test-migrations",
    "production-contract",
    "production-readiness",
    "smoke-gateways-sandbox",
}

EXPECTED_RUNBOOKS = {
    Path("docs/runbooks/go-live-preflight.md"),
    Path("docs/runbooks/go-live-cutover.md"),
    Path("docs/runbooks/rollback-de-deploy.md"),
    Path("docs/runbooks/backup-e-restore.md"),
}

FORBIDDEN_TEXT = {
    "stale Django range": re.compile(r"Django\s*>=\s*6\.0\s*,\s*<\s*6\.1", re.I),
    "manual-only hosted deploy": re.compile(r"deploy de c[oó]digo.{0,30}(?:é|e)\s+\*\*?manual", re.I),
    "stale not-started claim": re.compile(r"execu[cç][aã]o dos lotes.{0,20}n[aã]o iniciada", re.I),
    "Machine absent from code": re.compile(r"(?:TaOn\s*/\s*Taxi\s*)?Machine.{0,40}n[aã]o existe no c[oó]digo", re.I),
}

FORBIDDEN_HOSTS = {
    "alpha.nelsonboulangerie.com.br",
    "shopman-alpha.ondigitalocean.app",
}

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Stripe secret": re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{12,}\b"),
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
TOP_LEVEL_NAME_RE = re.compile(r'^name:\s*["\']?([^"\']+?)["\']?\s*$', re.M)
MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", re.M)
AUDIT_DATE_RE = re.compile(r"`verificado_em`:\s*`\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`")
READINESS_START = "<!-- canonical-readiness:start -->"
READINESS_END = "<!-- canonical-readiness:end -->"
ALLOWED_STATES = {"VERIFICADO", "PENDENTE", "BLOQUEADO", "DESCONHECIDO", "N/A"}

REQUIRED_CHECKS_FILE = Path(".github/required-status-checks.json")
WORKFLOWS_DIR = Path(".github/workflows")
# Um check obrigatório tem de existir no PR E na fila de merge: faltar em
# qualquer um dos dois trava o merge para sempre.
REQUIRED_TRIGGERS = ("pull_request", "merge_group")
MATRIX_REF_RE = re.compile(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}")


@dataclass
class Result:
    errors: list[str]
    passed: list[str]

    def ok(self, message: str) -> None:
        self.passed.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)


def _read(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _django_requirement() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    matches = [item for item in dependencies if re.match(r"^Django(?:[<>=!~].*)?$", item)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Django dependency, found {matches!r}")
    return matches[0]


def check_versions(result: Result) -> None:
    try:
        requirement = _django_requirement()
    except (KeyError, TypeError, ValueError) as exc:
        result.fail(f"pyproject Django requirement unreadable: {exc}")
        return
    for path in (Path("docs/status.md"), Path("docs/reference/runtime-dependencies.md")):
        if f"`{requirement}`" not in _read(path):
            result.fail(f"{path}: must document executable Django requirement `{requirement}`")
    if not any(str(path).endswith("status.md") and f"`{requirement}`" in _read(path) for path in CANONICAL_DOCS):
        result.fail("canonical status does not expose the Django requirement")
    result.ok(f"Django requirement matches pyproject: {requirement}")


def check_workflows_and_targets(result: Result) -> None:
    for path, expected in EXPECTED_WORKFLOWS.items():
        if not (ROOT / path).is_file():
            result.fail(f"missing workflow: {path}")
            continue
        match = TOP_LEVEL_NAME_RE.search(_read(path))
        actual = match.group(1).strip() if match else None
        if actual != expected:
            result.fail(f"{path}: workflow name {actual!r}, expected {expected!r}")
    makefile = _read(Path("Makefile"))
    targets = set(MAKE_TARGET_RE.findall(makefile))
    for target in sorted(EXPECTED_TARGETS - targets):
        result.fail(f"Makefile target referenced by canonical docs is missing: {target}")
    for path in sorted(EXPECTED_RUNBOOKS):
        if not (ROOT / path).is_file():
            result.fail(f"canonical runbook is missing: {path}")
    result.ok("workflow names, Make targets and runbooks exist")


def _link_target(source: Path, raw: str) -> Path | None:
    target = raw.strip()
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    if " " in target and not target.startswith("<"):
        target = target.split(" ", 1)[0]
    target = target.strip("<>").split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    return (source.parent / unquote(target)).resolve()


def check_links(result: Result) -> None:
    for source in CANONICAL_DOCS:
        for raw in LINK_RE.findall(_read(source)):
            target = _link_target(source, raw)
            if target is None:
                continue
            try:
                target.relative_to(ROOT)
            except ValueError:
                result.fail(f"{source}: local link escapes repository: {raw}")
                continue
            if not target.exists():
                result.fail(f"{source}: broken local link: {raw}")
    result.ok("canonical local links resolve")


def check_known_contradictions(result: Result) -> None:
    corpus = "\n".join(_read(path) for path in CANONICAL_DOCS)
    for label, pattern in FORBIDDEN_TEXT.items():
        if pattern.search(corpus):
            result.fail(f"known contradiction returned: {label}")
    lower = corpus.lower()
    for host in sorted(FORBIDDEN_HOSTS):
        if host.lower() in lower:
            result.fail(f"forbidden historical host returned to canonical docs: {host}")
    result.ok("known contradictions and retired hosts are absent")


def check_audit_metadata_and_table(result: Result) -> None:
    for path in (
        Path("docs/plans/GO-LIVE-READINESS-PLAN.md"),
        Path("docs/plans/GO-LIVE-CREDENTIALS-MATRIX.md"),
    ):
        if not AUDIT_DATE_RE.search(_read(path)):
            result.fail(f"{path}: missing UTC `verificado_em` audit timestamp")

    text = _read(Path("docs/plans/GO-LIVE-READINESS-PLAN.md"))
    if READINESS_START not in text or READINESS_END not in text:
        result.fail("readiness matrix markers are missing")
        return
    body = text.split(READINESS_START, 1)[1].split(READINESS_END, 1)[0]
    rows = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"Critério", "---"}:
            continue
        rows.append(cells)
    if len(rows) < 10:
        result.fail(f"readiness matrix has only {len(rows)} data rows")
    for index, cells in enumerate(rows, start=1):
        if len(cells) != 6:
            result.fail(f"readiness row {index} must have 6 columns, found {len(cells)}")
            continue
        criterion, state, environment, evidence, owner, next_event = cells
        if state not in ALLOWED_STATES:
            result.fail(f"readiness row {criterion!r} has invalid state {state!r}")
        if not all((criterion, environment, evidence, owner, next_event)):
            result.fail(f"readiness row {criterion!r} has an empty required field")
        if state in {"PENDENTE", "BLOQUEADO", "DESCONHECIDO"}:
            if owner in {"—", "-", "TBD", "UNKNOWN"}:
                result.fail(f"open readiness row {criterion!r} has no accountable owner")
            if next_event in {"—", "-", "TBD", "UNKNOWN"}:
                result.fail(f"open readiness row {criterion!r} has no next event")
    result.ok("readiness rows have state, environment, evidence, owner and next event")


def _tag_exists() -> bool:
    completed = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/tags/go-live-v1"],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode == 0


def check_adr015_state(result: Result) -> None:
    implementation = _read(Path("scripts/check_adr015.py"))
    workflow = _read(Path(".github/workflows/runtime-gate.yml"))
    readiness = _read(Path("docs/plans/GO-LIVE-READINESS-PLAN.md"))
    status = _read(Path("docs/status.md"))
    if 'GO_LIVE_TAG = "go-live-v1"' not in implementation:
        result.fail("ADR-015 implementation no longer uses go-live-v1")
    if "git fetch --force --depth=1 origin tag go-live-v1" not in workflow:
        result.fail("Runtime Gate no longer fetches the ADR-015 trigger tag")
    docs = readiness + "\n" + status
    if _tag_exists():
        if not re.search(r"tag `go-live-v1`.{0,80}(?:presente|existe)", docs, re.I | re.S):
            result.fail("go-live-v1 exists but canonical docs do not say the tag is present")
        if not re.search(r"ADR-015.{0,40}\*\*ativa\*\*", docs, re.I | re.S):
            result.fail("go-live-v1 exists but canonical docs do not say ADR-015 is active")
    else:
        if not re.search(r"tag `go-live-v1`.{0,80}ausente", docs, re.I | re.S):
            result.fail("go-live-v1 is absent but canonical docs do not say so")
        if not re.search(r"ADR-015.{0,40}\*\*inativa\*\*", docs, re.I | re.S):
            result.fail("go-live-v1 is absent but canonical docs do not say ADR-015 is inactive")
    result.ok("ADR-015 documentation matches the tag-trigger implementation")


def check_deploy_contract(result: Result) -> None:
    deploy = _read(Path(".github/workflows/deploy-images.yml"))
    smoke = _read(Path(".github/workflows/alpha-smoke.yml"))
    docs = _read(Path("docs/status.md")) + "\n" + _read(Path("docs/guides/deploy.md"))
    required_deploy_tokens = ("push:", "main", "published-components")
    required_smoke_tokens = ('workflows: ["Deploy Images"]', "wait_for_do_deployment.py", "API pronta (/ready/)")
    required_doc_tokens = ("Deploy Images", "deploy_on_push", "Pre-go-live Smoke", "deployment técnico")
    for token in required_deploy_tokens:
        if token not in deploy:
            result.fail(f"Deploy Images contract token missing: {token}")
    for token in required_smoke_tokens:
        if token not in smoke:
            result.fail(f"Pre-go-live Smoke contract token missing: {token}")
    for token in required_doc_tokens:
        if token not in docs:
            result.fail(f"hosted deploy documentation token missing: {token}")
    result.ok("hosted publish/deploy/smoke description matches workflows")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(raw: str) -> str:
    value = raw.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def _workflow_triggers(lines: list[str]) -> set[str]:
    """Chaves de primeiro nível do bloco `on:` (ou `"on":`)."""
    triggers: set[str] = set()
    inside = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _indent(line) == 0:
            key = line.split(":", 1)[0].strip().strip("'\"")
            inside = key == "on"
            if inside and ":" in line and line.split(":", 1)[1].strip():
                raise ValueError(f"inline `on:` not supported: {line.strip()}")
            continue
        if inside and _indent(line) == 2 and ":" in line:
            triggers.add(line.split(":", 1)[0].strip())
    return triggers


def _job_blocks(lines: list[str]) -> dict[str, list[str]]:
    jobs: dict[str, list[str]] = {}
    inside = False
    current: str | None = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            if current:
                jobs[current].append(line)
            continue
        if _indent(line) == 0:
            inside = line.startswith("jobs:")
            current = None
            continue
        if not inside:
            continue
        if _indent(line) == 2:
            current = line.split(":", 1)[0].strip()
            jobs[current] = []
        elif current:
            jobs[current].append(line)
    return jobs


def _job_matrix(block: list[str]) -> dict[str, list[str]]:
    """Eixos de uma matriz ESTÁTICA (`eixo: [a, b]` ou lista em bloco)."""
    matrix: dict[str, list[str]] = {}
    matrix_indent: int | None = None
    axis: str | None = None
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent(line)
        stripped = line.strip()
        if matrix_indent is None:
            if stripped.startswith("matrix:"):
                if stripped.split(":", 1)[1].strip():
                    raise ValueError(f"dynamic matrix not supported: {stripped}")
                matrix_indent = indent
            continue
        if indent <= matrix_indent:
            break
        if stripped.startswith("- ") and axis is not None:
            matrix[axis].append(_scalar(stripped[2:]))
            continue
        key, _, rest = stripped.partition(":")
        if key in {"include", "exclude"}:
            raise ValueError(f"matrix `{key}` not supported by the required-check reader")
        axis = key
        rest = rest.strip()
        if rest.startswith("[") and rest.endswith("]"):
            matrix[axis] = [_scalar(item) for item in rest[1:-1].split(",") if item.strip()]
            axis = None
        else:
            matrix[axis] = []
    return matrix


def _job_check_names(job_id: str, block: list[str]) -> set[str]:
    """Nomes de check que um job publica, como o GitHub os monta."""
    name = job_id
    for line in block:
        if _indent(line) == 4 and line.strip().startswith("name:"):
            name = _scalar(line.strip()[len("name:") :])
            break
    matrix = _job_matrix(block)
    if not matrix:
        return {name}
    referenced = MATRIX_REF_RE.findall(name)
    if referenced:
        names = {name}
        for axis in referenced:
            if axis not in matrix:
                raise ValueError(f"job {job_id}: name uses matrix.{axis}, which is not a static axis")
            names = {
                MATRIX_REF_RE.sub(lambda m, a=axis, v=value: v if m.group(1) == a else m.group(0), current)
                for current in names
                for value in matrix[axis]
            }
        return names
    # Sem referência à matriz no nome, o GitHub anexa os valores: "Testes (test-shop)".
    if len(matrix) != 1:
        raise ValueError(f"job {job_id}: multi-axis matrix without matrix reference in name")
    (values,) = matrix.values()
    return {f"{name} ({value})" for value in values}


def workflow_check_names() -> tuple[dict[str, set[str]], list[str]]:
    """Check name → workflows que o publicam em pull_request E merge_group.

    Devolve também os jobs cujo nome o leitor não sabe montar (matriz com
    `include`, matriz dinâmica): não são erro por si, mas entram na mensagem
    se um check obrigatório sumir.
    """
    produced: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for path in sorted((ROOT / WORKFLOWS_DIR).glob("*.y*ml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not set(REQUIRED_TRIGGERS) <= _workflow_triggers(lines):
            continue
        for job_id, block in _job_blocks(lines).items():
            try:
                names = _job_check_names(job_id, block)
            except ValueError as exc:
                unresolved.append(f"{path.name}:{job_id} ({exc})")
                continue
            for check_name in names:
                produced.setdefault(check_name, set()).add(path.name)
    return produced, unresolved


def _required_checks() -> list[str]:
    data = json.loads(_read(REQUIRED_CHECKS_FILE))
    contexts = data["contexts"]
    if not isinstance(contexts, list) or not all(isinstance(c, str) and c for c in contexts):
        raise ValueError(f"{REQUIRED_CHECKS_FILE}: `contexts` must be a list of non-empty strings")
    for key in ("branch", "read_at", "command"):
        if not data.get(key):
            raise ValueError(f"{REQUIRED_CHECKS_FILE}: missing `{key}`")
    return contexts


def check_required_status_checks(result: Result) -> None:
    contexts = _required_checks()
    duplicated = sorted({c for c in contexts if contexts.count(c) > 1})
    if duplicated:
        result.fail(f"{REQUIRED_CHECKS_FILE}: duplicated contexts {duplicated}")
    produced, unresolved = workflow_check_names()
    for context in contexts:
        if context not in produced:
            hint = f"; jobs the reader could not expand: {unresolved}" if unresolved else ""
            result.fail(
                f"required check {context!r} is not produced by any workflow job on "
                f"{' + '.join(REQUIRED_TRIGGERS)}: renaming/removing it locks every PR{hint}"
            )
    result.ok(f"{len(contexts)} required checks of main are produced by workflow jobs")


def check_required_status_checks_live(result: Result) -> None:
    """Compara o espelho versionado com a branch protection viva (precisa de `gh`)."""
    data = json.loads(_read(REQUIRED_CHECKS_FILE))
    completed = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{data['branch']}/protection/required_status_checks"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    live = json.loads(completed.stdout)
    if sorted(live["contexts"]) != sorted(data["contexts"]):
        missing = sorted(set(live["contexts"]) - set(data["contexts"]))
        extra = sorted(set(data["contexts"]) - set(live["contexts"]))
        result.fail(f"{REQUIRED_CHECKS_FILE} drifted from GitHub: missing {missing}, extra {extra}")
    if live["strict"] != data["strict"]:
        result.fail(f"{REQUIRED_CHECKS_FILE}: strict={data['strict']} but GitHub says {live['strict']}")
    result.ok(f"{REQUIRED_CHECKS_FILE} matches live branch protection ({len(live['contexts'])} contexts)")


def check_secrets(result: Result) -> None:
    paths = CANONICAL_DOCS + (Path(".env.example"),)
    for path in paths:
        text = _read(path)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                result.fail(f"{path}: possible literal {label}")
    result.ok("no high-confidence literal secret pattern found")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = Result(errors=[], passed=[])
    checks = (
        check_versions,
        check_workflows_and_targets,
        check_links,
        check_known_contradictions,
        check_audit_metadata_and_table,
        check_adr015_state,
        check_deploy_contract,
        check_required_status_checks,
        check_secrets,
    )
    if "--live-required-checks" in argv:
        checks += (check_required_status_checks_live,)
    for check in checks:
        try:
            check(result)
        except Exception as exc:  # noqa: BLE001 - checker bugs must fail closed
            result.fail(f"{check.__name__} crashed: {type(exc).__name__}: {exc}")

    for message in result.passed:
        print(f"[OK] {message}")
    if result.errors:
        for message in result.errors:
            print(f"[FAIL] {message}", file=sys.stderr)
        print(f"canonical docs drift: {len(result.errors)} failure(s)", file=sys.stderr)
        return 1
    print("canonical docs: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
