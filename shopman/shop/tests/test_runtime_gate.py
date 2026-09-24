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
_IGNORED_PARTS = {".git", ".venv", "node_modules", "build", "dist", ".claude", ".codex", "__pycache__"}

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


def _subprocess_pythonpath() -> str:
    """Resolve this checkout's namespace packages before editable installs.

    Worktree validation commonly reuses a venv created by another checkout.
    Pointing only at ``ROOT`` lets that venv supply stale ``shopman.*`` package
    portions, so the probe can fail before it reaches the skip collector.
    """
    package_roots = sorted(str(path) for path in (ROOT / "packages").iterdir() if path.is_dir())
    return os.pathsep.join((str(ROOT), *package_roots))


def test_every_requires_postgres_file_is_listed_in_the_runtime_gate():
    """Nenhum arquivo `requires_postgres` pode ficar fora do gate de runtime."""
    orphans = sorted(_files_with_marker() - _runtime_paths())

    assert not orphans, (
        "arquivos com `requires_postgres` fora de DEFAULT_RUNTIME_TEST_PATHS "
        "(scripts/run_runtime_tests.py) — eles NÃO rodam em lugar nenhum:\n  " + "\n  ".join(orphans)
    )


def test_runtime_gate_paths_all_exist():
    """Caminho que sumiu no rename vira coleta vazia, não erro. Aqui vira erro."""
    missing = sorted(p for p in _runtime_paths() if not (ROOT / p).is_file())

    assert not missing, (
        f"DEFAULT_RUNTIME_TEST_PATHS aponta para arquivo inexistente (o gate coletaria vazio e passaria): {missing}"
    )


def test_runtime_gate_fails_when_a_test_is_skipped():
    """Prova viva do SkipCollector: um skip reprova o gate, mesmo com pytest verde.

    É esta regra que transforma "esqueci o Postgres" em vermelho em vez de um
    relatório verde cheio de `s`. Sem ela, rodar o gate sem banco real seria
    indistinguível de rodá-lo com banco real.
    """
    fixture = ROOT / "scripts" / "_runtime_gate_probe_test.py"
    fixture.write_text(
        "import pytest\n\n\n@pytest.mark.skip(reason='sonda do gate de runtime')\ndef test_sonda():\n    pass\n",
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
                "PYTHONPATH": _subprocess_pythonpath(),
            },
        )
    finally:
        fixture.unlink(missing_ok=True)

    assert result.returncode == 1, (
        "o gate de runtime deu verde com um teste pulado — o SkipCollector "
        f"parou de reprovar skips.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Runtime gate failed because tests were skipped" in result.stderr


def _run_gate_against(fixture_paths: str, env_extra: dict[str, str] | None = None):
    """Roda o gate de runtime num subprocesso, como o `make test-runtime` faz."""
    return subprocess.run(
        [sys.executable, "scripts/run_runtime_tests.py", "-p", "no:randomly"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        # Herda o ambiente inteiro de propósito — ver a nota longa acima.
        env={
            **os.environ,
            "SHOPMAN_RUNTIME_TEST_PATHS": fixture_paths,
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "PYTHONPATH": _subprocess_pythonpath(),
            **(env_extra or {}),
        },
    )


def test_runtime_gate_fails_when_a_whole_module_skips_itself_at_collection():
    """O skip que o SkipCollector NÃO via: o módulo que se pula na coleta.

    ``pytest.skip(..., allow_module_level=True)`` acontece antes de existir
    teste para reportar, então ele não gera ``pytest_runtest_logreport``
    nenhum. O pytest imprime ``0 collected, 1 skipped`` e sai com 0, e até
    23/09/2026 o gate lia esse 0 e dizia verde — justamente o silêncio contra o
    qual ele foi escrito.

    O arquivo verde ao lado é de propósito: sozinho, o módulo pulado faz o
    pytest sair com 5 ("nenhum teste coletado") e o gate reprovaria pelo motivo
    errado, sem provar nada. Com um teste que passa junto, o pytest sai 0 — e só
    o hook de coleta transforma isso em vermelho.
    """
    skipper = ROOT / "scripts" / "_runtime_gate_module_skip_probe_test.py"
    passer = ROOT / "scripts" / "_runtime_gate_passing_probe_test.py"
    skipper.write_text(
        "import pytest\n\n"
        "pytest.skip('sonda: modulo pulado na coleta', allow_module_level=True)\n\n\n"
        "def test_nunca_roda():\n    raise AssertionError('inalcancavel')\n",
        encoding="utf-8",
    )
    passer.write_text("def test_passa():\n    pass\n", encoding="utf-8")
    try:
        result = _run_gate_against(
            f"{skipper.relative_to(ROOT)} {passer.relative_to(ROOT)}",
        )
    finally:
        skipper.unlink(missing_ok=True)
        passer.unlink(missing_ok=True)

    assert result.returncode == 1, (
        "o gate de runtime deu verde com um MÓDULO inteiro pulado na coleta — "
        "o arquivo se declara coberto pelo gate e não roda.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "whole modules were skipped at collection" in result.stderr
    assert "_runtime_gate_module_skip_probe_test.py" in result.stderr, (
        "o gate reprovou sem NOMEAR o arquivo culpado; sem o nome ninguém acha o defeito"
    )


def test_runtime_gate_fails_when_a_listed_file_collects_nothing():
    """Rede final: arquivo listado que não entrega teste nenhum reprova.

    O skip de coleta é só um dos caminhos para "listado e morto". Um arquivo
    que perdeu seus testes num rename, ou cujo conteúdo virou helper, coleta
    zero sem pular nada — e continua na lista dizendo que está coberto.
    """
    empty = ROOT / "scripts" / "_runtime_gate_empty_probe_test.py"
    passer = ROOT / "scripts" / "_runtime_gate_passing_probe_test.py"
    empty.write_text("# sonda: arquivo de teste sem teste nenhum\n", encoding="utf-8")
    passer.write_text("def test_passa():\n    pass\n", encoding="utf-8")
    try:
        result = _run_gate_against(f"{empty.relative_to(ROOT)} {passer.relative_to(ROOT)}")
    finally:
        empty.unlink(missing_ok=True)
        passer.unlink(missing_ok=True)

    assert result.returncode == 1, (
        "o gate de runtime deu verde com um arquivo listado que coletou ZERO testes.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "collected zero tests" in result.stderr
    assert "_runtime_gate_empty_probe_test.py" in result.stderr
