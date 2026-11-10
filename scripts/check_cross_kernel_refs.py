#!/usr/bin/env python3
"""C3 — identidade cross-domain por ref, nunca FK/pk de outro kernel (AST, fail-closed com baseline).

Constituição C3 / ADR-004: um kernel referencia entidade de outro kernel por ``sku``, ``ref``
ou ``*_ref``, nunca por ``ForeignKey``/``OneToOneField``/``ManyToManyField``. A guarda lê os
modelos de ``packages/`` (inclusive ``contrib/``) e resolve o ALVO do campo pelos dois
caminhos que existem:

- string ``"<app_label>.<Model>"``: o rótulo é mapeado ao pacote que o declara
  (``apps.py``, ``label = "..."``), então ``"craftsman_stockman.X"`` é do Craftsman;
- nome importado (``from shopman.offerman.models import Product`` + ``ForeignKey(Product)``,
  ou ``models_mod.Product``): o módulo do import diz o kernel.

FK para ``settings.AUTH_USER_MODEL``, ``contenttypes`` e apps de terceiros não é C3. O
orquestrador (``shopman/``) não é kernel: é o encontro dos domínios (C4) e pode apontar FK.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_baseline import (  # noqa: E402
    KERNELS,
    ROOT,
    Finding,
    import_map,
    iter_sources,
    kernel_of,
    kernel_of_module,
    nodes,
    run,
    scopes,
)

SECTION = "cross_kernel_refs"
RELATION_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}
LABEL_RE = re.compile(r"""^\s*label\s*=\s*["']([a-z0-9_]+)["']""", re.MULTILINE)
RULE = (
    "C3: entre kernels a referência é textual (sku, ref, *_ref), nunca FK/pk. Guarde o ref e\n"
    "resolva pelo serviço do kernel dono; o encontro com FK, se preciso, mora no orquestrador."
)


def label_map(root: Path = ROOT) -> dict[str, str]:
    """Rótulo de app Django → kernel que o declara."""
    labels: dict[str, str] = {}
    for apps in (root / "packages").glob("*/shopman/**/apps.py"):
        rel = apps.relative_to(root)
        if "build" in rel.parts:
            continue
        kernel = kernel_of(rel.as_posix())
        if kernel is None:
            continue
        for label in LABEL_RE.findall(apps.read_text()):
            labels[label] = kernel
    for kernel in KERNELS:
        labels.setdefault(kernel, kernel)
    return labels


def _field_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _target(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg == "to":
            return kw.value
    return None


def _target_kernel(target: ast.AST, imports: dict[str, str], labels: dict[str, str]) -> tuple[str, str] | None:
    """(kernel, nome legível) do alvo, quando o alvo é de um kernel."""
    if isinstance(target, ast.Constant) and isinstance(target.value, str) and "." in target.value:
        label, model = target.value.split(".", 1)
        kernel = labels.get(label)
        return (kernel, target.value) if kernel else None
    if isinstance(target, ast.Name):
        kernel = kernel_of_module(imports.get(target.id))
        return (kernel, target.id) if kernel else None
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        kernel = kernel_of_module(imports.get(target.value.id))
        return (kernel, ast.unparse(target)) if kernel else None
    return None


def findings_for(rel: str, tree: ast.Module, labels: dict[str, str]) -> list[Finding]:
    own = kernel_of(rel)
    if own is None:
        return []
    imports = import_map(tree)
    found = []
    for node in nodes(tree):
        if not isinstance(node, ast.Call) or _field_name(node) not in RELATION_FIELDS:
            continue
        target = _target(node)
        resolved = _target_kernel(target, imports, labels) if target is not None else None
        if resolved is None or resolved[0] == own:
            continue
        kernel, shown = resolved
        qual = scopes(tree).get(id(node), "<module>")
        found.append(
            Finding(
                f"{rel}::{qual}::{_field_name(node)}->{shown}",
                f"{rel}:{node.lineno}",
                f"{_field_name(node)} para {shown} ({own} -> {kernel})",
            )
        )
    return found


def collect(root: Path = ROOT) -> list[Finding]:
    labels = label_map(root)
    return [f for rel, tree, _ in iter_sources(("packages",), root) for f in findings_for(rel, tree, labels)]


def main(argv: list[str] | None = None) -> int:
    return run(SECTION, "Ref entre kernels, nunca FK (C3)", collect(), argv, rule=RULE)


if __name__ == "__main__":
    sys.exit(main())
