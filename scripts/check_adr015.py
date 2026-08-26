#!/usr/bin/env python
"""ADR-015 enforcement gate — backward-compat policy as a machine, not prose.

The policy in ``docs/decisions/adr-015-backward-compat-policy-post-prod.md``
arms itself on the EXISTENCE of the ``go-live-v1`` git tag. Before the tag,
every check here is a green no-op with one honest log line; after the tag,
two things become blocking in CI:

1. **Migrations are append-only** — the PR diff (against the merge base) may
   only ADD files under ``*/migrations/``. Modifying or deleting an existing
   migration fails the gate. A fix to an applied migration is a NEW migration.
2. **DEPRECATED markers carry a deadline** — every ``# DEPRECATED(remove by
   YYYY-MM-DD)`` marker is collected; a past date (or a marker that does not
   parse) fails the gate. The transition window is enforced, not decorative.

A third post-tag check — new migrations with destructive operations must carry
an ``# expand-contract:`` marker — lives in ``scripts/check_migrations.py``
(``make test-migrations``) and imports its helpers from this module.

CI note: the runner checkout is shallow and tag-less. The Runtime Gate fetches
the ``go-live-v1`` tag explicitly before running this script; without that
fetch the policy would stay "pre go-live" forever. ``SHOPMAN_ADR015_FORCE=1``
(or ``0``) overrides tag detection for tests and local simulation.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

GO_LIVE_TAG = "go-live-v1"
PRE_GO_LIVE_MESSAGE = "pré-go-live: política ADR-015 inativa (tag go-live-v1 ausente)"

#: Migration operations that remove or reshape something the running code may
#: still depend on. Post go-live these demand the expand-contract discipline.
DESTRUCTIVE_OPERATIONS = frozenset(
    {"RemoveField", "DeleteModel", "RenameField", "RenameModel", "AlterField"}
)

#: ``# expand-contract: <phase> — <plan reference>`` — phase names come from
#: docs/guides/production-upgrades.md; the reference points at the plan/PR that
#: schedules the matching contract (or records why the phase is safe).
EXPAND_CONTRACT_MARKER_RE = re.compile(
    r"#\s*expand-contract:\s*(?P<phase>expand|backfill|migrate|contract)\b\s*[—–-]+\s*(?P<reference>\S.*)"
)

EXPAND_CONTRACT_HOWTO = (
    "Migração nova com operação destrutiva (RemoveField/DeleteModel/RenameField/"
    "RenameModel/AlterField) exige o marcador expand-contract no próprio arquivo:\n"
    "    # expand-contract: <fase> — <link do plano>\n"
    "onde <fase> ∈ {expand, backfill, migrate, contract} e <link do plano> aponta o "
    "plano/PR que agenda a fase contract (docs/guides/production-upgrades.md). "
    "O marcador declara que a remoção foi faseada de propósito, não num deploy só."
)

DEPRECATED_MARKER_RE = re.compile(r"DEPRECATED\((?P<inner>[^)]*)\)")
DEPRECATED_DEADLINE_RE = re.compile(r"^\s*remove by (?P<date>\d{4}-\d{2}-\d{2})\s*$")

#: Paths where the literal string ``DEPRECATED(`` is documentation or fixture,
#: not a live marker in shipped code.
DEPRECATED_SCAN_EXCLUDES = (
    ":(exclude)docs",
    ":(exclude)scripts/check_adr015.py",
    ":(exclude)shopman/shop/tests/test_adr015_gate.py",
    ":(exclude)CLAUDE.md",
)


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def go_live_active(repo_root: Path | None = None) -> bool:
    """Whether the ADR-015 policy is armed.

    ``SHOPMAN_ADR015_FORCE`` ("1"/"0") wins, for tests and local simulation.
    Otherwise: the ``go-live-v1`` tag exists in the local repository.
    """
    forced = (os.environ.get("SHOPMAN_ADR015_FORCE", "") or "").strip()
    if forced == "1":
        return True
    if forced == "0":
        return False
    result = _git(["tag", "--list", GO_LIVE_TAG], cwd=repo_root)
    return result.returncode == 0 and GO_LIVE_TAG in result.stdout.split()


# ---------------------------------------------------------------------------
# Check 1 — migrations are append-only in the PR diff
# ---------------------------------------------------------------------------


def is_migration_file(path: str) -> bool:
    posix = path.replace("\\", "/")
    if not posix.endswith(".py") or posix.endswith("/__init__.py"):
        return False
    return "/migrations/" in posix


def classify_append_only(name_status_lines: list[str]) -> list[tuple[str, str]]:
    """Return ``(status, path)`` violations from ``git diff --name-status`` lines.

    Anything but an addition (``A``) touching a migration file is a violation.
    """
    violations: list[tuple[str, str]] = []
    for line in name_status_lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        # --no-renames keeps statuses to single letters; be defensive anyway.
        paths = [p for p in parts[1:] if p.strip()]
        for path in paths:
            if is_migration_file(path) and not status.startswith("A"):
                violations.append((status, path))
    return violations


def resolve_diff_base(repo_root: Path | None = None) -> tuple[str | None, str]:
    """Find the merge base for the append-only diff, per trigger.

    Returns ``(commit-ish or None, human description)``. Handles the three
    contexts the Runtime Gate runs in:

    - ``merge_group``: the event payload carries ``merge_group.base_sha`` — the
      exact commit the queue is merging onto.
    - ``pull_request``: HEAD is the synthetic merge commit of PR into base, so
      a tree-diff against the fetched base tip isolates the PR's changes.
    - local: merge-base against ``origin/main`` (fallback: the tip itself).
    """
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "merge_group":
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        try:
            payload = json.loads(Path(event_path).read_text())
            base_sha = payload["merge_group"]["base_sha"]
        except (OSError, KeyError, ValueError, TypeError):
            return None, "merge_group sem base_sha legível no GITHUB_EVENT_PATH"
        _git(["fetch", "--depth=1", "origin", base_sha], cwd=repo_root)
        return base_sha, f"merge_group base_sha {base_sha[:12]}"
    if event == "pull_request":
        base_ref = os.environ.get("GITHUB_BASE_REF", "") or "main"
        fetched = _git(["fetch", "--depth=1", "origin", base_ref], cwd=repo_root)
        if fetched.returncode != 0:
            return None, f"fetch da base '{base_ref}' falhou: {fetched.stderr.strip()}"
        return "FETCH_HEAD", f"pull_request base origin/{base_ref} (FETCH_HEAD)"
    # Local / other triggers: best effort against origin/main.
    for candidate in ("origin/main", "main"):
        merge_base = _git(["merge-base", candidate, "HEAD"], cwd=repo_root)
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            return merge_base.stdout.strip(), f"merge-base com {candidate}"
    return None, "sem base local (origin/main indisponível)"


def append_only_violations(base: str, repo_root: Path | None = None) -> list[tuple[str, str]]:
    diff = _git(
        ["diff", "--name-status", "--no-renames", base, "HEAD"],
        cwd=repo_root,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"git diff contra '{base}' falhou: {diff.stderr.strip()}")
    return classify_append_only(diff.stdout.splitlines())


# ---------------------------------------------------------------------------
# Check 2 (hosted by check_migrations.py) — destructive ops need a marker
# ---------------------------------------------------------------------------


def destructive_operations(source: str) -> list[str]:
    """Names of destructive migration operations found in ``source`` (via AST)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # An unparseable migration will fail elsewhere; report every candidate
        # name the raw text mentions so the gate stays fail-closed.
        return sorted(op for op in DESTRUCTIVE_OPERATIONS if op in source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in DESTRUCTIVE_OPERATIONS:
            found.append(name)
    return sorted(set(found))


def has_expand_contract_marker(source: str) -> bool:
    return EXPAND_CONTRACT_MARKER_RE.search(source) is not None


def migration_paths_added_since_tag(repo_root: Path | None = None) -> list[str]:
    """Tracked migration files that do not exist in the ``go-live-v1`` tree.

    Files present at the tag are the grandfathered baseline; everything after
    it must follow the expand-contract discipline.
    """
    baseline = _git(["ls-tree", "-r", "--name-only", GO_LIVE_TAG], cwd=repo_root)
    if baseline.returncode != 0:
        raise RuntimeError(
            f"tag {GO_LIVE_TAG} existe mas 'git ls-tree {GO_LIVE_TAG}' falhou: {baseline.stderr.strip()}"
        )
    baseline_paths = set(baseline.stdout.splitlines())
    current = _git(["ls-files"], cwd=repo_root)
    if current.returncode != 0:
        raise RuntimeError(f"git ls-files falhou: {current.stderr.strip()}")
    return [
        path
        for path in current.stdout.splitlines()
        if is_migration_file(path) and path not in baseline_paths
    ]


def expand_contract_violations(repo_root: Path | None = None) -> list[tuple[str, list[str]]]:
    """``(path, destructive_ops)`` for post-tag migrations missing the marker."""
    root = repo_root or Path.cwd()
    violations: list[tuple[str, list[str]]] = []
    for rel_path in migration_paths_added_since_tag(repo_root):
        try:
            source = (root / rel_path).read_text(encoding="utf-8")
        except OSError:
            continue
        ops = destructive_operations(source)
        if ops and not has_expand_contract_marker(source):
            violations.append((rel_path, ops))
    return violations


# ---------------------------------------------------------------------------
# Check 3 — DEPRECATED markers carry a deadline that has not passed
# ---------------------------------------------------------------------------


def evaluate_deprecated_marker(inner: str, today: datetime.date) -> str | None:
    """Return a violation reason for one ``DEPRECATED(...)`` payload, or None."""
    match = DEPRECATED_DEADLINE_RE.match(inner)
    if not match:
        return (
            f"marcador ilegível 'DEPRECATED({inner})' — o formato único é "
            "'# DEPRECATED(remove by YYYY-MM-DD)' (ADR-015)"
        )
    try:
        deadline = datetime.date.fromisoformat(match.group("date"))
    except ValueError:
        return (
            f"data inválida em 'DEPRECATED({inner})' — o formato único é "
            "'# DEPRECATED(remove by YYYY-MM-DD)' (ADR-015)"
        )
    if deadline < today:
        return f"prazo vencido em {deadline.isoformat()} — remova o código deprecated ou justifique um prazo novo"
    return None


def deprecated_violations(
    repo_root: Path | None = None, today: datetime.date | None = None
) -> list[tuple[str, str]]:
    """``(location, reason)`` for expired or malformed DEPRECATED markers."""
    today = today or datetime.date.today()
    grep = _git(
        ["grep", "-In", r"DEPRECATED(", "--", ".", *DEPRECATED_SCAN_EXCLUDES],
        cwd=repo_root,
    )
    if grep.returncode not in (0, 1):  # 1 = no matches
        raise RuntimeError(f"git grep falhou: {grep.stderr.strip()}")
    violations: list[tuple[str, str]] = []
    for line in grep.stdout.splitlines():
        parts = line.split(":", 2)  # git grep -In → path:lineno:content
        if len(parts) < 3:
            continue
        location = f"{parts[0]}:{parts[1]}"
        for match in DEPRECATED_MARKER_RE.finditer(parts[2]):
            reason = evaluate_deprecated_marker(match.group("inner"), today)
            if reason:
                violations.append((location, reason))
    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    del argv
    repo_root = Path.cwd()
    if not go_live_active(repo_root):
        print(f"check-adr015: {PRE_GO_LIVE_MESSAGE}")
        return 0

    failed = False
    print("check-adr015: política ADR-015 ATIVA (tag go-live-v1 presente)")

    base, base_description = resolve_diff_base(repo_root)
    if base is None:
        print(f"- [FAIL] adr015.append_only: base do diff não resolvida ({base_description})")
        failed = True
    else:
        try:
            violations = append_only_violations(base, repo_root)
        except RuntimeError as exc:
            print(f"- [FAIL] adr015.append_only: {exc}")
            failed = True
        else:
            if violations:
                failed = True
                print(f"- [FAIL] adr015.append_only ({base_description}): migrations são append-only pós go-live.")
                for status, path in violations:
                    print(f"    {status}\t{path}")
                print(
                    "    Nunca editar/remover migration existente: correção é migration NOVA "
                    "(ADR-015 §1, docs/guides/production-upgrades.md)."
                )
            else:
                print(f"- [OK] adr015.append_only: só adições em */migrations/ ({base_description}).")

    try:
        deprecated = deprecated_violations(repo_root)
    except RuntimeError as exc:
        print(f"- [FAIL] adr015.deprecated_deadline: {exc}")
        failed = True
    else:
        if deprecated:
            failed = True
            print("- [FAIL] adr015.deprecated_deadline: marcadores DEPRECATED vencidos ou ilegíveis.")
            for location, reason in deprecated:
                print(f"    {location}: {reason}")
        else:
            print("- [OK] adr015.deprecated_deadline: nenhum marcador DEPRECATED vencido ou ilegível.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
