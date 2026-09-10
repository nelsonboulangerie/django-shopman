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


def test_deprecated_violations_scan_tracked_files(tagged_repo):
    (tagged_repo / "app" / "compat.py").write_text(
        "OLD_NAME = NEW_NAME  # DEPRECATED(remove by 2026-01-01)\n"
        "STILL_OK = 1  # DEPRECATED(remove by 2099-01-01)\n"
    )
    _git(tagged_repo, "add", "app/compat.py")
    _git(tagged_repo, "commit", "--quiet", "-m", "compat alias")

    violations = check_adr015.deprecated_violations(tagged_repo, today=_TODAY)
    assert [(loc, "vencido" in reason) for loc, reason in violations] == [("app/compat.py:1", True)]


# ---------------------------------------------------------------------------
# resolve_diff_base — a base do diff não pode ser a ponta que anda
# ---------------------------------------------------------------------------
#
# Medido no PR #554: o #549 entrou no main entre o push e o job. A ponta da
# base andou, o merge ref (gerado no push, e nunca refeito) não, e o diff
# passou a mostrar as mudanças do PR alheio AO CONTRÁRIO — o gate reprovou
# apontando um arquivo que aquele PR nunca abriu. Este bloco monta o cenário.


def _pull_request_scenario(tmp_path, *, move_base: bool, shallow: bool):
    """Origem + merge ref publicado no push; opcionalmente a base anda depois."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "--quiet", "--bare", "-b", "main")

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "--quiet", "-b", "main")
    (work / "apps.py").write_text("x = 1\n")
    _git(work, "add", "apps.py")
    _git(work, "commit", "--quiet", "-m", "base")
    base_sha = _git(work, "rev-parse", "HEAD").strip()

    _git(work, "checkout", "--quiet", "-b", "feature")
    (work / "feature.py").write_text("y = 2\n")
    _git(work, "add", "feature.py")
    _git(work, "commit", "--quiet", "-m", "o que ESTE PR fez")
    head_sha = _git(work, "rev-parse", "HEAD").strip()

    # O merge sintético que o GitHub publica em refs/pull/N/merge, no push.
    _git(work, "checkout", "--quiet", base_sha)
    _git(work, "merge", "--quiet", "--no-ff", "-m", "Merge pull request", head_sha)
    merge_sha = _git(work, "rev-parse", "HEAD").strip()
    _git(work, "update-ref", "refs/pull/1/merge", merge_sha)

    _git(work, "checkout", "--quiet", "main")
    moved_tip = base_sha
    if move_base:
        # A base anda DEPOIS: outro PR entra e mexe num arquivo alheio.
        (work / "apps.py").write_text("x = 1\nz = 3  # o PR alheio\n")
        _git(work, "add", "apps.py")
        _git(work, "commit", "--quiet", "-m", "PR alheio entrou no main")
        moved_tip = _git(work, "rev-parse", "HEAD").strip()
    _git(work, "push", "--quiet", str(origin), "main", "refs/pull/1/merge:refs/pull/1/merge")

    runner = tmp_path / "runner"
    runner.mkdir()
    _git(runner, "init", "--quiet")
    _git(runner, "remote", "add", "origin", str(origin))
    depth = ["--depth=1"] if shallow else []
    _git(runner, "fetch", "--quiet", *depth, "origin", "refs/pull/1/merge")
    # A ponta da base também chega ao runner — era ela que a versão anterior
    # usava como base do diff, e é contra ela que a prova do defeito corre.
    _git(runner, "fetch", "--quiet", *depth, "origin", "main")
    _git(runner, "checkout", "--quiet", merge_sha)

    return runner, {"base": base_sha, "head": head_sha, "merge": merge_sha, "moved_tip": moved_tip}


@pytest.fixture
def moved_base_repo(tmp_path):
    """Um PR cujo merge ref ficou para trás porque a base andou depois do push."""
    return _pull_request_scenario(tmp_path, move_base=True, shallow=False)


def _arm_pull_request_event(monkeypatch, tmp_path, shas, *, base_sha=None, head_sha=None):
    payload = tmp_path / "event.json"
    payload.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": shas["base"] if base_sha is None else base_sha, "ref": "main"},
                    "head": {"sha": shas["head"] if head_sha is None else head_sha},
                }
            }
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(payload))


def test_a_ponta_da_base_acusa_o_arquivo_do_pr_alheio(moved_base_repo):
    """A prova do defeito, antes do remédio: contra a ponta, o alheio aparece.

    Sem esta asserção o teste seguinte poderia estar verde por acaso — é ela
    que demonstra que o cenário reproduz a reprovação medida no PR #554.
    """
    runner, shas = moved_base_repo
    diff = _git(runner, "diff", "--name-status", "--no-renames", shas["moved_tip"], "HEAD")
    assert "apps.py" in diff, "contra a ponta, o arquivo do PR alheio aparece — e ao contrário"


def test_base_movida_nao_contamina_o_diff(moved_base_repo, monkeypatch, tmp_path):
    """A base é o commit sobre o qual o merge ref foi montado, não a ponta."""
    runner, shas = moved_base_repo
    _arm_pull_request_event(monkeypatch, tmp_path, shas)

    base, description = check_adr015.resolve_diff_base(runner)

    assert base == shas["base"], "a base tem de ser o commit do merge ref, não a ponta que andou"
    assert base != shas["moved_tip"]
    assert "merge ref" in description

    diff = _git(runner, "diff", "--name-status", "--no-renames", base, "HEAD").split()
    assert diff == ["A", "feature.py"], "o diff só pode ter o arquivo deste PR"


def test_checkout_raso_ainda_resolve_a_base(tmp_path, monkeypatch):
    """`fetch-depth: 1` esconde os pais na revision walk; o objeto os mantém.

    O job `quality` faz checkout raso. Ali `rev-list --parents` e `HEAD^1`
    voltam vazios por causa do enxerto do shallow, e um gate que dependesse
    deles reprovaria todo PR — ou, pior, passaria vendo zero arquivo.
    """
    runner, shas = _pull_request_scenario(tmp_path, move_base=False, shallow=True)
    assert (runner / ".git" / "shallow").exists(), "o cenário precisa ser mesmo raso"
    _arm_pull_request_event(monkeypatch, tmp_path, shas)

    base, _ = check_adr015.resolve_diff_base(runner)

    assert base == shas["base"]
    diff = _git(runner, "diff", "--name-status", "--no-renames", base, "HEAD").split()
    assert diff == ["A", "feature.py"]


def test_base_irresolvivel_devolve_none_em_vez_de_chutar(moved_base_repo, monkeypatch, tmp_path):
    """Sem base confiável o gate não chuta: devolve None e o chamador reprova.

    Aqui HEAD não é o merge ref (o `head.sha` do evento não bate com o pai 2),
    o `base.sha` do evento não existe, e o remoto sumiu. A resposta certa é
    "não sei", nunca a ponta de alguma coisa.
    """
    runner, shas = moved_base_repo
    _git(runner, "remote", "remove", "origin")
    _arm_pull_request_event(monkeypatch, tmp_path, shas, base_sha="0" * 40, head_sha="1" * 40)

    base, description = check_adr015.resolve_diff_base(runner)

    assert base is None
    assert "não resolvida" in description
    assert "merge ref" in description


def test_merge_group_continua_usando_o_base_sha_da_fila(moved_base_repo, monkeypatch, tmp_path):
    runner, shas = moved_base_repo
    payload = tmp_path / "merge_group.json"
    payload.write_text(json.dumps({"merge_group": {"base_sha": shas["base"]}}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(payload))

    base, description = check_adr015.resolve_diff_base(runner)

    assert base == shas["base"]
    assert "merge_group" in description


def test_merge_group_sem_o_commit_reprova(moved_base_repo, monkeypatch, tmp_path):
    runner, _shas = moved_base_repo
    _git(runner, "remote", "remove", "origin")
    payload = tmp_path / "merge_group.json"
    payload.write_text(json.dumps({"merge_group": {"base_sha": "0" * 40}}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(payload))

    base, description = check_adr015.resolve_diff_base(runner)

    assert base is None
    assert "indisponível" in description


def test_append_only_reprova_quando_a_base_nao_resolve(monkeypatch, capsys, tmp_path):
    """O gate do ADR-015 falha FECHADO — nunca verde por não ter olhado nada."""
    monkeypatch.setenv("SHOPMAN_ADR015_FORCE", "1")
    monkeypatch.setattr(
        check_adr015,
        "resolve_diff_base",
        lambda *a, **k: (None, "base do PR não resolvida — remoto indisponível"),
    )
    monkeypatch.setattr(check_adr015, "deprecated_violations", lambda *a, **k: [])
    monkeypatch.chdir(tmp_path)

    assert check_adr015.main([]) == 1
    saida = capsys.readouterr().out
    assert "FAIL" in saida
    assert "base do diff não resolvida" in saida
