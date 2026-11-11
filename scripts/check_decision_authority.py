"""Detecta duplicação de autoridade de decisão (Constituição C5 / ADR-037).
A regra: cada decisão canônica tem UM ponto autoritativo no kernel dono. Este gate
falha se (1) um símbolo de decisão já-duplicado ainda estiver definido fora do dono, ou
(2) uma decisão canônica estiver definida em mais de um lugar.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = {
    "promise_for_sku": "packages/stockman",
    "decision_from_availability": "packages/stockman",
}
FORBIDDEN = {
    "_stock_decision": "shopman/shop",
}
DEF_RE = re.compile(r"^\s*def (\w+)\(")

def main() -> int:
    violations = []
    for root in (ROOT / "packages", ROOT / "shopman" / "shop"):
        for path in root.rglob("*.py"):
            if any(p in {"__pycache__", "tests", "test"} for p in path.parts):
                continue
            rel = str(path.relative_to(ROOT))
            try:
                text = path.read_text()
            except OSError:
                continue
            for m in DEF_RE.finditer(text):
                name = m.group(1)
                if name in FORBIDDEN and rel.startswith(FORBIDDEN[name]):
                    violations.append(f"{rel}: {name} ainda definido fora do dono")
                if name in CANONICAL and not rel.startswith(CANONICAL[name]):
                    violations.append(f"{rel}: {name} fora do dono {CANONICAL[name]}")
    if violations:
        print("DUPLICACAO DE AUTORIDADE DE DECISAO:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: decisoes canonicas com autoridade unica.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

