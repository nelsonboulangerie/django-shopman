from __future__ import annotations

import json
from pathlib import Path

from scripts import check_docs_governance as guard


def _repo(tmp_path: Path, *, baseline: list[dict[str, str]] | None = None) -> Path:
    (tmp_path / "docs/plans/completed").mkdir(parents=True)
    (tmp_path / "docs/governance").mkdir(parents=True)
    (tmp_path / "docs/plans/README.md").write_text("# Planos\n", encoding="utf-8")
    (tmp_path / "docs/plans/INDEX.md").write_text("# Inventário\n", encoding="utf-8")
    (tmp_path / guard.BASELINE_FILE).write_text(
        json.dumps({"historical_links": baseline or []}), encoding="utf-8"
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
    root = _repo(tmp_path)
    (root / "docs/plans/completed/old.md").write_text("[ausente](missing.md)\n", encoding="utf-8")

    assert any("dívida histórica nova" in error for error in guard.check(root))


def test_fixing_an_old_link_does_not_pay_for_a_new_one(tmp_path: Path):
    """Laudo CORE-SOVEREIGNTY A12-2: o teto por TIPO trocava um link velho por um novo."""
    old = {"source": "docs/plans/completed/old.md", "destination": "velho.md", "kind": "missing_target"}
    root = _repo(tmp_path, baseline=[old])
    (root / "docs/plans/completed/old.md").write_text("[novo](novo.md)\n", encoding="utf-8")

    errors = guard.check(root)

    assert any("dívida histórica nova" in error and "novo.md" in error for error in errors)
    assert any("apague a entrada" in error and "velho.md" in error for error in errors)


def test_known_historical_link_passes_on_any_line(tmp_path: Path):
    known = {"source": "docs/plans/completed/old.md", "destination": "missing.md", "kind": "missing_target"}
    root = _repo(tmp_path, baseline=[known])
    (root / "docs/plans/completed/old.md").write_text("# Old\n\ntexto\n\n[ausente](missing.md)\n", encoding="utf-8")

    assert guard.check(root) == []


def test_markdown_outside_docs_is_live(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "tools/agent").mkdir(parents=True)
    (root / "tools/agent/README.md").write_text("[plano](../../docs/plans/GONE.md)\n", encoding="utf-8")
    (root / "node_modules/pkg").mkdir(parents=True)
    (root / "node_modules/pkg/README.md").write_text("[x](nada.md)\n", encoding="utf-8")

    errors = guard.check(root)

    assert [error for error in errors if "missing_target" in error] == [
        "tools/agent/README.md:1: missing_target: ../../docs/plans/GONE.md"
    ]


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
