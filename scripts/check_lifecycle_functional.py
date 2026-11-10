#!/usr/bin/env python3
"""C7 — lifecycle funcional e config-driven, sem subclasse (AST, fail-closed com baseline).

Constituição C7 / ADR-007: o orquestrador despacha fases explícitas dirigidas pela
configuração do canal (``lifecycle.dispatch(order, phase)`` + ``ChannelConfig``); não há
classe de lifecycle nem herança que esconda decisão de instância. A guarda reprova, em
``shopman/``, ``packages/`` e ``config/``:

1. classe que HERDA de uma base cujo nome tem ``Lifecycle``, ``Flow`` ou ``Phase``
   (``class NelsonFlow(BaseFlow)``);
2. classe cujo NOME termina em ``Lifecycle`` ou ``Flow`` (a base de uma hierarquia futura).

``Enum``/``TextChoices`` de fase (``class Phase(TextChoices)``) é vocabulário, não lifecycle,
e não conta. A versão regex lia linha a linha e perdia base quebrada em várias linhas.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import ROOT, Finding, iter_sources, nodes, run, scopes  # noqa: E402

SECTION = "lifecycle_functional"
SCAN_ROOTS = ("shopman", "packages", "config")
BASE_RE = re.compile(r"(Lifecycle|Flow|Phase)")
NAME_RE = re.compile(r"(Lifecycle|Flow)$")
VOCABULARY_BASES = {"Enum", "StrEnum", "IntEnum", "TextChoices", "IntegerChoices", "Choices"}
RULE = (
    "C7: lifecycle é funcional. Comportamento por canal vem de ChannelConfig e de fases\n"
    "despachadas por lifecycle.dispatch(); não crie classe/herança de lifecycle."
)


def _base_name(base: ast.AST) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    return ""


def findings_for(rel: str, tree: ast.Module) -> list[Finding]:
    found = []
    for node in nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [_base_name(b) for b in node.bases]
        if any(b in VOCABULARY_BASES for b in bases):
            continue
        hits = [b for b in bases if BASE_RE.search(b)]
        if hits:
            detail = f"class {node.name}({', '.join(hits)}): herança de lifecycle"
        elif NAME_RE.search(node.name):
            detail = f"class {node.name}: classe de lifecycle"
        else:
            continue
        qual = scopes(tree).get(id(node), "<module>")
        found.append(Finding(f"{rel}::{qual}::class {node.name}", f"{rel}:{node.lineno}", detail))
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    return [f for rel, tree, _ in iter_sources(SCAN_ROOTS, root) for f in findings_for(rel, tree)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Lifecycle funcional (C7)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
