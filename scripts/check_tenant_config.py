#!/usr/bin/env python3
"""Trava barata de multi-loja (ADR-042): configuração de loja não cresce por env/settings.

O alvo é um schema do Postgres por loja, com a `Shop` singleton por schema. Até lá,
nenhuma configuração ou credencial NOVA de uma loja entra por variável de ambiente ou
por `settings`: entra na `Shop`, no descritor de instância (`config/instances/`) ou num
cofre futuro. O que já existe fica congelado numa baseline versionada
(`scripts/tenant-config-baseline.json`), contado por arquivo.

O que conta (AST, sem importar Django):

- ``settings``: leitura de configuração por loja via ``django.conf.settings``, isto é,
  ``settings.<NOME>`` e ``getattr/hasattr(settings, "<NOME>")`` em que ``<NOME>`` começa
  por um dos prefixos de ``TENANT_PREFIXES`` (o alias do import é respeitado), mais todo
  ``getattr(settings, <nome montado>)``, que esconde o prefixo da busca;
- ``env``: toda leitura direta do ambiente em runtime (``os.environ``, ``os.getenv`` e
  ``environ``/``getenv`` importados de ``os``), qualquer que seja o nome; runtime que lê o
  ambiente sem passar pelo settings é exatamente o caminho que não escala para N lojas;
- ``settings_env``: nos módulos de settings (``config/settings*.py``), as variáveis de
  ambiente lidas cujo nome literal começa por um prefixo por loja. É a porta de entrada
  de uma credencial nova, e o único ponto onde o settings é contado.

O que fica de fora, e por quê:

- ``tests/``, ``test_*.py``, ``conftest.py``: teste lê settings para provar o runtime;
- ``migrations/``: história, não runtime;
- nos módulos de settings, as leituras de infraestrutura (banco, Redis, hosts, CSP...):
  são do ambiente de execução, não da loja;
- ``scripts/`` e ``surfaces/``: ferramenta de repositório e apps Nuxt (outra trava).

Crescer reprova; diminuir passa e sugere ``--update`` para a folga não ser reaproveitada.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "scripts" / "tenant-config-baseline.json"
SCAN_ROOTS = ("shopman", "packages", "config")
SKIP_PARTS = frozenset(
    {"tests", "migrations", "__pycache__", "build", "dist", ".venv", "node_modules", "site-packages"}
)
TENANT_PREFIXES = (
    "SHOPMAN_",
    "EFI",
    "FOCUS",
    "STRIPE",
    "MANYCHAT",
    "IFOOD",
    "COMTELE",
    "MACHINE",
    "TAON",
)
TENANT_NAME = re.compile(rf"^(?:{'|'.join(TENANT_PREFIXES)})")
SETTINGS_MODULE = re.compile(r"^config/settings[a-z0-9_]*\.py$")
KINDS = ("settings", "env", "settings_env")

WHERE_IT_LIVES = (
    "Configuração ou credencial nova de uma loja não entra por variável de ambiente nem por\n"
    "`settings` (ADR-042, alvo: um schema do Postgres por loja). Ela mora em:\n"
    "  - campo ou JSON da `Shop` (shopman/shop/models/shop.py), quando é dado da loja;\n"
    "  - descritor de instância (config/instances/*.json), quando é contrato de bootstrap,\n"
    "    e só o NOME do segredo, em ownership.secret;\n"
    "  - o cofre de credenciais por loja, quando ele existir.\n"
    "Configuração de ambiente que não é da loja (infraestrutura) pode crescer: rode\n"
    "`python scripts/check_tenant_config.py --update` e diga o motivo no PR."
)


@dataclass(frozen=True)
class FileCounts:
    settings: int = 0
    env: int = 0
    settings_env: int = 0

    def as_dict(self) -> dict[str, int]:
        return {kind: getattr(self, kind) for kind in KINDS if getattr(self, kind)}

    def total(self) -> int:
        return sum(getattr(self, kind) for kind in KINDS)


def _is_skipped(rel: Path) -> bool:
    if SKIP_PARTS.intersection(rel.parts):
        return True
    return rel.name.startswith("test_") or rel.name == "conftest.py"


def runtime_sources(root: Path = ROOT) -> list[Path]:
    paths: list[Path] = []
    for base in SCAN_ROOTS:
        directory = root / base
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            if not _is_skipped(path.relative_to(root)):
                paths.append(path)
    return sorted(paths)


def _string_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


class _Collector(ast.NodeVisitor):
    def __init__(self, tree: ast.Module, *, settings_module: bool):
        self.settings_module = settings_module
        self.settings_aliases: set[str] = set()
        self.conf_aliases: set[str] = set()
        self.os_aliases: set[str] = set()
        self.env_names: set[str] = set()
        self.settings = 0
        self.env = 0
        self.settings_env: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if node.module == "django.conf" and alias.name == "settings":
                        self.settings_aliases.add(bound)
                    elif node.module == "django" and alias.name == "conf":
                        self.conf_aliases.add(bound)
                    elif node.module == "os" and alias.name in {"environ", "getenv"}:
                        self.env_names.add(bound)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        self.os_aliases.add(alias.asname or "os")

    # -- settings ---------------------------------------------------------
    def _is_settings(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.settings_aliases
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "settings"
            and isinstance(node.value, ast.Name)
            and node.value.id in self.conf_aliases
        )

    # -- env --------------------------------------------------------------
    def _is_env(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.env_names
        return (
            isinstance(node, ast.Attribute)
            and node.attr in {"environ", "getenv"}
            and isinstance(node.value, ast.Name)
            and node.value.id in self.os_aliases
        )

    def _env_key(self, node: ast.AST) -> str | None:
        """Nome literal lido do ambiente: os.environ.get("X"), os.getenv("X"), os.environ["X"], _env_x("X")."""
        if isinstance(node, ast.Call):
            func = node.func
            if self._is_env(func):
                return _string_arg(node)
            if isinstance(func, ast.Attribute) and self._is_env(func.value):
                return _string_arg(node)
            if isinstance(func, ast.Name) and func.id.startswith("_") and "env" in func.id.lower():
                return _string_arg(node)
        if isinstance(node, ast.Subscript) and self._is_env(node.value):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
        return None

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not self.settings_module and self._is_settings(node.value) and TENANT_NAME.match(node.attr):
            self.settings += 1
        if not self.settings_module and self._is_env(node):
            self.env += 1
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if not self.settings_module and node.id in self.env_names and isinstance(node.ctx, ast.Load):
            self.env += 1

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            not self.settings_module
            and isinstance(func, ast.Name)
            and func.id in {"getattr", "hasattr"}
            and len(node.args) >= 2
            and self._is_settings(node.args[0])
            and self._tenant_or_dynamic(node.args[1])
        ):
            self.settings += 1
        self._record_settings_env(node)
        self.generic_visit(node)

    @staticmethod
    def _tenant_or_dynamic(name: ast.AST) -> bool:
        """Nome literal com prefixo de loja, ou nome dinâmico (``getattr(settings, nome)``).

        O nome dinâmico conta porque esconde o prefixo da busca: é o atalho de quem lê
        ``SHOPMAN_<X>_BASE_URL`` montando a string.
        """
        if isinstance(name, ast.Constant):
            return isinstance(name.value, str) and bool(TENANT_NAME.match(name.value))
        return True

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._record_settings_env(node)
        self.generic_visit(node)

    def _record_settings_env(self, node: ast.AST) -> None:
        if not self.settings_module:
            return
        key = self._env_key(node)
        if key and TENANT_NAME.match(key):
            self.settings_env.add(key)


def count_source(source: str, rel: str) -> FileCounts:
    tree = ast.parse(source, filename=rel)
    collector = _Collector(tree, settings_module=bool(SETTINGS_MODULE.match(rel)))
    collector.visit(tree)
    return FileCounts(
        settings=collector.settings,
        env=collector.env,
        settings_env=len(collector.settings_env),
    )


def measure(root: Path = ROOT, paths: Iterable[Path] | None = None) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for path in paths if paths is not None else runtime_sources(root):
        rel = path.relative_to(root).as_posix()
        counts = count_source(path.read_text(encoding="utf-8"), rel)
        if counts.total():
            result[rel] = counts.as_dict()
    return dict(sorted(result.items()))


def load_baseline(path: Path | None = None) -> dict[str, dict[str, int]]:
    data = json.loads((path or BASELINE_PATH).read_text(encoding="utf-8"))
    return data["files"]


def write_baseline(current: dict[str, dict[str, int]], path: Path | None = None) -> None:
    totals = {kind: sum(entry.get(kind, 0) for entry in current.values()) for kind in KINDS}
    payload = {
        "_doc": (
            "Baseline da trava de multi-loja (ADR-042). Contagem por arquivo de leituras de "
            "configuração por loja: settings = settings.<PREFIXO>; env = os.environ/os.getenv em "
            "runtime; settings_env = variável de ambiente por loja lida em config/settings*.py. "
            "Só diminui. Regere com: python scripts/check_tenant_config.py --update"
        ),
        "prefixes": list(TENANT_PREFIXES),
        "totals": totals,
        "files": current,
    }
    (path or BASELINE_PATH).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def compare(current: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]]) -> tuple[list[str], list[str]]:
    grew: list[str] = []
    shrank: list[str] = []
    for rel in sorted(set(current) | set(baseline)):
        now = current.get(rel, {})
        before = baseline.get(rel, {})
        for kind in KINDS:
            n, b = now.get(kind, 0), before.get(kind, 0)
            if n > b:
                grew.append(f"{rel}: {kind} {b} -> {n}")
            elif n < b:
                shrank.append(f"{rel}: {kind} {b} -> {n}")
    return grew, shrank


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="regrava a baseline com a contagem atual")
    args = parser.parse_args(argv)

    current = measure()
    totals = {kind: sum(entry.get(kind, 0) for entry in current.values()) for kind in KINDS}
    summary = (
        f"{len(current)} arquivos; settings.<loja> {totals['settings']}, "
        f"env em runtime {totals['env']}, env de loja no settings {totals['settings_env']}"
    )

    if args.update:
        write_baseline(current)
        print(f"tenant-config: baseline regravada ({summary}).")
        return 0

    if not BASELINE_PATH.exists():
        print(f"tenant-config: baseline ausente em {BASELINE_PATH}.", file=sys.stderr)
        return 1

    grew, shrank = compare(current, load_baseline())
    if grew:
        print("tenant-config: REPROVADO, configuração de loja cresceu por env/settings:", file=sys.stderr)
        for line in grew:
            print(f"  + {line}", file=sys.stderr)
        print("", file=sys.stderr)
        print(WHERE_IT_LIVES, file=sys.stderr)
        return 1

    print(f"tenant-config: OK ({summary}).")
    if shrank:
        print("tenant-config: a contagem DIMINUIU; trave a folga com --update:")
        for line in shrank:
            print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
