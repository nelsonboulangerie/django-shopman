#!/usr/bin/env python3
"""Fail closed when canonical go-live documentation drifts from the repo.

The checker is intentionally stdlib-only so the required Runtime Gate can run
it immediately after Python setup. It validates executable contracts (version,
workflow and Make targets), local links, the canonical readiness schema, the
ADR-015 tag state and high-confidence secret/legacy-host regressions.
"""

from __future__ import annotations

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


def check_secrets(result: Result) -> None:
    paths = CANONICAL_DOCS + (Path(".env.example"),)
    for path in paths:
        text = _read(path)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                result.fail(f"{path}: possible literal {label}")
    result.ok("no high-confidence literal secret pattern found")


def main() -> int:
    result = Result(errors=[], passed=[])
    checks = (
        check_versions,
        check_workflows_and_targets,
        check_links,
        check_known_contradictions,
        check_audit_metadata_and_table,
        check_adr015_state,
        check_deploy_contract,
        check_secrets,
    )
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
