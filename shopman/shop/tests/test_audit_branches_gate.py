"""A auditoria de branches não pode decidir por uma janela fixa de PRs.

O falso positivo real, medido em 08/09/2026: o script listava os 300 PRs
mergeados mais recentes e decidia por ali. O PR #135 já tinha caído para fora
da janela, e `feat/badge-issue-screen` — entregue — apareceu como
`⚠️ UNMERGED`. Auditoria que aponta trabalho inexistente ensina a ignorar a
coluna que importa.

Estes testes montam um repositório de mentira e um `gh` de mentira em que o
CACHE VEM VAZIO — exatamente o que acontece quando o PR é antigo demais. Se a
classificação ainda estiver presa ao cache, `entregue` cai em ⚠️ e o teste
reprova.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "audit-branches.sh"

#: `gh` de mentira: o cache (--state merged --limit N) vem VAZIO, como quando o
#: PR é mais antigo que a janela. Só a pergunta dirigida (--head) sabe a verdade.
FAKE_GH = """#!/usr/bin/env bash
for arg in "$@"; do
  if [ "$seen_head" = "1" ]; then branch="$arg"; seen_head=0; fi
  [ "$arg" = "--head" ] && seen_head=1
  [ "$arg" = "open" ] && aberto=1
done
if [ "${aberto:-0}" = "1" ]; then
  echo 'em-revisao'              # head de PR ABERTO
elif [ -z "${branch:-}" ]; then
  echo '[]'                      # o cache de mergeados erra por construção
elif [ "$branch" = "entregue" ]; then
  echo 'MERGED'
elif [ "$branch" = "recusado" ]; then
  echo 'CLOSED'
else
  echo ''
fi
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "gate@example.test")
    git(r, "config", "user.name", "Gate")
    (r / "base.txt").write_text("base\n")
    git(r, "add", "base.txt")
    git(r, "commit", "-qm", "base")
    base = git(r, "rev-parse", "HEAD")
    git(r, "update-ref", "refs/remotes/origin/main", base)

    # Três branches com delta REAL sobre o main.
    for name, payload in (
        ("entregue", "a"),
        ("recusado", "b"),
        ("esquecido", "c"),
        ("em-revisao", "d"),
    ):
        git(r, "checkout", "-q", "-b", name, base)
        (r / f"{name}.txt").write_text(payload + "\n")
        git(r, "add", f"{name}.txt")
        git(r, "commit", "-qm", f"trabalho de {name}")
        git(r, "update-ref", f"refs/remotes/origin/{name}", "HEAD")
    git(r, "checkout", "-q", "main")
    return r


def run_audit(repo: Path, tmp_path: Path) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BASE": "origin/main",
        "REMOTE": "origin",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def linha(saida: str, branch: str) -> str:
    for line in saida.splitlines():
        if branch in line:
            return line
    raise AssertionError(f"branch '{branch}' não apareceu na tabela:\n{saida}")


def test_pr_mergeado_fora_da_janela_nao_vira_falso_positivo(repo, tmp_path):
    """O defeito de 08/09/2026: cache vazio não pode virar ⚠️ UNMERGED."""
    saida = run_audit(repo, tmp_path)
    assert "PR MERGEADO" in linha(saida, "entregue")
    assert "UNMERGED" not in linha(saida, "entregue")


def test_pr_fechado_e_decisao_registrada_nao_pendencia(repo, tmp_path):
    saida = run_audit(repo, tmp_path)
    assert "PR FECHADO" in linha(saida, "recusado")
    assert "UNMERGED" not in linha(saida, "recusado")


def test_head_de_pr_aberto_nao_e_branch_esquecida(repo, tmp_path):
    """Os sete Dependabot enchiam a coluna ⚠️ sem exigir ação nenhuma.

    Uma coluna que grita por trabalho em revisão é uma coluna que se aprende a
    ignorar — que é como o falso positivo da janela de 300 PRs fazia mal.
    """
    saida = run_audit(repo, tmp_path)
    assert "PR ABERTO" in linha(saida, "em-revisao")
    assert "UNMERGED" not in linha(saida, "em-revisao")


def test_branch_sem_pr_nenhum_continua_gritando(repo, tmp_path):
    """O segundo bloco: um gate que nunca reprova não guarda nada."""
    saida = run_audit(repo, tmp_path)
    assert "UNMERGED" in linha(saida, "esquecido")
    assert "1 branch(es) com trabalho potencialmente não mergeado" in saida


def test_a_janela_e_apenas_cache():
    """Se a decisão voltar a depender do limite, este teste conta a história."""
    texto = SCRIPT.read_text(encoding="utf-8")
    assert "gh pr list --head" in texto
    assert "MERGED_PR_LIMIT" in texto  # o cache pode existir…
    assert "pr_state_for" in texto     # …mas quem decide é a pergunta dirigida
