"""ADR-025 gate: anúncio por signal acontece DEPOIS do COMMIT (heurística).
Falha se um call site de signal.send/<sinal>.send não estiver co-localizado com
transaction.on_commit em janela adjacente (disparar dentro da transação cria efeito
fantasma sob rollback — o P1 do Payman).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOW = 8
SEND_RE = re.compile(r"signal\.send\(|_signals\.\w+\.send\(|\.send\(sender=")

def main() -> int:
    violations = []
    for root in (ROOT / "packages", ROOT / "shopman" / "shop"):
        for path in root.rglob("*.py"):
            if any(p in {"__pycache__", "tests", "test"} for p in path.parts):
                continue
            rel = str(path.relative_to(ROOT))
            try:
                lines = path.read_text().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines):
                if SEND_RE.search(line) and "on_commit" not in line:
                    lo = max(0, i - WINDOW)
                    hi = min(len(lines), i + WINDOW + 1)
                    if not any("on_commit" in lines[j] for j in range(lo, hi)):
                        violations.append(f"{rel}:{i + 1}: send fora de on_commit")
    if violations:
        print("SIGNAL FORA DE ON_COMMIT (ADR-025):")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: signals anunciados apos o commit.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

