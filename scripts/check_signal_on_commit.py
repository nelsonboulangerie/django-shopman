#!/usr/bin/env python3
"""ADR-025 — anúncio por signal sai DEPOIS do COMMIT (AST, fail-closed com baseline).

Um ``send`` de signal Django (``<sinal>.send(sender=...)`` ou ``send_robust``) é aceito
quando:

1. está ADIADO pelo emissor: dentro de um ``lambda`` ou função passados a
   ``transaction.on_commit(...)``, ou dentro de uma função do mesmo módulo cujo nome aparece
   num ``on_commit(...)`` (``on_commit(_emit)``, ``on_commit(lambda: _emit(x))``,
   ``on_commit(self._announce)``);
2. é ESCRITA ACOPLADA declarada no código, como manda a ADR-025: um comentário com
   ``ADR-025`` e ``escrita acoplada`` até 3 linhas acima do ``send`` (ou na mesma linha);
3. está dentro de um handler de Directive (classe com ``handle(self, *, message, ctx)``),
   que o worker e o dispatcher rodam fora de transação (ADR-003).

Todo o resto é anúncio dentro da transação: o receiver roda antes do COMMIT, um rollback
deixa de pé o que ele fez e uma exceção dele aborta quem emitiu. O que já existe está
classificado em ``scripts/constitution-baseline.json[signal_on_commit]``: ``excecao`` para
escrita acoplada já decidida pela ADR-025 §6 (falta só o comentário, que não é desta guarda
escrever) e ``violacao`` para anúncio que devia sair por ``on_commit``.

A janela de 8 linhas da versão regex aceitava qualquer ``on_commit`` vizinho, inclusive em
docstring, e perdia o ``send`` quebrado em várias linhas; o AST resolve os dois.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, iter_sources, nodes, run, scopes  # noqa: E402

SECTION = "signal_on_commit"
SCAN_ROOTS = ("packages", "shopman", "config")
MARKER = re.compile(r"#.*ADR-025.*escrita acoplada", re.IGNORECASE)
RULE = (
    "ADR-025: anúncio sai por transaction.on_commit(lambda: sinal.send(...)). Se o receiver\n"
    "completa a escrita (gate de estoque, ledger), deixe o send na transação e escreva ao lado\n"
    "'# ADR-025: escrita acoplada — <qual atomicidade>'."
)


def _is_signal_send(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"send", "send_robust"}
        and any(k.arg == "sender" for k in node.keywords)
    )


def _is_on_commit(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "on_commit") or (
        isinstance(func, ast.Name) and func.id == "on_commit"
    )


def _deferred_names(tree: ast.Module) -> set[str]:
    """Nomes de função citados dentro de um ``on_commit(...)`` do módulo."""
    names: set[str] = set()
    for node in nodes(tree):
        if not _is_on_commit(node):
            continue
        for arg in [*node.args, *(k.value for k in node.keywords)]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
    return names


def _deferred_nodes(tree: ast.Module) -> set[int]:
    """``id`` de todo nó dentro dos argumentos de um ``on_commit(...)`` e das funções citadas."""
    names = _deferred_names(tree)
    inside: set[int] = set()
    for node in nodes(tree):
        roots: list[ast.AST] = []
        if _is_on_commit(node):
            roots = [*node.args, *(k.value for k in node.keywords)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            roots = [node]
        for root in roots:
            inside.update(id(sub) for sub in ast.walk(root))
    return inside


def _is_directive_handler(cls: ast.ClassDef) -> bool:
    """Classe com ``handle(self, *, message, ctx)``: handler de Directive (ADR-003)."""
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "handle":
            kwonly = {a.arg for a in item.args.kwonlyargs}
            if {"message", "ctx"} <= kwonly:
                return True
    return False


def _directive_handler_nodes(tree: ast.Module) -> set[int]:
    """``id`` de todo nó dentro de um handler de Directive.

    O worker (``process_directives``) e o dispatcher (``orderman.dispatch``, chamado por
    ``on_commit``) rodam ``handle()`` FORA de transação: o fato que o handler anuncia já
    está gravado, então o ``send`` ali é pós-COMMIT por contrato, não por acaso.
    """
    inside: set[int] = set()
    for node in nodes(tree):
        if isinstance(node, ast.ClassDef) and _is_directive_handler(node):
            inside.update(id(sub) for sub in ast.walk(node))
    return inside


def findings_for(rel: str, tree: ast.Module, lines: list[str]) -> list[Finding]:
    deferred = _deferred_nodes(tree) | _directive_handler_nodes(tree)
    found = []
    for node in nodes(tree):
        if not _is_signal_send(node) or id(node) in deferred:
            continue
        window = lines[max(0, node.lineno - 4) : node.lineno]
        if any(MARKER.search(line) for line in window):
            continue
        signal = ast.unparse(node.func.value)
        qual = scopes(tree).get(id(node), "<module>")
        found.append(
            Finding(f"{rel}::{qual}::{signal}", f"{rel}:{node.lineno}", f"{signal}.{node.func.attr} na transação")
        )
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, lines in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree, lines)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Signal depois do COMMIT (ADR-025)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
