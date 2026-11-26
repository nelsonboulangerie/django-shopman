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


# ── Shards por peso e trava do custo (DEV-2026-098: "não deixar a sacada se perder") ──

import check_test_cost  # noqa: E402
import test_shards  # noqa: E402


def test_particao_cobre_cada_arquivo_uma_vez_e_e_deterministica():
    files = [f"t/test_{i:03d}.py" for i in range(40)]
    weights = {f: float((i * 37) % 11 + 1) for i, f in enumerate(files)}
    for n in (1, 2, 3, 5):
        parts = test_shards.partition(files, n, weights)
        flat = [f for p in parts for f in p]
        assert sorted(flat) == files and len(flat) == len(set(flat))
        assert parts == test_shards.partition(list(reversed(files)), n, weights)


def test_particao_equilibra_pelo_peso_e_arquivo_novo_entra_com_a_mediana():
    weights = {"a.py": 100.0, "b.py": 60.0, "c.py": 40.0}
    parts = test_shards.partition(["a.py", "b.py", "c.py", "novo.py"], 2, weights)
    loads = [sum(weights.get(f, 60.0) for f in p) for p in parts]
    assert max(loads) - min(loads) <= 60.0
    assert any("novo.py" in p for p in parts)


def test_arquivo_listado_que_nao_existe_reprova_alto():
    with pytest.raises(SystemExit, match="não existe"):
        test_shards.expand(["shopman/backstage/tests/test_que_nao_existe.py"], [])


def _cost(monkeypatch, tmp_path, calls, baseline, seed_list=(), heavy_list=()):
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({"seed_calls": baseline}))
    monkeypatch.setattr(check_test_cost, "BASELINE", base)
    monkeypatch.setattr(check_test_cost, "seed_calls", lambda: calls)
    lists = {"BACKSTAGE_SEED_TESTS": list(seed_list), "BACKSTAGE_HEAVY_TESTS": list(heavy_list)}
    monkeypatch.setattr(check_test_cost, "make_list", lambda var: lists[var])
    monkeypatch.setattr(check_test_cost, "shard_specs", lambda: [])
    monkeypatch.setattr(check_test_cost, "load_weights", lambda path: {})
    monkeypatch.setattr(sys, "argv", ["check_test_cost.py"])
    return check_test_cost.main()


def test_trava_reprova_teste_novo_que_paga_o_seed_completo(monkeypatch, tmp_path, capsys):
    f = "shopman/shop/tests/test_novo.py"
    assert _cost(monkeypatch, tmp_path, {f: 1}, {}) == 1
    out = capsys.readouterr().out
    assert f in out and "--update" in out


def test_trava_reprova_quem_semeia_no_rest_do_backstage(monkeypatch, tmp_path, capsys):
    f = "shopman/backstage/tests/test_x.py"
    assert _cost(monkeypatch, tmp_path, {f: 1}, {f: 1}) == 1
    assert "BACKSTAGE_SEED_TESTS" in capsys.readouterr().out
    assert _cost(monkeypatch, tmp_path, {f: 1}, {f: 1}, seed_list=[f]) == 0


def test_trava_deixa_diminuir_e_pede_update(monkeypatch, tmp_path, capsys):
    f = "shopman/shop/tests/test_y.py"
    assert _cost(monkeypatch, tmp_path, {}, {f: 2}) == 0
    assert "--update" in capsys.readouterr().out


