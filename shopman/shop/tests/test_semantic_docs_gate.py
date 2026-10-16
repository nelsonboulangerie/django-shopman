"""Negative fixtures for the semantic documentation gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_semantic_docs.py"

spec = importlib.util.spec_from_file_location("check_semantic_docs_under_test", SCRIPT)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _package_section(name: str) -> str:
    return f"""## {name}

**Diretório físico:** `packages/{name}/`

- **Pergunta canônica:** pergunta
- **Verbos:** verbo
- **Estados e sinais:** estado
- **Eventos:** evento
"""


def test_repo_semantic_docs_are_consistent():
    assert gate.check_repository(REPO_ROOT) == []


def test_bijection_rejects_missing_and_nonexistent_packages(tmp_path):
    (tmp_path / "packages" / "real").mkdir(parents=True)
    _write(tmp_path / "docs/reference/semantic-map.md", _package_section("ghost"))

    errors = gate.check_package_bijection(tmp_path)

    assert "semantic map is missing physical packages: ['real']" in errors
    assert "semantic map names nonexistent packages: ['ghost']" in errors


def test_constitution_link_rejects_nonexistent_anchor(tmp_path):
    _write(tmp_path / "docs/constitution.md", "# Constituição\n\n## C1. Lei\n")
    _write(tmp_path / "docs/_archive/constitution-v1.md", "# Constituição v1\n")
    _write(
        tmp_path / "docs/guide.md",
        "[Constituição C9](constitution.md#c9-nao-existe)\n",
    )

    errors = gate.check_constitution_references(tmp_path)

    assert any("nonexistent Constitution anchor" in error for error in errors)


def test_bare_old_section_and_unmarked_history_are_rejected(tmp_path):
    _write(tmp_path / "docs/constitution.md", "# Constituição\n\n## 4.1. Preço\n")
    _write(tmp_path / "docs/_archive/constitution-v1.md", "# Constituição v1\n\n## 4.1. Preço\n")
    _write(
        tmp_path / "docs/guide.md",
        "Constituição §9.9 decide.\n[Constituição §4.1](_archive/constitution-v1.md#41-preço)\n",
    )

    errors = gate.check_constitution_references(tmp_path)

    assert any("bare Constitution section citation" in error for error in errors)
    assert any("must say historical" in error for error in errors)
