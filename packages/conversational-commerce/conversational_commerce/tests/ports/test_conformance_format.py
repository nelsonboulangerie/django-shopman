"""O formato ``@conformance`` e a matriz gerada."""

from __future__ import annotations

import pytest

from conversational_commerce.testing.conformance import K_TESTS, conformance
from conversational_commerce.testing.conformance.matrix import PACKAGE_TESTS, main, report, scan


def test_the_forty_tests_with_owner_and_scope():
    assert [test.id for test in K_TESTS] == [f"K{n:02d}" for n in range(1, 41)]
    assert {test.id for test in K_TESTS if test.scope == "real_mechanism"} == {"K11", "K12", "K13", "K14"}


def test_decorator_marks_and_validates():
    @conformance("K38", invariants=("N26",), scope="core")
    def probe():
        pass

    assert probe.__conformance__[0].test_id == "K38"
    with pytest.raises(ValueError):
        conformance("K99", scope="core")
    with pytest.raises(ValueError):
        conformance("K01", scope="everywhere")
    with pytest.raises(ValueError):
        conformance("K01", scope="core", invariants=("N99",))


def test_matrix_lists_marked_and_missing(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "| K38 | F0 | core | test_k38_no_infrastructure.py::" in out
    assert "Faltam:" in out and "K01" in out


def test_matrix_check_passes_with_the_forty_marked(capsys):
    """Desde o F11 nenhum K falta; o caminho que reprova está em ``test_d1_exit.py``."""
    assert main(["--check"]) == 0
    capsys.readouterr()


def test_matrix_flags_wrong_scope_and_non_literal(tmp_path):
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "from conversational_commerce.testing.conformance import conformance\n"
        "SCOPE = 'core'\n"
        "@conformance('K13', scope='core')\n"
        "def test_a(): pass\n"
        "@conformance('K01', scope=SCOPE)\n"
        "def test_b(): pass\n",
        encoding="utf-8",
    )
    _, problems, _ = report([PACKAGE_TESTS, tmp_path])
    messages = [problem.message for problem in problems]
    assert any("K13 declara core, o plano exige real_mechanism" in m for m in messages)
    assert any("não literal" in m for m in messages)
    marked, _ = scan([tmp_path])
    assert [mark.test_id for mark in marked] == ["K13"]
