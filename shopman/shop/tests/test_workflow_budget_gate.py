"""Gate do orçamento de workflow — dois blocos simétricos.

O defeito real: `timeout-minutes: 5` com `sleep 420`. Dezesseis execuções
canceladas, asserção nenhuma, e nada vermelho para avisar. Estes testes provam
que o gate reprova aquela combinação e que ele NÃO reprova a que a substituiu —
o segundo bloco é o que mantém a ferramenta viva depois do primeiro susto.

Além da aritmética, o gate guarda uma regra de domínio: o smoke não pode ter
default para `alpha.`/`staging.`, cortados em 01/09/2026.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_workflow_budgets.py"


def run_gate(workflow_dir: Path) -> subprocess.CompletedProcess:
    """Roda o gate contra uma árvore de workflows de mentira."""
    stub = workflow_dir.parent.parent / "scripts" / "check_workflow_budgets.py"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(stub)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def workflows(tmp_path: Path) -> Path:
    d = tmp_path / "repo" / ".github" / "workflows"
    d.mkdir(parents=True)
    return d


def write(workflows: Path, body: str, name: str = "exemplo.yml") -> None:
    (workflows / name).write_text(textwrap.dedent(body), encoding="utf-8")


# ---------------------------------------------------------------------------
# DEVE REPROVAR
# ---------------------------------------------------------------------------


def test_sleep_literal_maior_que_o_teto_do_job(workflows):
    """O defeito de 06-08/09/2026, reduzido ao osso."""
    write(
        workflows,
        """
        name: Exemplo
        jobs:
          smoke:
            timeout-minutes: 5
            steps:
              - name: Esperar
                run: sleep 420
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 1
    assert "espera até 420s" in result.stderr
    assert "teto do job é 300s" in result.stderr


def test_espera_declarada_maior_que_o_teto_do_job(workflows):
    write(
        workflows,
        """
        name: Exemplo
        env:
          DEPLOY_WAIT_MAX_SECONDS: "900"
        jobs:
          smoke:
            timeout-minutes: 10
            steps:
              - run: echo oi
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 1
    assert "espera até 900s" in result.stderr


def test_folga_insuficiente_reprova(workflows):
    """Caber por um segundo não basta: as asserções vêm DEPOIS da espera."""
    write(
        workflows,
        """
        name: Exemplo
        env:
          DEPLOY_WAIT_MAX_SECONDS: "900"
        jobs:
          smoke:
            timeout-minutes: 16
            steps:
              - run: echo oi
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 1
    assert ">= 1200s" in result.stderr


def test_job_com_espera_e_sem_teto_reprova(workflows):
    write(
        workflows,
        """
        name: Exemplo
        jobs:
          smoke:
            steps:
              - run: sleep 420
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 1
    assert "não declara" in result.stderr


def test_default_para_dominio_cortado_reprova(workflows):
    """`alpha.` foi cortado em 01/09/2026 e não volta como fallback mudo."""
    write(
        workflows,
        """
        name: Exemplo
        env:
          STOREFRONT_URL: ${{ vars.STOREFRONT_URL || 'https://alpha.nelsonboulangerie.com.br' }}
        jobs:
          smoke:
            timeout-minutes: 25
            steps:
              - run: echo oi
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 1
    assert "cortou" in result.stderr


# ---------------------------------------------------------------------------
# DEVE PASSAR
# ---------------------------------------------------------------------------


def test_teto_com_folga_passa(workflows):
    write(
        workflows,
        """
        name: Exemplo
        env:
          DEPLOY_WAIT_MAX_SECONDS: "900"
        jobs:
          smoke:
            timeout-minutes: 25
            steps:
              - run: echo oi
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 0, result.stderr
    assert "folga 600s" in result.stdout


def test_workflow_sem_espera_e_ignorado(workflows):
    """Gate que exige teto de quem não espera vira burocracia e é desligado."""
    write(
        workflows,
        """
        name: Exemplo
        jobs:
          build:
            steps:
              - run: make test
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 0, result.stderr


def test_sleep_curto_dentro_de_passo_nao_conta_como_espera_cega(workflows):
    """`sleep 20` de laço de polling é normal; o que assusta é o teto."""
    write(
        workflows,
        """
        name: Exemplo
        jobs:
          smoke:
            timeout-minutes: 25
            steps:
              - run: |
                  while :; do
                    sleep 20
                  done
        """,
    )
    result = run_gate(workflows)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# O workflow DE VERDADE deste repositório
# ---------------------------------------------------------------------------


def test_workflows_do_repo_passam_no_gate():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_alpha_smoke_nao_tem_espera_cega():
    """Espera cega não tem número certo — a de hoje pergunta à DigitalOcean."""
    text = (REPO_ROOT / ".github" / "workflows" / "alpha-smoke.yml").read_text(
        encoding="utf-8"
    )
    # Só linhas de código: o comentário do arquivo CITA `sleep 420` de
    # propósito, para que quem ler saiba o que aconteceu.
    codigo = [
        linha for linha in text.splitlines() if not linha.lstrip().startswith("#")
    ]
    assert not [linha for linha in codigo if "sleep 420" in linha]
    assert "scripts/wait_for_do_deployment.py" in text
