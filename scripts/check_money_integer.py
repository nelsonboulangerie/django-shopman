#!/usr/bin/env python3
"""C2 — dinheiro é inteiro em unidade mínima (AST, fail-closed com baseline).

Constituição C2 / ADR-002: valor monetário é inteiro em centavos com sufixo ``_q``; ``float``
não representa dinheiro. A guarda lê os campos de MODELO (``models.<X>Field(...)``, ou o
nome importado de ``django.db.models``) em ``packages/``, ``shopman/`` e ``config/`` e
reprova:

1. campo ``*_q`` que não é inteiro (``IntegerField`` e família);
2. campo com nome monetário (``MONEY_WORDS``) declarado como ``FloatField``/``DecimalField``.

Quantidade, peso, percentual e taxa (``rate``, ``pct``, ``percent``) não são dinheiro e
podem ser decimais. A versão regex olhava só ``packages/**/models*.py`` e casava a palavra
em qualquer lugar da linha; o AST olha o nome do campo e o tipo dele.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, import_map, iter_sources, nodes, run, scopes  # noqa: E402

SECTION = "money_integer"
SCAN_ROOTS = ("packages", "shopman", "config")
INTEGER_FIELDS = {
    "IntegerField",
    "BigIntegerField",
    "SmallIntegerField",
    "PositiveIntegerField",
    "PositiveBigIntegerField",
    "PositiveSmallIntegerField",
}
FRACTIONAL_FIELDS = {"FloatField", "DecimalField"}
MONEY_WORDS = re.compile(
    r"(^|_)(price|prices|amount|cost|costs|total|subtotal|balance|discount|fee|fees|margin|revenue|"
    r"tip|tips|surcharge|change|ticket|ltv|spent|paid|refund|refunded|tendered|cash|money)(_|$)"
)
NOT_MONEY = re.compile(r"(^|_)(rate|pct|percent|percentage|ratio|qty|quantity|weight|kg|grams|factor|share)(_|$)")
RULE = (
    "C2: dinheiro é inteiro em centavos, com sufixo _q (models.BigIntegerField). Percentual, taxa\n"
    "e quantidade podem ser decimais; se o campo não é dinheiro, o nome deve dizer isso."
)


def _model_field_type(call: ast.Call, django_names: set[str]) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "models":
        return func.attr
    if isinstance(func, ast.Name) and func.id in django_names:
        return func.id
    return None


def findings_for(rel: str, tree: ast.Module) -> list[Finding]:
    django_names = {name for name, module in import_map(tree).items() if module == "django.db.models"}
    found = []
    for cls in nodes(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for stmt in cls.body:
            if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)):
                continue
            field = _model_field_type(stmt.value, django_names)
            if not field or not field.endswith("Field"):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name.endswith("_q") and field not in INTEGER_FIELDS:
                    reason = f"{name} é {field}: campo _q tem de ser inteiro"
                elif field in FRACTIONAL_FIELDS and MONEY_WORDS.search(name) and not NOT_MONEY.search(name):
                    reason = f"{name} é {field}: nome monetário em fração"
                else:
                    continue
                qual = scopes(tree).get(id(stmt), "<module>")
                found.append(Finding(f"{rel}::{qual}::{name}", f"{rel}:{stmt.lineno}", reason))
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Dinheiro inteiro em centavos (C2)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
