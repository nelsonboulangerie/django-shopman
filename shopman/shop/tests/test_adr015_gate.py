"""ADR-015 enforcement gate — the policy runs as code, these tests prove it.

Covers the three post-go-live checks:

- append-only migrations (diff classification + temp-repo integration),
- destructive migration operations need the expand-contract marker,
- DEPRECATED markers carry a valid, unexpired deadline.

The scripts live outside the package tree, so the module is loaded by path.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_adr015.py"
_spec = importlib.util.spec_from_file_location("check_adr015", _SCRIPT)
check_adr015 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_adr015)


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def test_force_env_arms_the_policy(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADR015_FORCE", "1")
    assert check_adr015.go_live_active() is True


def test_force_env_disarms_the_policy(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADR015_FORCE", "0")
    assert check_adr015.go_live_active() is False


def test_policy_is_inactive_without_the_tag(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPMAN_ADR015_FORCE", raising=False)
    _git(tmp_path, "init", "--quiet")
    assert check_adr015.go_live_active(tmp_path) is False


# ---------------------------------------------------------------------------
# Append-only classification (pure)
# ---------------------------------------------------------------------------


def test_added_migration_is_allowed():
    lines = ["A\tpackages/offerman/shopman/offerman/migrations/0002_new.py"]
    assert check_adr015.classify_append_only(lines) == []


def test_modified_migration_is_a_violation():
    lines = ["M\tpackages/offerman/shopman/offerman/migrations/0001_initial.py"]
    assert check_adr015.classify_append_only(lines) == [
        ("M", "packages/offerman/shopman/offerman/migrations/0001_initial.py")
    ]


def test_deleted_migration_is_a_violation():
    lines = ["D\tshopman/shop/migrations/0003_gone.py"]
    assert check_adr015.classify_append_only(lines) == [("D", "shopman/shop/migrations/0003_gone.py")]


def test_non_migration_changes_are_ignored():
    lines = [
        "M\tshopman/shop/services/stock.py",
        "D\tdocs/guides/old.md",
        "M\tpackages/offerman/shopman/offerman/migrations/__init__.py",
    ]
    assert check_adr015.classify_append_only(lines) == []


# ---------------------------------------------------------------------------
# Destructive operation detection (AST)
# ---------------------------------------------------------------------------

_DESTRUCTIVE_SNIPPETS = {
    "RemoveField": "migrations.RemoveField(model_name='order', name='note')",
    "DeleteModel": "migrations.DeleteModel(name='LegacyThing')",
    "RenameField": "migrations.RenameField(model_name='order', old_name='note', new_name='observation')",
    "RenameModel": "migrations.RenameModel(old_name='Old', new_name='New')",
    "AlterField": "migrations.AlterField(model_name='order', name='note', field=models.TextField())",
}


def _migration_source(operation_line: str, marker: str = "") -> str:
    return (
        "from django.db import migrations, models\n"
        f"{marker}"
        "\n\nclass Migration(migrations.Migration):\n"
        "    dependencies = []\n"
        "    operations = [\n"
        f"        {operation_line},\n"
        "    ]\n"
    )


@pytest.mark.parametrize("op_name", sorted(_DESTRUCTIVE_SNIPPETS))
def test_each_destructive_operation_is_detected(op_name):
    source = _migration_source(_DESTRUCTIVE_SNIPPETS[op_name])
    assert check_adr015.destructive_operations(source) == [op_name]


def test_additive_operations_are_not_destructive():
    source = _migration_source(
        "migrations.AddField(model_name='order', name='observation', field=models.TextField(null=True))"
    )
    assert check_adr015.destructive_operations(source) == []


def test_unparseable_source_falls_back_to_text_scan():
    source = "def broken(:\n    migrations.RemoveField(model_name='x', name='y')"
    assert check_adr015.destructive_operations(source) == ["RemoveField"]


# ---------------------------------------------------------------------------
# Expand-contract marker format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        "# expand-contract: contract — docs/plans/RENAME-NOTE-PLAN.md\n",
        "# expand-contract: expand - PR #999\n",
        "#expand-contract: backfill -- docs/plans/X.md\n",
    ],
)
def test_valid_markers_are_accepted(marker):
    assert check_adr015.has_expand_contract_marker(_migration_source("migrations.RunPython(lambda a, b: None)", marker))


@pytest.mark.parametrize(
    "marker",
    [
        "",
        "# expand-contract:\n",  # no phase
        "# expand-contract: demolition — plano\n",  # unknown phase
        "# expand-contract: contract\n",  # phase without a plan reference
    ],
)
def test_missing_or_malformed_markers_are_rejected(marker):
    source = _migration_source("migrations.RunPython(lambda a, b: None)", marker)
    assert not check_adr015.has_expand_contract_marker(source)


# ---------------------------------------------------------------------------
# DEPRECATED deadline evaluation
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 8, 26)


def test_future_deadline_passes():
    assert check_adr015.evaluate_deprecated_marker("remove by 2026-10-01", _TODAY) is None


def test_deadline_today_still_passes():
    assert check_adr015.evaluate_deprecated_marker("remove by 2026-08-26", _TODAY) is None


def test_past_deadline_fails():
    reason = check_adr015.evaluate_deprecated_marker("remove by 2026-08-25", _TODAY)
    assert reason is not None and "vencido" in reason


@pytest.mark.parametrize("inner", ["remove in v1.2", "remove by soon", "remove by 2026-13-99", ""])
def test_malformed_markers_fail(inner):
    reason = check_adr015.evaluate_deprecated_marker(inner, _TODAY)
    assert reason is not None and "formato" in reason


# ---------------------------------------------------------------------------
# Temp-repo integration — the tag baseline and the git plumbing
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
        },
    )
    return result.stdout


@pytest.fixture
def tagged_repo(tmp_path):
    """A repo with one migration committed at the go-live-v1 tag."""
    repo = tmp_path / "repo"
    migrations = repo / "app" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "__init__.py").write_text("")
    (migrations / "0001_initial.py").write_text(
        _migration_source("migrations.DeleteModel(name='PreTagLeftover')")
    )
    _git(repo, "init", "--quiet")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "baseline")
    _git(repo, "tag", "go-live-v1")
    return repo


def test_migrations_at_the_tag_are_grandfathered(tagged_repo):
    assert check_adr015.migration_paths_added_since_tag(tagged_repo) == []
    assert check_adr015.expand_contract_violations(tagged_repo) == []


def test_new_destructive_migration_without_marker_is_a_violation(tagged_repo):
    new = tagged_repo / "app" / "migrations" / "0002_contract.py"
    new.write_text(_migration_source("migrations.RemoveField(model_name='order', name='note')"))
    _git(tagged_repo, "add", "app/migrations/0002_contract.py")
    _git(tagged_repo, "commit", "--quiet", "-m", "contract")

    assert check_adr015.migration_paths_added_since_tag(tagged_repo) == ["app/migrations/0002_contract.py"]
    assert check_adr015.expand_contract_violations(tagged_repo) == [
        ("app/migrations/0002_contract.py", ["RemoveField"])
    ]


def test_marker_clears_the_new_destructive_migration(tagged_repo):
    new = tagged_repo / "app" / "migrations" / "0002_contract.py"
    new.write_text(
        _migration_source(
            "migrations.RemoveField(model_name='order', name='note')",
            marker="# expand-contract: contract — docs/plans/RENAME-NOTE-PLAN.md\n",
        )
    )
    _git(tagged_repo, "add", "app/migrations/0002_contract.py")
    _git(tagged_repo, "commit", "--quiet", "-m", "contract with marker")

    assert check_adr015.expand_contract_violations(tagged_repo) == []


def test_new_additive_migration_needs_no_marker(tagged_repo):
    new = tagged_repo / "app" / "migrations" / "0002_expand.py"
    new.write_text(
        _migration_source(
            "migrations.AddField(model_name='order', name='observation', field=models.TextField(null=True))"
        )
    )
    _git(tagged_repo, "add", "app/migrations/0002_expand.py")
    _git(tagged_repo, "commit", "--quiet", "-m", "expand")

    assert check_adr015.expand_contract_violations(tagged_repo) == []


def test_append_only_violations_against_an_explicit_base(tagged_repo):
    base = _git(tagged_repo, "rev-parse", "HEAD").strip()
    migration = tagged_repo / "app" / "migrations" / "0001_initial.py"
    migration.write_text(migration.read_text() + "\n# edited after apply\n")
    (tagged_repo / "app" / "migrations" / "0002_new.py").write_text(
        _migration_source("migrations.RunPython(lambda a, b: None)")
    )
    _git(tagged_repo, "add", "-A")
    _git(tagged_repo, "commit", "--quiet", "-m", "edit an applied migration")

    violations = check_adr015.append_only_violations(base, tagged_repo)
    assert violations == [("M", "app/migrations/0001_initial.py")]


# ---------------------------------------------------------------------------
# resolve_diff_base — the base must be the commit HEAD was built on
# ---------------------------------------------------------------------------


@pytest.fixture
def pr_repo(tmp_path):
    """A repo shaped like a `pull_request` run, with the base moved afterwards.

    ``main`` gets a commit the PR author never touched (``app/alheio.py``) AFTER
    the synthetic merge ref was built — exactly the 08/09/2026 shape, when PR
    #549 landed between the push and the job of PR #554. Returns the repo plus
    the two commits the two possible answers point at.
    """
    repo = tmp_path / "pr"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "base.py").write_text("BASE = 1\n")
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "add", "app/base.py")
    _git(repo, "commit", "--quiet", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "--quiet", "-b", "pr")
    (repo / "app" / "meu.py").write_text("MEU = 1\n")
    _git(repo, "add", "app/meu.py")
    _git(repo, "commit", "--quiet", "-m", "o que o autor fez")
    head_pr = _git(repo, "rev-parse", "HEAD").strip()

    # The synthetic merge ref: PR merged onto the base as it was at push time.
    _git(repo, "checkout", "--quiet", "-b", "merge-ref", base_sha)
    _git(repo, "merge", "--quiet", "--no-ff", "-m", "merge ref", head_pr)
    merge_ref = _git(repo, "rev-parse", "HEAD").strip()

    # Someone else's PR lands. The merge ref is NOT rebuilt.
    _git(repo, "checkout", "--quiet", "main")
    (repo / "app" / "alheio.py").write_text("ALHEIO = 1\n")
    _git(repo, "add", "app/alheio.py")
    _git(repo, "commit", "--quiet", "-m", "PR de outra frente")
    tip_sha = _git(repo, "rev-parse", "HEAD").strip()

    _git(repo, "checkout", "--quiet", merge_ref)
    return repo, base_sha, tip_sha


def _pull_request_event(tmp_path: Path, base_sha: str) -> Path:
    payload = tmp_path / "pull_request.json"
    payload.write_text(json.dumps({"pull_request": {"base": {"sha": base_sha}}}))
    return payload


def test_pull_request_base_comes_from_the_payload_not_the_branch_tip(pr_repo, tmp_path, monkeypatch):
    """The base is the commit HEAD was built on, frozen at event time."""
    repo, base_sha, tip_sha = pr_repo
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(_pull_request_event(tmp_path, base_sha)))

    base, description = check_adr015.resolve_diff_base(repo)
    assert base == base_sha
    assert base != tip_sha
    assert base_sha[:12] in description


def test_moved_base_does_not_drag_someone_elses_pr_into_the_diff(pr_repo, tmp_path, monkeypatch):
    """The regression itself: the diff must show only what the author changed.

    Measured on 08/09/2026 — with the base branch TIP as the reference, the
    other PR's file shows up REVERSED (as a deletion), and the half-fix gate
    failed a PR over a file its author never opened. A required check that goes
    red because of someone else's PR teaches people to ignore red.
    """
    repo, base_sha, tip_sha = pr_repo
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(_pull_request_event(tmp_path, base_sha)))

    base, _ = check_adr015.resolve_diff_base(repo)
    changed = _git(repo, "diff", "--name-only", base, "HEAD").split()
    assert changed == ["app/meu.py"]

    # And the proof that the old answer was the bug, not a coincidence.
    contaminated = _git(repo, "diff", "--name-only", tip_sha, "HEAD").split()
    assert "app/alheio.py" in contaminated


def test_merge_group_base_still_comes_from_its_own_payload(pr_repo, tmp_path, monkeypatch):
    repo, base_sha, _ = pr_repo
    payload = tmp_path / "merge_group.json"
    payload.write_text(json.dumps({"merge_group": {"base_sha": base_sha}}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(payload))

    base, description = check_adr015.resolve_diff_base(repo)
    assert base == base_sha
    assert description.startswith("merge_group base_sha")


@pytest.mark.parametrize("event", ["pull_request", "merge_group"])
def test_unreadable_payload_fails_closed(pr_repo, tmp_path, monkeypatch, event):
    """No base is a FAIL, never an empty diff dressed up as green."""
    repo, _, _ = pr_repo
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "nao-existe.json"))

    base, description = check_adr015.resolve_diff_base(repo)
    assert base is None
    assert "GITHUB_EVENT_PATH" in description


def test_base_commit_that_cannot_be_fetched_fails_closed(pr_repo, tmp_path, monkeypatch):
    """A base SHA the repo cannot reach (force-pushed away) is a FAIL, not a guess."""
    repo, _, _ = pr_repo
    ausente = "0" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(_pull_request_event(tmp_path, ausente)))

    base, description = check_adr015.resolve_diff_base(repo)
    assert base is None
    assert "indisponível" in description


def test_local_run_still_uses_the_merge_base(pr_repo, monkeypatch):
    repo, base_sha, _ = pr_repo
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    base, description = check_adr015.resolve_diff_base(repo)
    assert base == base_sha
    assert description == "merge-base com main"


def test_deprecated_violations_scan_tracked_files(tagged_repo):
    (tagged_repo / "app" / "compat.py").write_text(
        "OLD_NAME = NEW_NAME  # DEPRECATED(remove by 2026-01-01)\n"
        "STILL_OK = 1  # DEPRECATED(remove by 2099-01-01)\n"
    )
    _git(tagged_repo, "add", "app/compat.py")
    _git(tagged_repo, "commit", "--quiet", "-m", "compat alias")

    violations = check_adr015.deprecated_violations(tagged_repo, today=_TODAY)
    assert [(loc, "vencido" in reason) for loc, reason in violations] == [("app/compat.py:1", True)]
