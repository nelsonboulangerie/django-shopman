"""CI local-first (DEV-2026-098): o executor imita a CI sem inventar lista.

Sem Django: roda com ``-p no:django``, como os outros testes de ``scripts/``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import ci_baseline  # noqa: E402
import local_ci  # noqa: E402

yaml = pytest.importorskip("yaml")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "old.py").write_text("y = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_diff_pega_o_que_nao_foi_commitado_e_os_dois_lados_da_renomeacao(repo, monkeypatch):
    _git(repo, "checkout", "-qb", "frente")
    _git(repo, "mv", "old.py", "new.py")
    (repo / "a.py").write_text("x = 2\n")  # sujo, sem commit
    (repo / "novo.py").write_text("z = 1\n")  # não rastreado
    diff = local_ci.compute_diff(repo, "main")
    assert {"a.py", "old.py", "new.py", "novo.py"} <= set(diff.files)
    assert "old.py" in diff.deleted


def test_hash_da_arvore_e_o_do_commit_que_contem_exatamente_o_testado(repo):
    (repo / "a.py").write_text("x = 3\n")
    (repo / "b.py").write_text("b = 1\n")
    tested = local_ci.working_tree_hash(repo)
    assert _git(repo, "status", "--porcelain")  # índice real intocado
    _git(repo, "add", "a.py", "b.py")
    _git(repo, "commit", "-qm", "frente")
    assert _git(repo, "rev-parse", "HEAD^{tree}") == tested
    (repo / "c.py").write_text("c = 1\n")  # qualquer byte a mais invalida
    assert local_ci.working_tree_hash(repo) != tested


def test_espelho_do_workflow_adapta_sem_inventar(tmp_path):
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text(
        yaml.safe_dump(
            {
                "jobs": {
                    "q": {
                        "name": "Quality",
                        "steps": [
                            {"uses": "actions/checkout@v7"},
                            {"name": "Create virtualenv", "run": "python -m venv .venv"},
                            {"name": "Lint", "run": ".venv/bin/ruff check ."},
                            {"name": "Tag", "run": "git fetch --force --depth=1 origin tag go-live-v1 || true"},
                            {"name": "Guard", "run": "python -m pip install --quiet pyyaml\npython scripts/g.py"},
                            {"name": "Make", "run": "make test-migrations"},
                            {"name": "So no PR", "if": "github.event_name == 'pull_request'", "run": "echo"},
                            {"name": "Expr", "run": 'echo "${{ github.sha }}"'},
                            {"name": "PG", "env": {"DATABASE_URL": "postgres://x"}, "run": "manage.py check"},
                        ],
                    }
                }
            }
        )
    )
    py = Path("/v/bin/python")
    remote: list[str] = []
    steps = {s.name.split(" › ")[1]: s for s in local_ci.mirror_job(tmp_path, py, "x.yml", "q", remote)}
    assert set(steps) == {"Lint", "Tag", "Guard", "Make"}
    assert "/v/bin/ruff check ." in steps["Lint"].cmd
    assert "--depth" not in steps["Tag"].cmd  # o .git é de todas as worktrees
    assert "pip install" not in steps["Guard"].cmd and "/v/bin/python scripts/g.py" in steps["Guard"].cmd
    assert "make PYTHON=/v/bin/python test-migrations" in steps["Make"].cmd
    assert any("So no PR" in r for r in remote)
    assert any("Expr" in r for r in remote)
    assert any("PG" in r and "PostgreSQL" in r for r in remote)


def test_espelho_le_os_jobs_reais_que_o_executor_usa():
    py = Path("/v/bin/python")
    for workflow, job in (
        ("runtime-gate.yml", "quality"),
        ("runtime-gate.yml", "silent-swallow-gate"),
        ("runtime-gate.yml", "admin-gate"),
        ("surfaces-gate.yml", "surface-versions"),
    ):
        steps = local_ci.mirror_job(ROOT, py, workflow, job, [])
        assert steps, f"{workflow}#{job} sumiu ou mudou de forma: o executor local perderia paridade"


def test_testes_focados_por_modulo_e_por_pacote():
    found = local_ci.focused_tests(ROOT, ["scripts/ci_scope.py", "packages/utils/shopman/utils/monetary.py"])
    assert "scripts/tests/test_ci_scope.py" in found["."]
    # Core: a suíte inteira do pacote — quem testa format_money é test_money_field.py
    assert found["packages/utils"] == ["."]


def test_testes_focados_incluem_quem_importa_o_modulo():
    found = local_ci.focused_tests(ROOT, ["shopman/shop/lifecycle.py"])
    hits = found["."]
    assert any(h.endswith("test_lifecycle.py") or "lifecycle" in h for h in hits)
    assert all(h.startswith("shopman/") for h in hits)


def test_plano_doc_so_e_leve_e_nao_roda_suite_python(monkeypatch):
    diff = local_ci.Diff("origin/main", "0" * 40, ["docs/x.md"], [], "t" * 40)
    plan = local_ci.build_plan(ROOT, Path("/v/bin/python"), "impact", diff, 4)
    names = [s.name for s in plan.steps]
    assert not any(n.startswith("Testes (") for n in names)
    assert any(n.startswith("Quality + deploy contract") for n in names)


def test_preflight_de_core_alcanca_shop_e_backstage():
    diff = local_ci.Diff("origin/main", "0" * 40, ["packages/refs/shopman/refs/registry.py"], [], "t" * 40)
    plan = local_ci.build_plan(ROOT, Path("/v/bin/python"), "preflight", diff, 4)
    names = [s.name for s in plan.steps]
    assert "Testes (test-shop) — fila" in names and "Testes (test-backstage) — fila" in names
    assert any("Coverage Gate" in r for r in plan.remote)


def test_migracao_com_numero_repetido_reprova(tmp_path, capsys):
    mig = tmp_path / "app/migrations"
    mig.mkdir(parents=True)
    (mig / "0002_a.py").write_text("")
    (mig / "0002_b.py").write_text("")
    assert local_ci.cmd_migrations(tmp_path) == 1
    assert "0002" in capsys.readouterr().out


def test_baseline_da_fila_mede_o_grupo_pelo_ultimo_gate():
    def run(name, created, updated, conclusion="success"):
        return {"name": name, "head_branch": "gh-readonly-queue/main/pr-1-x", "head_sha": "s", "status": "completed",
                "conclusion": conclusion, "created_at": created, "updated_at": updated, "run_started_at": created}

    rep = ci_baseline.analyse_queue([
        run("Runtime Gate", "2026-11-25T10:00:00Z", "2026-11-25T10:20:00Z"),
        run("Surfaces Gate", "2026-11-25T10:00:00Z", "2026-11-25T10:16:00Z"),
        run("Cache do main (Playwright e npm)", "2026-11-25T10:00:00Z", "2026-11-25T11:00:00Z"),
    ])
    assert rep["outcome"] == {"success": 1}
    assert rep["success_wall"]["p50_min"] == 20.0
    assert rep["critical_path_last_to_finish"] == {"Runtime Gate": 1}
    json.dumps(rep)  # serializável para o --json


# ── Hook de promoção (scripts/preflight_merge_guard.py) ──────────────────

import preflight_merge_guard as guard  # noqa: E402


@pytest.fixture
def evidence_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOPMAN_LOCAL_CI_HOME", str(tmp_path))
    (tmp_path / "evidence").mkdir()

    def fake_gh(*args):
        if args[:2] == ("pr", "view"):
            return json.dumps({"number": 7, "headRefOid": "c" * 40, "isDraft": False})
        if args[0] == "api":
            return "t" * 40
        raise AssertionError(args)

    monkeypatch.setattr(guard, "gh", fake_gh)
    return tmp_path


@pytest.mark.parametrize("cmd", ["git status", "gh pr view 7", "gh pr merge 7 --disable-auto", "gh pr merge 7 -R outro/repo --auto"])
def test_hook_ignora_o_que_nao_promove(cmd, evidence_home):
    assert guard.decide(cmd)[0]


def test_hook_barra_merge_sem_evidencia_e_ensina_o_caminho(evidence_home):
    ok, msg = guard.decide("gh pr merge 7 --auto --merge")
    assert not ok and "make preflight && make ready pr=7" in msg and "SHOPMAN_SEM_PREFLIGHT" in msg


def test_hook_deixa_passar_com_preflight_verde_da_arvore(evidence_home):
    (evidence_home / "evidence" / ("t" * 40 + ".json")).write_text(json.dumps({"level": "preflight", "status": "pass"}))
    assert guard.decide("cd x && gh pr merge 7 --auto --merge")[0]


@pytest.mark.parametrize("level,status", [("impact", "pass"), ("preflight", "fail"), ("preflight", "stale")])
def test_hook_nao_aceita_evidencia_fraca(evidence_home, level, status):
    (evidence_home / "evidence" / ("t" * 40 + ".json")).write_text(json.dumps({"level": level, "status": status}))
    assert not guard.decide("gh pr merge 7 --auto")[0]


def test_hook_registra_o_motivo_de_quem_promove_sem_preflight(evidence_home):
    assert guard.decide('SHOPMAN_SEM_PREFLIGHT="hotfix do caixa" gh pr merge 7 --auto')[0]
    line = json.loads((evidence_home / "overrides.jsonl").read_text().splitlines()[-1])
    assert line["reason"] == "hotfix do caixa" and line["pr"] == "7"


def test_hook_falha_aberto_sem_gh(evidence_home, monkeypatch):
    def boom(*args):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(guard, "gh", boom)
    assert guard.decide("gh pr merge 7 --auto")[0]


def test_comparacao_de_runner_agrupa_o_benchmark_pelo_alvo(monkeypatch):
    def run(i, name):
        return {"id": i, "name": name, "status": "completed"}

    jobs = {
        1: [
            {"name": "test-backstage-rest · ubuntu-latest · 1", "conclusion": "success", "labels": ["ubuntu-latest"],
             "started_at": "2026-11-25T10:00:00Z", "completed_at": "2026-11-25T10:14:00Z"},
            {"name": "test-backstage-rest · ubicloud-standard-8 · 1", "conclusion": "success", "labels": ["ubicloud-standard-8"],
             "started_at": "2026-11-25T10:00:00Z", "completed_at": "2026-11-25T10:07:00Z"},
            {"name": "test-shop-rest · ubuntu-latest · 1", "conclusion": "failure", "labels": ["ubuntu-latest"],
             "started_at": "2026-11-25T10:00:00Z", "completed_at": "2026-11-25T10:09:00Z"},
        ]
    }
    monkeypatch.setattr(ci_baseline, "jobs_for_run", lambda cache, rid: jobs[rid])
    rows = ci_baseline.compare_runners(None, [run(1, "Benchmark de runner")])
    assert len(rows) == 1  # job vermelho e job em um runner só não entram
    row = rows[0]
    assert row["job"] == "test-backstage-rest" and row["reference"] == "ubuntu-latest"
    assert row["runners"]["ubicloud-standard-8"]["speedup"] == 2.0
