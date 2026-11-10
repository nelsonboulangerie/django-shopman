"""C2 gate: dinheiro é inteiro em unidade mínima (_q), nunca float/decimal.
Falha se um campo de modelo com nome monetário usar FloatField ou DecimalField.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MONETARY = re.compile(r"\w*(?:_q|price|amount|cost|total|value|change|difference|balance|discount|fee|margin)\w*")
FLOAT = re.compile(r"models\.(FloatField|DecimalField)\(")

def main() -> int:
    violations = []
    for path in (ROOT / "packages").rglob("models*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(ROOT))
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for i in range(len(lines) - 1):
            if MONETARY.search(lines[i]) and FLOAT.search(lines[i] + " " + lines[i + 1]):
                violations.append(f"{rel}:{i + 1}: campo monetario com float/decimal")
    if violations:
        print("DINHEIRO EM FLOAT/DECIMAL (C2):")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: dinheiro inteiro em centavos.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

