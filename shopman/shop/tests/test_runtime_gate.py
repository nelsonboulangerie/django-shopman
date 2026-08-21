"""O gate de runtime cobre TODO teste que só roda em PostgreSQL.

Um teste marcado com ``requires_postgres`` (``skipif`` em SQLite) não roda no
``make test`` — e o único lugar do projeto que o executa é o gate de runtime,
que lê ``DEFAULT_RUNTIME_TEST_PATHS`` em ``scripts/run_runtime_tests.py``.

Quem esquece de acrescentar o arquivo à lista não recebe erro nenhum: o teste
some do CI, some do local, e ainda conta como "passou" no relatório do dia
porque ``skipped`` não é ``failed``. Foi assim que cinco corridas de dinheiro e
estoque (venda simultânea, dupla submissão, cupom de uso único, fechar a gaveta
com venda em voo, notificação duplicada) ficaram escritas e mortas.

Este teste é a costura: varre a árvore atrás do marcador e reprova quando um
arquivo com ``requires_postgres`` não está na lista do gate. Ele roda em SQLite
como qualquer outro, então avisa no `make test` de quem escreveu o teste novo,
não três meses depois.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: Diretórios que não são código do projeto (venv, builds, worktrees aninhadas).
_IGNORED_PARTS = {".git", ".venv", "node_modules", "build", "dist", ".claude", "__pycache__"}

#: O marcador canônico: `requires_postgres = pytest.mark.skipif("sqlite" in ...)`.
_MARKER = re.compile(r"^\s*requires_postgres\s*=\s*pytest\.mark\.skipif", re.MULTILINE)


def _runtime_paths() -> set[str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from run_runtime_tests import DEFAULT_RUNTIME_TEST_PATHS
    finally:
        sys.path.pop(0)
    return set(DEFAULT_RUNTIME_TEST_PATHS)


def _files_with_marker() -> set[str]:
    found = set()
    for path in ROOT.rglob("test_*.py"):
        if _IGNORED_PARTS & set(path.relative_to(ROOT).parts):
            continue
        if _MARKER.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(str(path.relative_to(ROOT)))
    return found


def test_every_requires_postgres_file_is_listed_in_the_runtime_gate():
    """Nenhum arquivo `requires_postgres` pode ficar fora do gate de runtime."""
    orphans = sorted(_files_with_marker() - _runtime_paths())

    assert not orphans, (
        "arquivos com `requires_postgres` fora de DEFAULT_RUNTIME_TEST_PATHS "
        "(scripts/run_runtime_tests.py) — eles NÃO rodam em lugar nenhum:\n  "
        + "\n  ".join(orphans)
    )


def test_runtime_gate_paths_all_exist():
    """Caminho que sumiu no rename vira coleta vazia, não erro. Aqui vira erro."""
    missing = sorted(p for p in _runtime_paths() if not (ROOT / p).is_file())

    assert not missing, (
        "DEFAULT_RUNTIME_TEST_PATHS aponta para arquivo inexistente "
        f"(o gate coletaria vazio e passaria): {missing}"
    )


def test_runtime_gate_fails_when_a_test_is_skipped():
    """Prova viva do SkipCollector: um skip reprova o gate, mesmo com pytest verde.

    É esta regra que transforma "esqueci o Postgres" em vermelho em vez de um
    relatório verde cheio de `s`. Sem ela, rodar o gate sem banco real seria
    indistinguível de rodá-lo com banco real.
    """
    fixture = ROOT / "scripts" / "_runtime_gate_probe_test.py"
    fixture.write_text(
        "import pytest\n\n\n"
        "@pytest.mark.skip(reason='sonda do gate de runtime')\n"
        "def test_sonda():\n"
        "    pass\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, "scripts/run_runtime_tests.py", "-p", "no:randomly"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            # Herda o ambiente inteiro de propósito. Montar um env mínimo à mão
            # parecia mais limpo e escondia o teste: sem `DJANGO_SECRET_KEY`, o
            # subprocesso morria no assert de settings antes de chegar ao gate,
            # e o `returncode == 1` continuava verdadeiro pelo motivo errado —
            # verde local (onde existe .env) e vermelho no CI (onde não existe).
            env={
                **os.environ,
                "SHOPMAN_RUNTIME_TEST_PATHS": str(fixture.relative_to(ROOT)),
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "PYTHONPATH": str(ROOT),
            },
        )
    finally:
        fixture.unlink(missing_ok=True)

    assert result.returncode == 1, (
        "o gate de runtime deu verde com um teste pulado — o SkipCollector "
        f"parou de reprovar skips.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Runtime gate failed because tests were skipped" in result.stderr
