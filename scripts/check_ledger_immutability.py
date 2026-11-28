#!/usr/bin/env python3
"""C11 — o ledger pertence ao domínio do fato e não se reescreve (AST, fail-closed com baseline).

Constituição C11 / ADR-022: história imutável mora no kernel que possui o fato; correção é
lançamento novo, nunca reescrita. Cada ledger tem um DONO (``LEDGERS``) e a guarda faz o
mapeamento por dono:

- fora do dono (e fora de uma ponte ``contrib/<dono>/``, que conecta sem transferir
  titularidade — C1/C5): QUALQUER escrita ORM no ledger (``create``, ``bulk_create``,
  ``get_or_create``, ``update_or_create``, ``update``, ``bulk_update``, ``delete``) reprova;
  o fato nasce pelo serviço do dono;
- dentro do dono: lançar (``create``/``bulk_create``) é o trabalho dele; ``update``,
  ``bulk_update``, ``update_or_create`` e ``delete`` reescrevem história e reprovam.

O modelo é resolvido pelo import (``from shopman.stockman.models import Move``): um ``Move``
de outro módulo não conta. Fica de fora o que o AST não tipa: escrita por related manager
(``order.events.create``) e ``instancia.save()``. Para isso valem as travas de runtime dos
próprios modelos (``MoveQuerySet``, ``EntryQuerySet``, ``PaymentTransaction.save``).

Medida (10/11/2026): a primeira passagem contava 1 candidato (só ``update/delete`` via
``X.objects``, sem dono); a varredura larga, sem mapeamento por dono, conta toda escrita
ORM nos seis ledgers (``--broad``). O mapeamento por dono reduz isso ao que é violação.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import (  # noqa: E402
    ROOT,
    Finding,
    bridge_target,
    import_map,
    iter_sources,
    kernel_of,
    kernel_of_module,
    nodes,
    run,
    scopes,
)

SECTION = "ledger_immutability"
SCAN_ROOTS = ("packages", "shopman", "config")
LEDGERS = {
    "Entry": "cashman",
    "Move": "stockman",
    "PaymentTransaction": "payman",
    "OrderEvent": "orderman",
    "SessionEvent": "orderman",
    "WorkOrderEvent": "craftsman",
}
APPEND = {"create", "bulk_create", "get_or_create"}
REWRITE = {"update", "bulk_update", "delete", "update_or_create"}
QUERYSET_HOPS = {
    "all",
    "filter",
    "exclude",
    "select_for_update",
    "select_related",
    "prefetch_related",
    "order_by",
    "only",
    "defer",
    "using",
}
RULE = (
    "C11: o ledger é do kernel dono do fato. Fora do dono, lance pelo serviço dele; dentro do\n"
    "dono, corrija com um lançamento novo (estorno/delta inverso), nunca com update/delete."
)


def _ledger_target(call: ast.Call) -> str | None:
    """Nome do model quando a chamada é ``<Model>.objects[.<hops>].<método>(...)``."""
    recv = call.func.value
    while isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute) and recv.func.attr in QUERYSET_HOPS:
        recv = recv.func.value
    if isinstance(recv, ast.Attribute) and recv.attr == "objects" and isinstance(recv.value, ast.Name):
        return recv.value.id
    return None


def _model_kernel(name: str, imports: dict[str, str], file_kernel: str | None) -> str | None:
    """Kernel de onde vem o model ``name`` neste módulo, ou None se não é o ledger."""
    if name not in LEDGERS:
        return None
    if name in imports:
        return kernel_of_module(imports[name])
    return file_kernel  # definido no próprio módulo (o models do dono)


def findings_for(rel: str, tree: ast.Module, *, broad: bool = False) -> list[Finding]:
    imports = import_map(tree)
    file_kernel = kernel_of(rel)
    territory = {file_kernel, bridge_target(rel)} - {None}
    found = []
    for node in nodes(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        method = node.func.attr
        if method not in APPEND | REWRITE:
            continue
        name = _ledger_target(node)
        if name not in LEDGERS:
            continue
        model_kernel = _model_kernel(name, imports, file_kernel)
        if model_kernel != LEDGERS[name]:
            continue
        in_owner = LEDGERS[name] in territory
        if not broad and in_owner and method in APPEND:
            continue
        why = "reescrita de história" if method in REWRITE else f"lançamento fora do dono ({LEDGERS[name]})"
        qual = scopes(tree).get(id(node), "<module>")
        found.append(Finding(f"{rel}::{qual}::{name}.{method}", f"{rel}:{node.lineno}", f"{name}.objects…{method}: {why}"))
    return found


def collect(root: Path = ROOT, *, broad: bool = False) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree, broad=broad)]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--broad" in args:
        findings = collect(broad=True)
        print(f"Varredura larga (toda escrita ORM nos ledgers, sem dono): {len(findings)}")
        for f in findings:
            print(f"  - {f.where}: {f.detail}")
        return 0
    return run(SECTION, "Ledger imutável no dono (C11)", collect(), args, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
