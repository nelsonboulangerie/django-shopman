"""A API do balcão fala o ato do PDV: validar, nunca finalizar (#3278).

As frases de ``operations.py`` chegam ao operador como ``detail``. O vocabulário do
PDV (docs/reference/suite-vocabulary.md) diz *validar* para o ato e *comanda*/*venda*
para o objeto; "finalizar" e "carrinho" são da loja. A trava lê toda string do módulo
que não seja docstring nem comentário.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "api" / "operations.py"
BANNED = ("finaliz", "carrinho")


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def test_api_do_balcao_nao_diz_finalizar_nem_carrinho():
    tree = ast.parse(MODULE.read_text())
    docstrings = _docstring_ids(tree)
    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
        and any(word in node.value.lower() for word in BANNED)
    ]
    assert not offenders, offenders
