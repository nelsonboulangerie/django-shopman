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


def _write_adr(
    root: Path,
    filename: str,
    number: str,
    status: str = "Aceito",
    governance: str = "",
) -> None:
    decisions = root / "docs" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / filename).write_text(
        f"# ADR-{number} — Decisão {number}\n\n"
        f"**Status:** {status}\n**Data:** 2026-10-16\n{governance}\n---\n",
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


@pytest.mark.parametrize(
    "status",
    ["Aceito; emendado por ADR-002", "Substituído por ADR-002"],
)
def test_status_target_without_predecessor_backlink_fails(gate, tmp_path, status):
    _write_adr(tmp_path, "adr-001-one.md", "001", status=status)
    _write_adr(tmp_path, "adr-002-two.md", "002")
    _write_index(
        tmp_path,
        [
            _row("001", "adr-001-one.md", status=status),
            _row("002", "adr-002-two.md"),
        ],
    )

    assert any(
        "alvo ADR-002 não referencia a predecessora ADR-001" in error
        for error in gate.check(tmp_path)
    )


def test_successor_backlink_does_not_require_circular_status(gate, tmp_path):
    status = "Aceito; emendado por ADR-002"
    _write_adr(tmp_path, "adr-001-one.md", "001", status=status)
    _write_adr(
        tmp_path,
        "adr-002-two.md",
        "002",
        governance="**Emenda:** [ADR-001](adr-001-one.md)\n",
    )
    _write_index(
        tmp_path,
        [
            _row("001", "adr-001-one.md", status=status),
            _row("002", "adr-002-two.md"),
        ],
    )

    assert gate.check(tmp_path) == []
