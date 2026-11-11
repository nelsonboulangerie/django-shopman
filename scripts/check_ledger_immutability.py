"""C11 — ledger imutável: reescrita de história é o alvo (REPORT-ONLY, AST).

Regra (ADR-022/C11): correção é NOVO lançamento, nunca reescrita. Os ledgers IMUTÁVEIS são
três: Entry (caixa), Move (estoque), PaymentTransaction (pagamento — save() bloqueia após criar).
Directive/Session/Hold/Quant/Order/WorkOrder são estado mutável e NÃO são sinalizados.
Este script flagra QuerySet.update/delete/bulk_update sobre esses três. Report-only.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE = {"update", "delete", "bulk_update"}
IMMUTABLE_LEDGERS = {"Entry", "Move", "PaymentTransaction"}


def _ledger_rewrite(node: ast.Call):
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in WRITE:
        return None
    recv = func.value
    if isinstance(recv, ast.Attribute) and recv.attr == "objects" and isinstance(recv.value, ast.Name):
        return recv.value.id if recv.value.id in IMMUTABLE_LEDGERS else None
    if isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute) and recv.func.attr in {"filter", "exclude", "all"}:
        inner = recv.func.value
        if isinstance(inner, ast.Attribute) and inner.attr == "objects" and isinstance(inner.value, ast.Name):
            return inner.value.id if inner.value.id in IMMUTABLE_LEDGERS else None
    return None


def main() -> int:
    candidates = []
    for root in (ROOT / "packages", ROOT / "shopman"):
        for path in root.rglob("*.py"):
            if any(p in {"__pycache__", "tests", "test", "migrations"} for p in path.parts):
                continue
            rel = str(path.relative_to(ROOT))
            try:
                tree = ast.parse(path.read_text(), filename=str(path))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    model = _ledger_rewrite(node)
                    if model:
                        candidates.append(f"{rel}:{node.lineno}: {model}.objects.{node.func.attr}")
    if candidates:
        print(f"REESCRITA DE LEDGER IMUTAVEL (C11, {len(candidates)}):")
        for c in candidates:
            print(f"  - {c}")
    else:
        print("Nenhuma reescrita dos ledgers imutaveis (Entry/Move/PaymentTransaction).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
