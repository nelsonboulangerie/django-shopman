"""O cashman é um core: o código de domínio não importa orquestrador, superfície
nem outro core (ADR-001). Só ``contrib/`` pode olhar para fora, e mesmo assim
só para o Unfold e o ``shopman.utils``."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    "shopman.shop",
    "shopman.storefront",
    "shopman.backstage",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.craftsman",
    "shopman.orderman",
    "shopman.guestman",
    "shopman.doorman",
    "shopman.payman",
    "shopman.buyman",
    "shopman.fiscalman",
    "config",
)


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module


def test_domain_code_imports_nothing_from_the_rest_of_the_suite():
    violations = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        parts = path.relative_to(PACKAGE_ROOT).parts
        if "tests" in parts or "__pycache__" in parts or "contrib" in parts or "migrations" in parts:
            continue
        for lineno, module in _imports(path):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{lineno} imports {module}")
    assert not violations, "\n".join(violations)


def test_contrib_only_reaches_utils_and_unfold():
    violations = []
    for path in sorted((PACKAGE_ROOT / "contrib").rglob("*.py")):
        for lineno, module in _imports(path):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{lineno} imports {module}")
    assert not violations, "\n".join(violations)
