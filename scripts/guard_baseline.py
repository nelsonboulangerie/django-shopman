"""Base comum das guardas da Constituição (C2, C3, C5, C6, C7, C10, C11, ADR-025).

Sem importar Django: ``ast`` da biblioteca padrão. Cada guarda produz *achados* com uma
chave estável (arquivo + função/classe + detalhe, nunca o número da linha) e os compara com
a seção dela em ``scripts/constitution-baseline.json``:

- achado sem entrada na baseline, ou em número maior que o registrado: REPROVA (crescer);
- entrada da baseline que não acontece mais, ou acontece menos: REPROVA (obsoleta), para a
  folga não ser reaproveitada; quem conserta apaga a entrada no mesmo PR;
- toda entrada declara ``classe`` (``violacao`` ou ``excecao``), ``motivo`` e, quando é
  violação, a ``frente`` que conserta.

``--strict`` ignora a baseline e mostra o estado bruto (sai 1 se houver qualquer achado).
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "scripts" / "constitution-baseline.json"
SKIP_PARTS = frozenset(
    {"tests", "test", "migrations", "__pycache__", "build", "dist", ".venv", "node_modules", "site-packages"}
)
KERNELS = (
    "buyman",
    "cashman",
    "craftsman",
    "doorman",
    "fiscalman",
    "guestman",
    "offerman",
    "orderman",
    "payman",
    "refs",
    "stockman",
    "utils",
    "watchman",
)
CLASSES = ("violacao", "excecao")


@dataclass(frozen=True)
class Finding:
    key: str
    where: str  # arquivo:linha, só para leitura humana
    detail: str


def is_skipped(rel: Path) -> bool:
    if SKIP_PARTS.intersection(rel.parts):
        return True
    return rel.name.startswith("test_") or rel.name == "conftest.py"


@cache
def _parse(path: Path, mtime_ns: int) -> tuple[ast.Module, list[str]]:
    source = path.read_text()
    return ast.parse(source, filename=str(path)), source.splitlines()


def iter_sources(roots: Iterable[str], root: Path = ROOT) -> Iterator[tuple[str, ast.Module, list[str]]]:
    """(caminho relativo POSIX, árvore, linhas) de cada ``.py`` de runtime sob ``roots``.

    A árvore é memorizada por (arquivo, mtime): as guardas rodam no mesmo processo nos
    testes e no agregado, e o parse é o custo dominante. Árvore memorizada é só leitura.
    """
    for base in roots:
        directory = root / base
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            rel = path.relative_to(root)
            if is_skipped(rel):
                continue
            tree, lines = _parse(path, path.stat().st_mtime_ns)
            yield rel.as_posix(), tree, lines


@cache
def nodes(tree: ast.Module) -> tuple[ast.AST, ...]:
    """Todos os nós da árvore, memorizados: cada guarda percorre a mesma lista."""
    return tuple(ast.walk(tree))


def kernel_of(rel: str) -> str | None:
    """Kernel dono de um arquivo: ``packages/<kernel>/...``; None fora de ``packages``."""
    parts = rel.split("/")
    if len(parts) > 1 and parts[0] == "packages" and parts[1] in KERNELS:
        return parts[1]
    return None


def bridge_target(rel: str) -> str | None:
    """Kernel ALVO de uma ponte ``.../contrib/<kernel>/...`` (C1: titularidade não muda)."""
    parts = rel.split("/")
    for i, part in enumerate(parts[:-1]):
        if part == "contrib" and parts[i + 1] in KERNELS:
            return parts[i + 1]
    return None


@cache
def import_map(tree: ast.Module) -> dict[str, str]:
    """Nome local → módulo de origem (``from a.b import C`` dá ``C → a.b``; ``import a.b`` dá ``a → a``)."""
    names: dict[str, str] = {}
    for node in nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                names[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    names[top] = top
    return names


def kernel_of_module(module: str | None) -> str | None:
    if not module:
        return None
    parts = module.split(".")
    if len(parts) > 1 and parts[0] == "shopman" and parts[1] in KERNELS:
        return parts[1]
    return None


@cache
def scopes(tree: ast.Module) -> dict[int, str]:
    """``id(nó)`` → qualname da função/classe que o contém (``<module>`` no topo)."""
    owner: dict[int, str] = {}

    def visit(node: ast.AST, qual: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = child.name if qual == "<module>" else f"{qual}.{child.name}"
                owner[id(child)] = qual
                visit(child, inner)
            else:
                owner[id(child)] = qual
                visit(child, qual)

    visit(tree, "<module>")
    return owner


def compare(findings: list[Finding], baseline: dict[str, dict]) -> tuple[list[str], list[str]]:
    counts = Counter(f.key for f in findings)
    where: dict[str, list[str]] = {}
    for f in findings:
        where.setdefault(f.key, []).append(f"{f.where}: {f.detail}")
    grew = []
    for key, count in sorted(counts.items()):
        allowed = int(baseline.get(key, {}).get("count", 0))
        if count > allowed:
            grew.append(f"{key} (baseline {allowed}, achado {count})\n      " + "\n      ".join(where[key]))
    stale = [
        f"{key} (baseline {int(entry.get('count', 1))}, achado {counts.get(key, 0)}): {entry.get('motivo', '')}"
        for key, entry in sorted(baseline.items())
        if counts.get(key, 0) < int(entry.get("count", 1))
    ]
    return grew, stale


def load_baseline(section: str, path: Path = BASELINE_PATH) -> dict[str, dict]:
    data = json.loads(path.read_text())
    entries = data.get(section, {})
    for key, entry in entries.items():
        if entry.get("classe") not in CLASSES or not entry.get("motivo"):
            raise SystemExit(f"{path.name}[{section}][{key}]: toda entrada precisa de classe ({CLASSES}) e motivo")
        if entry["classe"] == "violacao" and not entry.get("frente"):
            raise SystemExit(f"{path.name}[{section}][{key}]: violação na baseline precisa da frente que conserta")
    return entries


def run(section: str, title: str, findings: list[Finding], argv: list[str] | None = None, *, rule: str) -> int:
    """Imprime o veredito de uma guarda e devolve o código de saída."""
    args = sys.argv[1:] if argv is None else argv
    if "--strict" in args:
        if findings:
            print(f"{title} — estado bruto, sem baseline ({len(findings)}):")
            for f in findings:
                print(f"  - {f.where}: {f.detail}  [{f.key}]")
            return 1
        print(f"{title}: nenhum achado.")
        return 0

    baseline = load_baseline(section)
    grew, stale = compare(findings, baseline)
    if grew:
        print(f"{title} — NOVO fora da baseline:")
        for g in grew:
            print(f"  - {g}")
        print(f"\n{rule}")
    if stale:
        print(f"{title} — entrada OBSOLETA na baseline (apague de scripts/constitution-baseline.json[{section}]):")
        for s in stale:
            print(f"  - {s}")
    if grew or stale:
        return 1
    debt = [(k, e) for k, e in sorted(baseline.items()) if e["classe"] == "violacao"]
    excused = len(baseline) - len(debt)
    print(f"OK: {title} ({len(findings)} achado(s), todos na baseline: {len(debt)} dívida(s), {excused} exceção(ões)).")
    for key, entry in debt:
        print(f"  - dívida [{entry['frente']}] {key}: {entry['motivo']}")
    return 0
