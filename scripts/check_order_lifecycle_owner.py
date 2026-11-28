#!/usr/bin/env python3
"""C6 — o ciclo de ``Order`` pertence ao Orderman (AST, fail-closed com baseline).

Constituição C6 / ADR-006: estados e transições de ``Order`` são do Orderman; orquestrador,
read-side e superfícies consomem essa semântica e não inventam ciclo paralelo. Fora de
``packages/orderman`` a guarda reprova:

1. **transição por fora do dono**: ``<x>.status = Order.Status.<Y>``,
   ``setattr(<x>, "status", Order.Status.<Y>)`` e ``Order.objects…update(status=...)``; a
   transição passa por ``order.transition_status(...)``, que valida a tabela e emite o
   evento. Ler o status (inclusive ``order.status = <valor relido do banco>``) não conta;
2. **tabela de transição paralela**: um ``dict`` cujas chaves e valores são membros de
   ``Order.Status`` (o formato de ``Order.TRANSITIONS``), ou uma classe ``*OrderStatus*``.

``Order`` é resolvido pelo import (``from shopman.orderman.models import Order``).
Chamar ``order.transition_status()`` a partir do orquestrador é consumo legítimo (ADR-006).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, import_map, iter_sources, nodes, run, scopes  # noqa: E402

SECTION = "order_lifecycle_owner"
SCAN_ROOTS = ("shopman", "config", "packages")
OWNER = "packages/orderman/"
RULE = (
    "C6: o ciclo de Order é do Orderman. Transicione com order.transition_status(<novo>, actor=...);\n"
    "se falta um estado ou uma transição, ela nasce em Order.Status/Order.TRANSITIONS, não aqui."
)


def _order_names(imports: dict[str, str]) -> set[str]:
    return {name for name, module in imports.items() if module.startswith("shopman.orderman") and name == "Order"}


def _is_status_member(node: ast.AST, orders: set[str]) -> bool:
    """``Order.Status.<X>`` com ``Order`` importado do Orderman."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "Status"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id in orders
    )


def _members(node: ast.AST, orders: set[str]) -> bool:
    if _is_status_member(node, orders):
        return True
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return bool(node.elts) and all(_is_status_member(e, orders) for e in node.elts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"}:
        return len(node.args) == 1 and _members(node.args[0], orders)
    return False


def _is_order_manager_update(call: ast.Call, orders: set[str]) -> bool:
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "update"):
        return False
    if not any(kw.arg == "status" for kw in call.keywords):
        return False
    recv = call.func.value
    while isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute):
        recv = recv.func.value
    return (
        isinstance(recv, ast.Attribute)
        and recv.attr == "objects"
        and isinstance(recv.value, ast.Name)
        and recv.value.id in orders
    )


def findings_for(rel: str, tree: ast.Module) -> list[Finding]:
    if rel.startswith(OWNER):
        return []
    orders = _order_names(import_map(tree))
    found = []

    def add(node: ast.AST, kind: str, detail: str) -> None:
        qual = scopes(tree).get(id(node), "<module>")
        found.append(Finding(f"{rel}::{qual}::{kind}", f"{rel}:{node.lineno}", detail))

    for node in nodes(tree):
        if isinstance(node, ast.ClassDef) and "OrderStatus" in node.name:
            add(node, f"class {node.name}", f"classe de status de pedido fora do Orderman: {node.name}")
        if not orders:
            continue
        if isinstance(node, ast.Assign) and _is_status_member(node.value, orders):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "status":
                    add(node, "status=", f"{ast.unparse(target)} = {ast.unparse(node.value)}")
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "setattr"
                and len(node.args) == 3
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "status"
                and _is_status_member(node.args[2], orders)
            ):
                add(node, "setattr(status)", ast.unparse(node))
            elif _is_order_manager_update(node, orders):
                add(node, "objects.update(status)", f"{ast.unparse(node.func)}(status=...)")
        elif isinstance(node, ast.Dict) and node.keys and all(
            k is not None and _is_status_member(k, orders) for k in node.keys
        ):
            if all(_members(v, orders) for v in node.values):
                add(node, "tabela de transicao", "dict Order.Status -> Order.Status (tabela de transição paralela)")
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Ciclo de Order no Orderman (C6)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
