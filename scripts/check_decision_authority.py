#!/usr/bin/env python3
"""C5 / ADR-037 — uma decisão tem um dono (AST, fail-closed com baseline).

Cada decisão canônica tem UM ponto autoritativo no kernel dono. Reprova:

1. uma decisão canônica (``CANONICAL``) DEFINIDA fora do kernel dono;
2. um símbolo de duplicação já conhecido (``FORBIDDEN``) ainda definido em qualquer lugar.

Conta definição (``def``/``async def``, em qualquer nível, inclusive método), não chamada:
quem consome a decisão do dono está certo. A versão regex desta guarda dava OK falso porque
``^`` sem ``re.MULTILINE`` só casava a primeira linha do arquivo; o AST não tem esse modo de
falha. ``build/`` (cópia instalada do pacote) e testes ficam de fora.

Duplicação que ainda existe entra em ``scripts/constitution-baseline.json[decision_authority]``
com a frente que a apaga; quando o código some, a entrada vira obsoleta e reprova até ser
apagada no mesmo PR.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, iter_sources, nodes, run, scopes  # noqa: E402

SECTION = "decision_authority"
SCAN_ROOTS = ("packages", "shopman", "config")
CANONICAL = {
    "promise_for_sku": "packages/stockman/",
    "decision_from_availability": "packages/stockman/",
}
FORBIDDEN = {
    # Apagado pela F2 (#2263); fica como trava contra a volta do nome.
    "_stock_decision": "recomputa no orquestrador a promessa de estoque que o Stockman decide",
}
RULE = (
    "Uma decisão tem um dono (Constituição C5, ADR-037). Consuma a decisão do kernel dono em vez\n"
    "de recomputá-la; se a decisão é nova, defina-a no dono e registre-a em CANONICAL."
)


def findings_for(rel: str, tree: ast.Module) -> list[Finding]:
    found = []
    for node in nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if name not in FORBIDDEN and name not in CANONICAL:
            continue
        qual = scopes(tree).get(id(node), "<module>")
        if name in FORBIDDEN:
            found.append(Finding(f"{rel}::{qual}::{name}", f"{rel}:{node.lineno}", f"{name} ({FORBIDDEN[name]})"))
        if name in CANONICAL and not rel.startswith(CANONICAL[name]):
            found.append(
                Finding(f"{rel}::{qual}::{name}", f"{rel}:{node.lineno}", f"{name} fora do dono {CANONICAL[name]}")
            )
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Autoridade de decisão (C5)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
