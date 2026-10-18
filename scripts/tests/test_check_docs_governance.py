from __future__ import annotations

import json
from pathlib import Path

from scripts import check_docs_governance as guard


def _repo(tmp_path: Path, *, ceiling: dict[str, int] | None = None) -> Path:
    (tmp_path / "docs/plans/completed").mkdir(parents=True)
    (tmp_path / "docs/governance").mkdir(parents=True)
    (tmp_path / "docs/plans/README.md").write_text("# Planos\n", encoding="utf-8")
    (tmp_path / "docs/plans/INDEX.md").write_text("# Inventário\n", encoding="utf-8")
    (tmp_path / guard.BASELINE_FILE).write_text(
        json.dumps({"maximum_by_kind": ceiling or {}}), encoding="utf-8"
    )
    return tmp_path


def test_rejects_missing_live_target(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/guide.md").write_text("[ausente](missing.md)\n", encoding="utf-8")

    assert any("missing_target" in error for error in guard.check(root))


def test_rejects_missing_live_anchor(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/target.md").write_text("# Existe\n", encoding="utf-8")
    (root / "docs/guide.md").write_text("[seção](target.md#nao-existe)\n", encoding="utf-8")

    assert any("missing_anchor" in error for error in guard.check(root))


def test_accepts_code_line_fragment(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/target.md").write_text("texto\n", encoding="utf-8")
    (root / "docs/guide.md").write_text("[linhas](target.md#L1-L2)\n", encoding="utf-8")

    assert guard.check(root) == []


def test_rejects_historical_debt_above_baseline(tmp_path: Path):
    root = _repo(tmp_path, ceiling={"missing_target": 0})
    (root / "docs/plans/completed/old.md").write_text("[ausente](missing.md)\n", encoding="utf-8")

    assert any("excede baseline" in error for error in guard.check(root))


def test_rejects_active_plan_row_pointing_to_archive(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/plans/completed/old.md").write_text("# Old\n", encoding="utf-8")
    (root / "docs/plans/README.md").write_text(
        "# Planos\n\n| Plano | Estado |\n|---|---|\n| [Old](completed/old.md) | ativo |\n",
        encoding="utf-8",
    )

    assert any("plano ativo aponta" in error for error in guard.check(root))


def test_rejects_incomplete_live_plan_index(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/plans/open.md").write_text("# Open\n", encoding="utf-8")

    assert any("plano vivo não indexado" in error for error in guard.check(root))
