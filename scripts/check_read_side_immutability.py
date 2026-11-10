"""C10 — read-side não escreve (heurística REPORT-ONLY, não é gate).

Regra (ADR-021/C10): projection/BI pode MATERIALIZAR derivado recomputável, mas não pode
escrever no ledger de um kernel nem virar fonte do fato. Regex não distingue dict.update de
ORM.update, então este script só APONTA candidatos (`.objects.*`, `.save(`, `.delete(`) para
revisão humana. Nunca falha a esteira; imprime e sai 0.
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# apenas acesso ORM inequívoco: Model.objects.<write> — não pega dict/set.update
ORM = re.compile(r"\.objects\.(create|update|delete|bulk_create|bulk_update|get_or_create|update_or_create|filter\(.*\)\.update)\(|\.(save|delete|bulk_create|bulk_update)\(")

def main() -> int:
    candidates = []
    for root in (ROOT / "shopman", ROOT / "packages"):
        for path in root.rglob("projections/**/*.py"):
            rel = str(path.relative_to(ROOT))
            try:
                text = path.read_text()
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if ORM.search(line):
                    candidates.append(f"{rel}:{i}: {line.strip()[:80]}")
    if candidates:
        print(f"CANDIDATOS A REVISAO (C10, report-only, {len(candidates)}):")
        for c in candidates[:40]:
            print(f"  - {c}")
        if len(candidates) > 40:
            print(f"  ... e mais {len(candidates) - 40}")
    else:
        print("Nenhum candidato de escrita em projection.")
    return 0  # report-only: nunca falha

if __name__ == "__main__":
    raise SystemExit(main())
