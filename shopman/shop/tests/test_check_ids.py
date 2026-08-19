"""Os ids dos deploy checks são únicos e documentados.

Achado da série de auditorias: `SHOPMAN_W008`, `W009` e `W010` estavam cada um
em DOIS checks distintos. Id compartilhado quebra tudo que o id serve para
fazer — grep de runbook, silenciamento por id, `assert [m.id for m in ...]` num
teste que passa a valer para o check errado, e a conversa de plantão ("subiu
W010" — qual dos dois?).

O teste é estático (lê a árvore do módulo) de propósito: rodar os checks exigiria
montar o estado de banco e settings de cada um, e o que se quer travar aqui é a
declaração, não o disparo.
"""

from __future__ import annotations

import ast
import pathlib
import re

CHECKS_PATH = pathlib.Path(__file__).resolve().parents[1] / "checks.py"
ID_RE = re.compile(r"SHOPMAN_[EW]\d+")


def _module() -> ast.Module:
    return ast.parse(CHECKS_PATH.read_text(encoding="utf-8"))


def _functions() -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(_module())
        if isinstance(node, ast.FunctionDef)
    }


def _is_registered(node: ast.FunctionDef) -> bool:
    """O check é o que está sob ``@register(...)`` — helpers privados não contam."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "register":
            return True
    return False


def _own_ids(node: ast.FunctionDef) -> set[str]:
    ids = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.keyword) and inner.arg == "id":
            value = inner.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if ID_RE.fullmatch(value.value):
                    ids.add(value.value)
    return ids


def _called_names(node: ast.FunctionDef) -> set[str]:
    return {
        inner.func.id
        for inner in ast.walk(node)
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
    }


def _ids_by_function() -> dict[str, set[str]]:
    """{check registrado: ids que ele emite}, incluindo os dos helpers que chama.

    Agrupar pelo check REGISTRADO, e não por função, é o que separa colisão de
    fatoração: ``SHOPMAN_E009`` sai de dois helpers privados
    (``_check_efi_payment_credentials`` / ``_check_stripe_payment_credentials``),
    mas é um id só, de um check só ("adapter de pagamento real sem credencial") —
    isso é código bem fatorado, não id compartilhado.
    """
    functions = _functions()

    def collect(name: str, seen: set[str]) -> set[str]:
        if name in seen or name not in functions:
            return set()
        seen.add(name)
        node = functions[name]
        ids = set(_own_ids(node))
        for called in _called_names(node):
            ids |= collect(called, seen)
        return ids

    return {
        name: collect(name, set())
        for name, node in functions.items()
        if _is_registered(node)
    }


def test_no_check_id_is_shared_by_two_checks():
    owners: dict[str, set[str]] = {}
    for func, ids in _ids_by_function().items():
        for check_id in ids:
            owners.setdefault(check_id, set()).add(func)

    shared = {cid: sorted(funcs) for cid, funcs in owners.items() if len(funcs) > 1}
    assert not shared, f"ids em mais de um check: {shared}"


def test_every_declared_id_is_listed_in_the_module_docstring():
    # O cabeçalho de checks.py é o índice que o plantão lê. Id que não está lá é
    # id que ninguém encontra às 6h da manhã.
    docstring = ast.get_docstring(_module()) or ""
    declared = {cid for ids in _ids_by_function().values() for cid in ids}

    undocumented = sorted(cid for cid in declared if cid not in docstring)
    assert not undocumented, f"ids sem linha no cabeçalho: {undocumented}"


def test_docstring_does_not_list_ids_that_no_check_declares():
    docstring = ast.get_docstring(_module()) or ""
    declared = {cid for ids in _ids_by_function().values() for cid in ids}

    orphans = sorted(set(ID_RE.findall(docstring)) - declared)
    assert not orphans, f"ids documentados que nenhum check emite: {orphans}"
