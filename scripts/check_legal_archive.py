#!/usr/bin/env python
"""Recusa alteração ou remoção de uma versão legal já arquivada.

Novas versões entram como novos arquivos. Um documento existente nunca é
reescrito: o pedido guarda URL e SHA-256 (`Order.snapshot["data"]["legal"]`)
para que o cliente reproduza o texto que valia no pedido mesmo depois de uma
revisão da página viva. Ver `shopman/storefront/presentation/legal.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from check_adr015 import _git, resolve_diff_base

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PREFIX = "surfaces/storefront-nuxt/public/legal/"
ARCHIVE_NAME = re.compile(
    r"^surfaces/storefront-nuxt/public/legal/"
    r"(?:privacy|terms)/\d{4}-\d{2}-\d{2}\.html$"
)


def classify_archive_changes(name_status_lines: list[str]) -> list[tuple[str, str, str]]:
    """Return ``(status, path, reason)`` for unsafe archive changes."""
    violations: list[tuple[str, str, str]] = []
    for line in name_status_lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        for path in (item.strip() for item in parts[1:]):
            if not path.startswith(ARCHIVE_PREFIX):
                continue
            if not status.startswith("A"):
                violations.append((status, path, "versão existente não pode ser alterada ou removida"))
            elif not ARCHIVE_NAME.fullmatch(path):
                violations.append((status, path, "use privacy/AAAA-MM-DD.html ou terms/AAAA-MM-DD.html"))
    return violations


def archive_violations(base: str, repo_root: Path = ROOT) -> list[tuple[str, str, str]]:
    diff = _git(["diff", "--name-status", "--no-renames", base, "HEAD"], cwd=repo_root)
    if diff.returncode != 0:
        raise RuntimeError(f"git diff contra {base!r} falhou: {diff.stderr.strip()}")
    return classify_archive_changes(diff.stdout.splitlines())


def main() -> int:
    base, description = resolve_diff_base(ROOT)
    if base is None:
        print(f"ERRO: não foi possível resolver a base: {description}")
        return 1
    violations = archive_violations(base)
    if violations:
        print("ERRO: o arquivo legal é append-only; publique uma nova versão:")
        for status, path, reason in violations:
            print(f"  {status} {path}: {reason}")
        return 1
    print(f"arquivo legal íntegro ({description})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
