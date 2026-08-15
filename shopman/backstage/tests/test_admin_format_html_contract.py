"""``format_html`` sem interpolação é bomba-relógio (WP-ADM-R5).

Desde o Django 5.x, ``format_html("<b>oi</b>")`` — string única, sem args nem
kwargs — levanta ``TypeError: args or kwargs must be provided``. Não é aviso: é
500 na cara de quem abriu a tela. E o erro só acontece no ramo do código que
executa aquela linha, então a chamada dorme por meses até alguém cair no `if`
certo: bastou existir um texto de interface sem padrão no código para o
formulário morrer.

Havia treze dessas espalhadas pelos admins. Quem quer HTML fixo quer
``mark_safe``; ``format_html`` é para quando há valor a interpolar (e é ele que
escapa o valor).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCANNED_TREES = ("shopman", "packages", "config")


def _python_files():
    for tree in _SCANNED_TREES:
        yield from (_REPO_ROOT / tree).rglob("*.py")


def _single_argument_format_html_calls(path: pathlib.Path):
    try:
        parsed = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "format_html" and len(node.args) == 1 and not node.keywords:
            yield node.lineno


def test_no_format_html_call_without_interpolation():
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{lineno}"
        for path in _python_files()
        for lineno in _single_argument_format_html_calls(path)
    ]

    assert not offenders, (
        "format_html com string única levanta TypeError em runtime; use mark_safe:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_the_scan_actually_reaches_the_code(tmp_path):
    """Guarda da guarda: um scan que não acha nada porque não leu nada passa
    silenciosamente e não protege coisa nenhuma."""
    assert sum(1 for _ in _python_files()) > 100

    planted = tmp_path / "planted.py"
    planted.write_text("from django.utils.html import format_html\nformat_html('<b>x</b>')\n")

    assert list(_single_argument_format_html_calls(planted)) == [2]


@pytest.mark.parametrize("snippet", ["format_html('{}', value)", "format_html('{a}', a=1)"])
def test_interpolating_calls_are_not_flagged(tmp_path, snippet):
    sample = tmp_path / "sample.py"
    sample.write_text(f"from django.utils.html import format_html\n{snippet}\n")

    assert list(_single_argument_format_html_calls(sample)) == []
