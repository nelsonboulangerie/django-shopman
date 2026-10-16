from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_adr_governance.py"


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("check_adr_governance_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _write_adr(root: Path, filename: str, number: str, status: str = "Aceito") -> None:
    decisions = root / "docs" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / filename).write_text(
        f"# ADR-{number} — Decisão {number}\n\n**Status:** {status}\n**Data:** 2026-10-16\n",
        encoding="utf-8",
    )


def _write_index(root: Path, rows: list[str]) -> None:
    (root / "docs" / "decisions" / "README.md").write_text(
        "# ADRs\n\n| # | Título | Status | Dono | Data | Tema |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def _row(number: str, filename: str, status: str = "Aceito") -> str:
    return f"| [{number}]({filename}) | Decisão {number} | {status} | Suite | 2026-10-16 | Teste |"


def test_current_repository_is_valid(gate):
    assert gate.check(REPO_ROOT) == []


def test_duplicate_number_fails(gate, tmp_path):
    _write_adr(tmp_path, "adr-001-one.md", "001")
    _write_adr(tmp_path, "adr-001-two.md", "001")
    _write_index(tmp_path, [_row("001", "adr-001-one.md")])

    assert any("número duplicado" in error for error in gate.check(tmp_path))


def test_non_canonical_status_fails(gate, tmp_path):
    _write_adr(tmp_path, "adr-001-one.md", "001", status="Accepted")
    _write_index(tmp_path, [_row("001", "adr-001-one.md", status="Accepted")])

    assert any("status não canônico" in error for error in gate.check(tmp_path))


def test_adr_missing_from_index_fails(gate, tmp_path):
    _write_adr(tmp_path, "adr-001-one.md", "001")
    _write_index(tmp_path, [])

    assert any("sem entrada no índice" in error for error in gate.check(tmp_path))
