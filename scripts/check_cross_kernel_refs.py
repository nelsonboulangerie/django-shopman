"""C3 — identidade cross-domain por ref, não FK/pk de outro kernel (REPORT-ONLY).
Falha candidata: ForeignKey/OneToOne/ManyToMany com alvo string apontando para app de OUTRO
kernel. Regex cobre o alvo string (inequívoco); alvo importado exige AST (fora deste script).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNELS = {"offerman", "stockman", "craftsman", "orderman", "guestman", "doorman", "payman", "buyman", "fiscalman", "cashman", "watchman", "refs", "utils"}
FK_RE = re.compile(r"(ForeignKey|OneToOneField|ManyToManyField)\(\s*['\"]([a-z_]+)\.(\w+)['\"]")

def main() -> int:
    candidates = []
    for pkg in (ROOT / "packages").iterdir():
        if not pkg.is_dir():
            continue
        # app label do kernel atual = nome do subpacote sob packages/<pkg>/shopman/
        sub = pkg / "shopman"
        if not sub.is_dir():
            continue
        own_kernel = pkg.name
        for path in sub.rglob("models*.py"):
            if any(p in {"__pycache__", "tests", "test"} for p in path.parts):
                continue
            rel = str(path.relative_to(ROOT))
            try:
                text = path.read_text()
            except OSError:
                continue
            for m in FK_RE.finditer(text):
                target_app = m.group(2)
                if target_app in KERNELS and target_app != own_kernel:
                    candidates.append(f"{rel}: FK para {target_app}.{m.group(3)} (cross-kernel)")
    if candidates:
        print(f"CANDIDATOS A REVISAO (C3, report-only, {len(candidates)}):")
        for c in candidates[:30]:
            print(f"  - {c}")
    else:
        print("Nenhum FK cross-kernel por alvo string.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
