"""Leitor dos checks obrigatórios de `main` (scripts/check_canonical_docs.py).

O espelho `.github/required-status-checks.json` só protege alguma coisa se o
leitor montar os nomes de check como o GitHub monta. Estes testes, offline,
provam: o repositório de hoje passa; renomear um job obrigatório reprova; job
que não roda na fila de merge não conta; e a matriz expande do jeito que o
GitHub publica (`Testes (test-shop)` quando o nome não cita a matriz,
substituição quando cita).

A conferência contra a branch protection VIVA é `make required-checks-drift`
(precisa de `gh`), e não roda aqui: é ela que pega o espelho encolhido.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_canonical_docs.py"


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("check_canonical_docs_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _job(gate, text: str) -> set[str]:
    lines = textwrap.dedent(text).splitlines()
    ((job_id, block),) = gate._job_blocks(lines).items()
    return gate._job_check_names(job_id, block)


def _fake_repo(tmp_path: Path, workflow: str, contexts: list[str]) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(textwrap.dedent(workflow), encoding="utf-8")
    (tmp_path / ".github" / "required-status-checks.json").write_text(
        json.dumps(
            {
                "branch": "main",
                "read_at": "2026-10-01T00:00:00Z",
                "command": "gh api ...",
                "strict": False,
                "contexts": contexts,
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_today_every_required_check_is_produced(gate):
    result = gate.Result(errors=[], passed=[])
    gate.check_required_status_checks(result)
    assert result.errors == []
    data = json.loads((REPO_ROOT / ".github" / "required-status-checks.json").read_text(encoding="utf-8"))
    produced, _ = gate.workflow_check_names()
    assert set(data["contexts"]) <= set(produced)


def test_job_without_name_publishes_its_id(gate):
    names = _job(
        gate,
        """
        jobs:
          operator-kit:
            runs-on: ubuntu-latest
        """,
    )
    assert names == {"operator-kit"}


def test_matrix_not_cited_in_name_is_appended_in_parentheses(gate):
    names = _job(
        gate,
        """
        jobs:
          test:
            name: Testes
            strategy:
              matrix:
                suite: [test-shop, test-cores]
        """,
    )
    assert names == {"Testes (test-shop)", "Testes (test-cores)"}


def test_matrix_cited_in_name_is_substituted(gate):
    names = _job(
        gate,
        """
        jobs:
          test:
            name: Testes (${{ matrix.suite }})
            strategy:
              matrix:
                suite:
                  - test-shop
                  - test-storefront
        """,
    )
    assert names == {"Testes (test-shop)", "Testes (test-storefront)"}


def test_renamed_required_job_fails(gate, tmp_path, monkeypatch):
    root = _fake_repo(
        tmp_path,
        """
        on:
          pull_request:
          merge_group:
        jobs:
          gate:
            name: Gate renomeado
            runs-on: ubuntu-latest
        """,
        ["Gate da meia-correção"],
    )
    monkeypatch.setattr(gate, "ROOT", root)
    result = gate.Result(errors=[], passed=[])
    gate.check_required_status_checks(result)
    assert any("Gate da meia-correção" in error for error in result.errors)


def test_job_outside_merge_group_does_not_count(gate, tmp_path, monkeypatch):
    """Check que só roda em pull_request nunca reporta na fila: trava o merge."""
    root = _fake_repo(
        tmp_path,
        """
        on:
          pull_request:
        jobs:
          gate:
            name: Gate da meia-correção
            runs-on: ubuntu-latest
        """,
        ["Gate da meia-correção"],
    )
    monkeypatch.setattr(gate, "ROOT", root)
    result = gate.Result(errors=[], passed=[])
    gate.check_required_status_checks(result)
    assert any("Gate da meia-correção" in error for error in result.errors)
