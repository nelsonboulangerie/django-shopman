"""A recusa do PDV fala a língua do balcão (#3274).

O operador lê a frase do ``PosIntentError`` como vem. "Carrinho" é palavra da loja;
no balcão a conta aberta é a *comanda* e a cobrada é a *venda*, e o ato é *validar*
(docs/reference/suite-vocabulary.md). A trava lê, nos módulos que levantam o erro,
toda frase passada a ``PosIntentError`` (posicional ou ``message``/``recovery``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULES = [
    "shopman/shop/services/pos.py",
    "shopman/shop/services/pos_intent.py",
    "shopman/shop/services/pos_edit_session.py",
    "shopman/shop/services/pos_offline_sale.py",
    "shopman/shop/services/pos_receipt_identity.py",
    "shopman/shop/services/pos_sales_mode.py",
    "shopman/shop/services/weighed_sale.py",
    "shopman/backstage/services/pos_seating.py",
]
BANNED = ("carrinho", "finaliz")


def _phrases(path: Path) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "PosIntentError":
            continue
        values = list(node.args) + [kw.value for kw in node.keywords if kw.arg in {"message", "recovery"}]
        for value in values:
            for sub in ast.walk(value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    found.append((sub.lineno, sub.value))
    return found


@pytest.mark.parametrize("module", MODULES)
def test_recusa_do_pdv_nao_diz_carrinho_nem_finalizar(module):
    phrases = _phrases(ROOT / module)
    assert phrases, f"{module}: nenhuma frase de PosIntentError encontrada; a trava ficou cega"
    offenders = [(line, text) for line, text in phrases if any(word in text.lower() for word in BANNED)]
    assert not offenders, f"{module}: {offenders}"
