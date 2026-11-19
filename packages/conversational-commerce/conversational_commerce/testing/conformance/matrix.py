"""A matriz teste × invariante, gerada dos decoradores ``@conformance`` (plano, decisão 9).

    python -m conversational_commerce.testing.matrix            # lista marcados e faltantes
    python -m conversational_commerce.testing.matrix --check    # falha se faltar K ou escopo divergir
    python -m conversational_commerce.testing.matrix --path <dir>   # inclui os testes de um adaptador

Lê os testes pelo AST, sem importá-los. Nenhuma lista central para editar: o
teste se declara, e a matriz sai dele. Desde o F11 o ``--check`` roda dentro da
suíte (``tests/test_d1_exit.py``), com os 40 marcados.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from .catalog import K_BY_ID, K_TESTS, SCOPES

PACKAGE_TESTS = Path(__file__).resolve().parents[2] / "tests"


@dataclass(frozen=True, slots=True)
class Marked:
    test_id: str
    scope: str
    invariants: tuple[str, ...]
    where: str


@dataclass(frozen=True, slots=True)
class Problem:
    where: str
    message: str


def _literal(node: ast.AST):
    return ast.literal_eval(node)


def _is_conformance(decorator: ast.AST) -> ast.Call | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return decorator if name == "conformance" else None


def scan(paths: list[Path]) -> tuple[list[Marked], list[Problem]]:
    marked: list[Marked] = []
    problems: list[Problem] = []
    for root in paths:
        files = [root] if root.is_file() else sorted(root.rglob("test_*.py"))
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for decorator in node.decorator_list:
                    call = _is_conformance(decorator)
                    if call is None:
                        continue
                    where = f"{path.name}::{node.name}"
                    try:
                        test_id = _literal(call.args[0])
                        keywords = {kw.arg: _literal(kw.value) for kw in call.keywords}
                    except (ValueError, IndexError):
                        problems.append(Problem(where, "@conformance com argumento não literal"))
                        continue
                    scope = keywords.get("scope")
                    invariants = tuple(keywords.get("invariants", ()))
                    if test_id not in K_BY_ID:
                        problems.append(Problem(where, f"K desconhecido: {test_id}"))
                        continue
                    if scope not in SCOPES:
                        problems.append(Problem(where, f"{test_id} sem escopo válido: {scope!r}"))
                        continue
                    marked.append(Marked(test_id, scope, invariants, where))
    return marked, problems


def report(paths: list[Path]) -> tuple[str, list[Problem], list[str]]:
    marked, problems = scan(paths)
    by_id: dict[str, list[Marked]] = {}
    for mark in marked:
        by_id.setdefault(mark.test_id, []).append(mark)
    lines = ["| K | Dono | Escopo exigido | Marcado em | Escopo declarado |", "|---|---|---|---|---|"]
    missing = []
    for test in K_TESTS:
        marks = by_id.get(test.id, [])
        if not marks:
            missing.append(test.id)
            lines.append(f"| {test.id} | {test.owner} | {test.scope} | falta | |")
            continue
        for mark in marks:
            lines.append(f"| {test.id} | {test.owner} | {test.scope} | {mark.where} | {mark.scope} |")
            if mark.scope != test.scope:
                problems.append(Problem(mark.where, f"{test.id} declara {mark.scope}, o plano exige {test.scope}"))
    lines.append("")
    lines.append(f"Marcados: {len(K_TESTS) - len(missing)} de {len(K_TESTS)}. Faltam: {', '.join(missing) or 'nenhum'}.")
    return "\n".join(lines), problems, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Matriz de conformidade K01 a K40")
    parser.add_argument("--check", action="store_true", help="falha se faltar K ou se um escopo divergir")
    parser.add_argument("--path", action="append", default=[], help="diretório de testes a mais (adaptador)")
    args = parser.parse_args(argv)
    paths = [PACKAGE_TESTS, *(Path(path) for path in args.path)]
    text, problems, missing = report(paths)
    print(text)
    for problem in problems:
        print(f"problema: {problem.where}: {problem.message}", file=sys.stderr)
    if problems:
        return 1
    if args.check and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