def test_trava_real_do_repositorio_passa():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "check_test_cost.py")], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_partes_concordam_entre_makefile_matriz_e_coverage_gate():
    """Mudar o número de partes num lugar só deixaria shard sem rodar ou cobertura faltando."""
    seed_parts = int(check_test_cost.make_list("BACKSTAGE_SEED_PARTS")[0])
    rest_parts = int(check_test_cost.make_list("BACKSTAGE_REST_PARTS")[0])
    heavy_parts = int(check_test_cost.make_list("BACKSTAGE_HEAVY_PARTS")[0])
    expected = (
        {f"seed-{k}" for k in range(1, seed_parts + 1)}
        | {f"rest-{k}" for k in range(1, rest_parts + 1)}
        | {f"heavy-{k}" for k in range(1, heavy_parts + 1)}
    )
    wf = yaml.safe_load((ROOT / ".github/workflows/runtime-gate.yml").read_text())
    assert set(wf["jobs"]["tests-backstage-shards"]["strategy"]["matrix"]["shard"]) == expected
    gate = next(s for s in wf["jobs"]["coverage-gate"]["steps"] if "COVERAGE_SHARDS" in (s.get("env") or {}))
    listed = set(gate["env"]["COVERAGE_SHARDS"].split())
    assert {f"backstage-{s}" for s in expected} <= listed
    shop_parts = int(check_test_cost.make_list("SHOP_REST_PARTS")[0])
    shop = {f"rest-{k}" for k in range(1, shop_parts + 1)} | {"heavy"}
    assert set(wf["jobs"]["tests-shop-shards"]["strategy"]["matrix"]["shard"]) == shop
    assert {f"shop-{s}" for s in shop} <= listed
    # nada além dos shards que existem: cobertura velha esperada travaria o gate
    assert listed == {"test-storefront"} | {f"backstage-{s}" for s in expected} | {f"shop-{s}" for s in shop}


# ── Piloto da Ubicloud: seletor dos jobs de navegador com teto (scripts/ci_browser_runner.py) ──

import ci_browser_runner as browser  # noqa: E402

PILOT = {"EVENT": "merge_group", "CI_BROWSER_RUNNER": "ubicloud-standard-4", "CI_BROWSER_SINCE": "2026-11-26T12:00:00Z"}


@pytest.mark.parametrize("env", [
    {**PILOT, "EVENT": "pull_request"},
    {**PILOT, "CI_BROWSER_RUNNER": ""},
    {**PILOT, "CI_BROWSER_SINCE": ""},
])
def test_seletor_fica_no_gratis_fora_da_fila_ou_sem_piloto(env, monkeypatch):
    monkeypatch.delenv("CI_LINUX_RUNNER", raising=False)
    runner, _ = browser.choose(env, lambda since: pytest.fail("não deve nem consultar a API"))
    assert runner == "ubuntu-latest"


def test_seletor_usa_o_piloto_dentro_do_orcamento():
    runner, reason = browser.choose({**PILOT, "CI_BROWSER_BUDGET_USD": "8"}, lambda since: 10)
    assert runner == "ubicloud-standard-4" and "US$ 3.00 de US$ 8.00" in reason


def test_seletor_volta_ao_gratis_ao_esgotar_o_orcamento(monkeypatch):
    monkeypatch.delenv("CI_LINUX_RUNNER", raising=False)
    # 27 grupos × 0,30 = 8,10 ≥ 8: grátis ANTES do corte de 10 da Ubicloud (que travaria a fila)
    runner, reason = browser.choose({**PILOT, "CI_BROWSER_BUDGET_USD": "8"}, lambda since: 27)
    assert runner == "ubuntu-latest" and "esgotado" in reason


def test_seletor_erro_de_api_vira_gratis(monkeypatch):
    monkeypatch.delenv("CI_LINUX_RUNNER", raising=False)

    def boom(since):
        raise TimeoutError("api")

    runner, reason = browser.choose(PILOT, boom)
    assert runner == "ubuntu-latest" and "erro" in reason


def test_jobs_do_piloto_nunca_pulam_check_obrigatorio():
    """`needs: scope` + `!cancelled()`: scope que falha não pode PULAR check obrigatório (contaria verde)."""
    wf = yaml.safe_load((ROOT / ".github/workflows/omotenashi-gate.yml").read_text())
    for job in ("omotenashi-browser-qa", "storefront-e2e"):
        assert "!cancelled()" in wf["jobs"][job]["if"]
        assert "|| vars.CI_LINUX_RUNNER || 'ubuntu-latest'" in wf["jobs"][job]["runs-on"]


