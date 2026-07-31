"""O fallback da Presentation não pode divergir do registro.

A Presentation chama ``catalog.title(key, fallback)`` / ``catalog.message(key,
fallback)``. Quando a chave existe no registro, **o registro vence** e o
fallback nunca aparece. Isso cria um jeito silencioso de errar: alguém reescreve
a copy no fallback, lê o código, acha que mudou, e a tela continua com o texto
antigo — ou o contrário.

Foi assim que duas frases do pós-checkout ficaram para trás numa reescrita: o
fallback dizia uma coisa e o registro, outra. Este teste varre as chamadas reais
da Presentation e compara cada fallback com o default registrado.

Não exige que toda chave esteja registrada (fallback-only é legítimo enquanto a
chave não vira configurável). Exige que, existindo nos dois lugares, digam a
mesma coisa.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, default_for

PRESENTATION = pathlib.Path(__file__).resolve().parents[2] / "presentation"

# (arquivo, chave, fallback, "title"|"message")
Call = tuple[str, str, str, str]


def _copy_calls() -> list[Call]:
    """Toda chamada ``catalog.title/message("KEY", "fallback")`` da Presentation."""
    calls: list[Call] = []
    for path in sorted(PRESENTATION.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            kind = node.func.attr
            if kind not in {"title", "message"}:
                continue
            if len(node.args) < 2:
                continue
            key_node, fb_node = node.args[0], node.args[1]
            if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
                continue
            if not (isinstance(fb_node, ast.Constant) and isinstance(fb_node.value, str)):
                continue
            calls.append((path.name, key_node.value, fb_node.value, kind))
    return calls


def test_the_scan_actually_finds_calls():
    """Guarda do próprio guardrail: varredura vazia passaria por engano."""
    assert len(_copy_calls()) > 20


@pytest.mark.parametrize("call", _copy_calls(), ids=lambda c: f"{c[0]}:{c[1]}:{c[3]}")
def test_fallback_matches_registered_default(call: Call):
    filename, key, fallback, kind = call
    if key not in OMOTENASHI_DEFAULTS:
        pytest.skip(f"{key} não é registrada (fallback-only, legítimo)")

    entry = default_for(key)
    registered = (entry.title if kind == "title" else entry.message) or ""
    if not registered:
        pytest.skip(f"{key} não registra {kind}")

    assert registered == fallback, (
        f"{filename}: o fallback de {key} ({kind}) diverge do registro.\n"
        f"  registro (o que a tela mostra): {registered!r}\n"
        f"  fallback (o que o código sugere): {fallback!r}\n"
        "Como o registro vence, mexer só no fallback não muda nada na tela."
    )
