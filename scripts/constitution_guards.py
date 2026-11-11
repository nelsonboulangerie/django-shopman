#!/usr/bin/env python3
"""Roda as guardas da Constituição num processo só (``make constitution-guards``).

Cada ``scripts/check_*.py`` da lista continua executável sozinho; aqui elas dividem o parse
memorizado em ``guard_baseline`` (o custo dominante é ler ~1.500 arquivos), e o resultado é
um código de saída único: reprova se qualquer uma reprovar. ``--strict`` passa adiante.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

GUARDS = (
    "check_guard_map",
    "check_decision_authority",
    "check_cross_kernel_refs",
    "check_order_lifecycle_owner",
    "check_lifecycle_functional",
    "check_money_integer",
    "check_read_side_immutability",
    "check_ledger_immutability",
    "check_signal_on_commit",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    failed = []
    for name in GUARDS:
        print(f"── {name} ──")
        module = _load(name)
        code = module.main() if name == "check_guard_map" else module.main(args)
        if code:
            failed.append(name)
        print()
    if failed:
        print(f"REPROVADO: {', '.join(failed)}")
        return 1
    print(f"OK: {len(GUARDS)} guardas da Constituição.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