class _FakeGh:
    def __init__(self, open_issue=""):
        self.open_issue, self.calls = open_issue, []

    def __call__(self, *args):
        self.calls.append(args)
        return self.open_issue if args[:2] == ("issue", "list") else ""


def test_queda_nao_pedida_abre_uma_issue_so():
    env = {**PILOT, "ALERT": "true", "REASON": "orçamento do piloto esgotado: …", "RUN_URL": "u"}
    gh = _FakeGh()
    assert browser.notify(env, gh) == "issue aberta"
    assert any(c[:2] == ("issue", "create") for c in gh.calls)
    gh2 = _FakeGh(open_issue="77")  # já existe: não duplica nem comenta a cada grupo
    assert browser.notify(env, gh2) == "estado já registrado: nada a fazer"
    assert not any(c[:2] in {("issue", "create"), ("issue", "comment")} for c in gh2.calls)


def test_queda_chega_ao_dono_atribuida():
    env = {**PILOT, "ALERT": "true", "RUN_URL": "u", "ASSIGNEE": "dono"}
    gh = _FakeGh()
    assert browser.notify(env, gh) == "issue aberta, atribuída a dono"
    create = next(c for c in gh.calls if c[:2] == ("issue", "create"))
    assert create[-2:] == ("--assignee", "dono")


def test_atribuir_que_falha_nao_cala_o_aviso():
    class _Recusa(_FakeGh):
        def __call__(self, *args):
            if "--assignee" in args:
                raise RuntimeError("could not assign user")
            return super().__call__(*args)

    gh = _Recusa()
    env = {**PILOT, "ALERT": "true", "RUN_URL": "u", "ASSIGNEE": "fulano"}
    assert browser.notify(env, gh) == "issue aberta"
    assert any(c[:2] == ("issue", "create") and "--assignee" not in c for c in gh.calls)


def test_voltou_ao_pago_fecha_a_issue():
    gh = _FakeGh(open_issue="77")
    assert browser.notify({**PILOT, "ALERT": "false", "RUN_URL": "u"}, gh) == "issue #77 fechada"
    assert ("issue", "close", "77") in gh.calls


def test_passo_de_escolha_que_falhou_tambem_alarma():
    gh = _FakeGh()  # sem ALERT: a escolha falhou e não deixou saída
    assert browser.notify({**PILOT, "RUN_URL": "u"}, gh) == "issue aberta"


def test_piloto_desligado_nao_alarma():
    gh = _FakeGh()
    assert "nada a avisar" in browser.notify({**PILOT, "CI_BROWSER_RUNNER": "", "ALERT": "true"}, gh)
    assert gh.calls == []


def test_alert_sai_quando_ligado_e_caiu(monkeypatch, capsys):
    monkeypatch.setattr(browser, "groups_since", lambda *a: 99)
    for k, v in {**PILOT, "CI_BROWSER_BUDGET_USD": "8"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(sys, "argv", ["ci_browser_runner.py"])
    browser.main()
    out = capsys.readouterr().out
    assert "alert=true" in out and "runner=ubuntu-latest" in out


def test_ready_nunca_chama_de_verde_a_evidencia_vermelha():
    ok = {"level": "preflight", "status": "pass", "seconds": 1, "started_at": "t"}
    assert "verde" in local_ci.evidence_line(ok, "a" * 40)
    for ev in ({**ok, "status": "fail"}, {**ok, "level": "fast"}, {**ok, "status": "stale"}, None):
        line = local_ci.evidence_line(ev, "a" * 40)
        assert "verde" not in line and "exceção declarada" in line


def test_fetch_do_ready_tenta_de_novo_quando_outro_processo_trava_o_ref(monkeypatch):
    calls = []

    def flaky_git(*args, **kwargs):
        calls.append(args)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, "git fetch", "", "cannot lock ref")
        return ""

    monkeypatch.setattr(local_ci, "git", flaky_git)
    monkeypatch.setattr(local_ci.time, "sleep", lambda s: None)
    local_ci.fetch_main(Path("."))
    assert len(calls) == 3
