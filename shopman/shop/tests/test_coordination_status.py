"""`scripts/coordination_status.py` — a leitura de coordenação roda só com git.

O coordenador pode não ter `gh`; o comando tem de funcionar com um remoto qualquer,
inclusive com a fila de merge vazia (o caso comum). Os testes montam um remoto de
verdade numa pasta temporária: `main`, um branch sem PR, um PR aberto, um snapshot de
resgate e, quando o caso pede, a fila e o BOARD.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "coordination_status.py"

_spec = importlib.util.spec_from_file_location("coordination_status", SCRIPT)
status = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = status
_spec.loader.exec_module(status)

NOW = "2026-10-02T15:00:00+00:00"


def _git(cwd: Path, *args: str, when: str = "2026-10-02T14:00:00+00:00") -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout.strip()


def _commit(cwd: Path, name: str, when: str = "2026-10-02T14:00:00+00:00") -> str:
    (cwd / name).write_text(name)
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", f"add {name}", when=when)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def clone(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "remote", "add", "origin", str(origin))
    _commit(work, "base.txt", when="2026-09-01T10:00:00+00:00")
    _git(work, "push", "-q", "origin", "main")

    _git(work, "checkout", "-q", "-b", "feature/sem-pr")
    _commit(work, "invisivel.txt")
    _git(work, "push", "-q", "origin", "feature/sem-pr")

    _git(work, "checkout", "-q", "-b", "feature/com-pr", "main")
    pr_sha = _commit(work, "aberto.txt")
    _git(work, "push", "-q", "origin", "feature/com-pr")
    _git(work, "push", "-q", "origin", f"{pr_sha}:refs/pull/7/head")
    _git(work, "push", "-q", "origin", f"{pr_sha}:refs/pull/7/merge")

    _git(work, "checkout", "-q", "-b", "rescue/snapshot", "main")
    _commit(work, "snapshot.txt", when="2026-09-16T10:00:00+00:00")
    _git(work, "push", "-q", "origin", "rescue/snapshot")
    _git(work, "checkout", "-q", "main")

    monkeypatch.chdir(work)
    return work


def _run(capsys, *extra: str) -> tuple[int, str]:
    code = status.main(["--no-gh", "--now", NOW, *extra])
    return code, capsys.readouterr().out


def test_fila_vazia_nao_explode_e_mostra_o_estado(clone, tmp_path, capsys):
    code, out = _run(capsys, "--board", str(tmp_path / "nao-existe.md"))

    assert code == 0
    assert "== Fila de merge (gh-readonly-queue)\n   (vazia)" in out
    assert "#7 " in out  # PR aberto pelo ref de merge, sem gh
    assert "feature/sem-pr" in out.split("SEM PR")[1]
    assert "feature/com-pr" not in out.split("SEM PR")[1]
    assert "snapshots rescue/* (fora do resumo; triagem no BOARD): 1" in out
    assert "(sem BOARD)" in out
    assert out.rstrip().endswith("ATENÇÃO: branch sem PR")


def test_strict_sai_1_quando_ha_atencao(clone, tmp_path, capsys):
    code, _ = _run(capsys, "--strict", "--board", str(tmp_path / "nao-existe.md"))
    assert code == 1


def test_tudo_em_ordem_diz_ok(clone, tmp_path, capsys):
    _git(clone, "push", "-q", "origin", ":feature/sem-pr")
    code, out = _run(capsys, "--strict", "--board", str(tmp_path / "nao-existe.md"))
    assert code == 0
    assert out.rstrip().endswith("OK")


def test_fila_parada_e_reivindicacao_orfa(clone, tmp_path, capsys):
    _git(clone, "checkout", "-q", "-b", "fila", "main")
    queued = _commit(clone, "fila.txt", when="2026-10-02T12:00:00+00:00")
    _git(clone, "push", "-q", "origin", f"{queued}:refs/heads/gh-readonly-queue/main/pr-7-abc")
    board = tmp_path / "BOARD.md"
    board.write_text(
        "| id | frente | estado | sessão | branch / PR | desde (UTC) |\n"
        "|---|---|---|---|---|---|\n"
        "| R1 | velha | `EM_EXECUCAO` | s1 | — | 01/10 09:00 |\n"
        "| R2 | nova | `EM_EXECUCAO` | s2 | — | 2026-10-02 14:30 |\n"
        "| R3 | em PR | `EM_PR` | s3 | #7 | 01/10 01:00 |\n",
        encoding="utf-8",
    )

    _, out = _run(capsys, "--board", str(board))

    assert "gh-readonly-queue/main/pr-7-abc" in out
    orphans = out.split("Reivindicações órfãs")[1]
    assert "R1 | velha" in orphans
    assert "R2" not in orphans and "R3" not in orphans
    assert "fila parada há 3 h" in out
    assert "reivindicação órfã" in out.splitlines()[-1]


def test_pr_fechado_nao_esconde_o_branch(clone, tmp_path, capsys):
    """Head de PR fechado (sem ref de merge) não conta como PR: o branch aparece."""
    _git(clone, "checkout", "-q", "-b", "feature/fechado", "main")
    closed_sha = _commit(clone, "fechado.txt")
    _git(clone, "push", "-q", "origin", "feature/fechado")
    _git(clone, "push", "-q", "origin", f"{closed_sha}:refs/pull/9/head")

    _, out = _run(capsys, "--board", str(tmp_path / "nao-existe.md"))

    no_pr = out.split("SEM PR")[1]
    assert "feature/fechado  (PR fechado sem merge: #9)" in no_pr
    assert "feature/com-pr" not in no_pr


def test_board_em_pr_de_pr_que_ja_saiu(clone, tmp_path, capsys):
    board = tmp_path / "BOARD.md"
    board.write_text(
        "| id | frente | estado | sessão | branch / PR | desde (UTC) |\n"
        "|---|---|---|---|---|---|\n"
        "| R3 | aberto | `EM_PR` | s3 | #7 | 2026-10-02 14:00 |\n"
        "| R4 | mergeado | `EM_PR` | s4 | #8 | 2026-10-02 14:00 |\n",
        encoding="utf-8",
    )

    _, out = _run(capsys, "--board", str(board))

    stale = out.split("BOARD desatualizado")[1]
    assert "R4 | mergeado  → #8" in stale
    assert "R3" not in stale
    assert "BOARD desatualizado: #8 não está aberto" in out.splitlines()[-1]
    assert "sem gh: estado da CI e auto-merge NÃO medidos" in out
