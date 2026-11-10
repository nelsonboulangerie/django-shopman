"""C6 — ciclo de Order pertence ao Orderman (REPORT-ONLY).
Detecta DEFINICAO de estado/transição de Order fora do Orderman (segundo ciclo paralelo).
Chamar order.transition_status() a partir do orquestrador é consumo legítimo (ADR-006),
não violação — por isso NÃO é sinalizado aqui.
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DEF_RE = re.compile(r"(class\s+OrderStatus|OrderStatus\s*=|TRANSITIONS\s*=|ORDER_STATES\s*=)")

def main() -> int:
    candidates = []
    for path in (ROOT / "shopman").rglob("*.py"):
        if any(p in {"__pycache__", "tests", "test"} for p in path.parts):
            continue
        rel = str(path.relative_to(ROOT))
        if "orderman" in rel:
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if STATE_DEF_RE.search(line):
                candidates.append(f"{rel}:{i}: {line.strip()[:80]}")
    if candidates:
        print(f"CANDIDATOS A REVISAO (C6, report-only, {len(candidates)}):")
        for c in candidates[:30]:
            print(f"  - {c}")
    else:
        print("Nenhuma definicao de ciclo de Order fora do orderman.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
