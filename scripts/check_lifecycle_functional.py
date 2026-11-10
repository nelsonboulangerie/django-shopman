"""C7 — lifecycle funcional e config-driven, sem subclasse (REPORT-ONLY, heurística).

Regra (ADR-007): o orquestrador despacha fases explícitas dirigidas por configuração; não
há subclasse de lifecycle. Este script APONTA classes que herdam de base com nome Flow/
Lifecycle/Phase para revisão humana. Não falha a esteira (regex não é AST).
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASS_RE = re.compile(r"class\s+\w+\s*\([^)]*(Flow|Lifecycle|Phase)\w*[^)]*\)\s*:")

def main() -> int:
    candidates = []
    for root in (ROOT / "shopman", ROOT / "packages"):
        for path in root.rglob("*.py"):
            if any(p in {"__pycache__", "tests", "test"} for p in path.parts):
                continue
            rel = str(path.relative_to(ROOT))
            try:
                text = path.read_text()
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if CLASS_RE.search(line):
                    candidates.append(f"{rel}:{i}: {line.strip()[:80]}")
    if candidates:
        print(f"CANDIDATOS A REVISAO (C7, report-only, {len(candidates)}):")
        for c in candidates[:30]:
            print(f"  - {c}")
    else:
        print("Nenhuma subclasse de lifecycle/flow encontrada.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
