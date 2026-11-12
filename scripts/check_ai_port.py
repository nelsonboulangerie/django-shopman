#!/usr/bin/env python3
"""Trava da porta única de IA (ID3A-PLAN, E1).

Toda chamada paga a modelo passa por ``shopman/shop/ai.py``, que freia e mede
(``ai_governor``). Até 11/11/2026 um placar falava com o provedor sem freio e
gastou cerca de US$ 1.180. Esta trava reprova, fora da porta:

- criar cliente do SDK (``Anthropic(...)``, ``AsyncAnthropic(...)``);
- escrever o endereço de API de um provedor de IA num literal de texto.

Importar o ``anthropic`` para pegar a classe de um erro continua livre. Stdlib-only,
por AST. Fora da varredura: ``tests/``, ``test_*.py``, ``conftest.py``, migrações.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNED = ("shopman", "config", "packages")
#: A porta, e o cadastro de conexão (o texto de ajuda do Admin cita o endereço da DeepSeek).
PORT = {Path("shopman/shop/ai.py"), Path("shopman/shop/models/ai_connection.py")}
CLIENT_NAMES = frozenset({"Anthropic", "AsyncAnthropic"})
API_HOSTS = ("api.anthropic.com", "api.deepseek.com", "api.typesafe.ai")


def _skipped(path: Path) -> bool:
    parts = set(path.parts)
    return (
        "tests" in parts
        or "migrations" in parts
        or path.name.startswith("test_")
        or path.name == "conftest.py"
        or "node_modules" in parts
    )


def violations_in(path: Path, source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in CLIENT_NAMES:
                found.append(f"{path}:{node.lineno}: cliente do SDK de IA criado fora da porta ({name})")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for host in API_HOSTS:
                if host in node.value:
                    found.append(f"{path}:{node.lineno}: endereço de API de IA ({host}) fora da porta")
    return found


def scan(root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for base in SCANNED:
        for path in sorted((root / base).rglob("*.py")):
            relative = path.relative_to(root)
            if relative in PORT or _skipped(relative):
                continue
            found.extend(violations_in(relative, path.read_text(encoding="utf-8")))
    return found


def main() -> int:
    found = scan()
    if found:
        print("Porta de IA: chamada a modelo fora de shopman/shop/ai.py (sem freio nem medidor).")
        print("Use ai.anthropic_client(<propósito>) ou ai.jev_post(...).")
        for line in found:
            print(f"  {line}")
        return 1
    print("[OK] porta de IA: nenhum cliente de SDK nem endereço de API fora de shopman/shop/ai.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
