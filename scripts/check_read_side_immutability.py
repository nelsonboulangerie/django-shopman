#!/usr/bin/env python3
"""C10 — read-side não é fonte do fato (AST, fail-closed com baseline).

Constituição C10 / ADR-021: projections e B.I. leem e podem MATERIALIZAR derivado
recomputável nas tabelas deles; não escrevem nos modelos dos kernels nem passam a possuir o
fato observado.

Divisão de trabalho com o que já existe:

- ``shopman/shop/tests/test_import_boundaries.py`` (``test_read_side_does_not_write`` e
  ``test_read_side_never_writes``) proíbe QUALQUER escrita, direta ou transitiva, em
  ``shop/projections``, ``backstage/projections`` e ``storefront/presentation``;
- esta guarda cobre o B.I. (``shopman/backstage/bi``), que materializa de propósito (ingestão,
  ``ImportBatch``, canônica) e por isso não cabe naquela regra, e a ``backstage/presentation``:
  ali só reprova escrita ORM num modelo de KERNEL (resolvido pelo import
  ``from shopman.<kernel>...``). Escrever no modelo do próprio B.I. é materializar; escrever
  no ``Order``/``Move``/``Customer`` é virar fonte do fato.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, import_map, iter_sources, kernel_of_module, nodes, run, scopes  # noqa: E402

SECTION = "read_side_immutability"
SCAN_ROOTS = ("shopman/backstage/bi", "shopman/backstage/presentation")
ORM_WRITES = {"create", "bulk_create", "get_or_create", "update_or_create", "update", "bulk_update", "delete"}
RULE = (
    "C10: o read-side não escreve no kernel. Materialize o derivado numa tabela do B.I.; fato\n"
    "novo nasce pelo serviço do kernel dono, chamado por um comando, não pela leitura."
)


def _manager_model(call: ast.Call) -> str | None:
    recv = call.func.value
    while isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute):
        recv = recv.func.value
    if isinstance(recv, ast.Attribute) and recv.attr == "objects" and isinstance(recv.value, ast.Name):
        return recv.value.id
    return None


def findings_for(rel: str, tree: ast.Module) -> list[Finding]:
    imports = import_map(tree)
    found = []
    for node in nodes(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ORM_WRITES):
            continue
        model = _manager_model(node)
        kernel = kernel_of_module(imports.get(model)) if model else None
        if kernel is None:
            continue
        qual = scopes(tree).get(id(node), "<module>")
        found.append(
            Finding(
                f"{rel}::{qual}::{model}.{node.func.attr}",
                f"{rel}:{node.lineno}",
                f"{model}.objects…{node.func.attr}: read-side escreve no kernel {kernel}",
            )
        )
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Read-side não escreve no kernel (C10)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
