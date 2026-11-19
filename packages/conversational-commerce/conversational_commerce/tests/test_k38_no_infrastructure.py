"""K38: o pacote importa sem Django, sem SDK e sem nada fora da biblioteca padrão.

Duas provas, porque cada uma pega o que a outra deixa passar:

1. **Leitura (AST).** Varre todo ``.py`` do pacote e reprova ``import``,
   ``from ... import``, ``importlib.import_module("...")`` e ``__import__("...")``
   de módulo que não seja da biblioteca padrão nem do próprio pacote. Import
   dinâmico com nome não literal também reprova: o que não se lê não se confere.
   Pega o import escondido num ramo que nenhum teste executa.
2. **Execução.** Importa, num processo novo, todo módulo do pacote e reprova
   qualquer módulo de fora da biblioteca padrão que tenha entrado em
   ``sys.modules``. Pega o que entra por um import da própria biblioteca
   padrão que carrega plugin de terceiro.

Exceção única e declarada: ``tests`` e ``testing`` são o extra ``[testing]``
do ``pyproject.toml`` e podem importar ``pytest``. Nada mais.

O wheel limpo (``scripts/wheel_suite.py conversational-commerce``) fecha a
terceira prova: o pacote instala e passa esta suíte num venv sem Django.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "conversational_commerce"
PACKAGE_DIR = Path(__file__).resolve().parents[1]

# Subárvores que SÃO o extra [testing] e o que ele traz. Mudar aqui é mudar o
# pyproject junto, e o contrário também.
TESTING_SUBTREES = frozenset({"tests", "testing"})
TESTING_EXTRA = frozenset({"pytest"})

NON_LITERAL = "<nome não literal>"


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    module: str


def _allowed(top: str, extra: frozenset[str], package: str) -> bool:
    return top == package or top in sys.stdlib_module_names or top in extra


def _dynamic_import_target(node: ast.Call) -> str | None:
    """Nome importado por ``importlib.import_module(...)`` ou ``__import__(...)``.

    Devolve ``None`` se a chamada não for import dinâmico e ``NON_LITERAL`` se
    o nome não for uma string escrita no código.
    """
    func = node.func
    is_dunder = isinstance(func, ast.Name) and func.id == "__import__"
    is_import_module = (
        isinstance(func, ast.Attribute) and func.attr == "import_module"
    ) or (isinstance(func, ast.Name) and func.id == "import_module")
    if not (is_dunder or is_import_module):
        return None
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        name = node.args[0].value
        # import_module(".x", package=...) é relativo: é do próprio pacote.
        return PACKAGE if name.startswith(".") else name
    return NON_LITERAL


def infrastructure_imports(package_dir: Path, package: str = PACKAGE) -> tuple[list[Violation], list[str]]:
    """Varre ``package_dir`` e devolve (violações, arquivos lidos), caminhos relativos."""
    violations: list[Violation] = []
    scanned: list[str] = []
    for path in sorted(package_dir.rglob("*.py")):
        relative = path.relative_to(package_dir)
        if "__pycache__" in relative.parts:
            continue
        rel = relative.as_posix()
        scanned.append(rel)
        extra = TESTING_EXTRA if relative.parts[0] in TESTING_SUBTREES else frozenset()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            violations.append(Violation(rel, error.lineno or 0, "<não compila>"))
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    names = [node.module]
            elif isinstance(node, ast.Call):
                target = _dynamic_import_target(node)
                if target == NON_LITERAL:
                    violations.append(Violation(rel, node.lineno, NON_LITERAL))
                elif target is not None:
                    names = [target]
            for name in names:
                top = name.split(".")[0]
                if not _allowed(top, extra, package):
                    violations.append(Violation(rel, node.lineno, name))
    return violations, scanned


def test_k38_package_imports_only_the_standard_library():
    violations, scanned = infrastructure_imports(PACKAGE_DIR)

    assert "__init__.py" in scanned, f"a varredura não leu o pacote: {scanned}"
    assert "tests/test_k38_no_infrastructure.py" in scanned
    assert violations == [], "import fora da biblioteca padrão:\n" + "\n".join(
        f"  {v.path}:{v.line} importa {v.module}" for v in violations
    )


def test_k38_reproves_a_planted_infrastructure_import(tmp_path):
    """O teste do teste: a cópia do pacote com um módulo plantado reprova, e só ele."""
    copy = tmp_path / PACKAGE
    shutil.copytree(PACKAGE_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "planted.py").write_text(
        textwrap.dedent(
            """\
            from __future__ import annotations

            import importlib
            import json

            import django
            from django.db import models
            import pytest

            from . import tests
            from conversational_commerce import __version__

            anthropic = importlib.import_module("anthropic")
            own = importlib.import_module(".tests", package="conversational_commerce")
            whatever = __import__(json.dumps("x"))
            """
        ),
        encoding="utf-8",
    )
    (copy / "tests" / "test_planted.py").write_text(
        "import pytest\nimport requests\n",
        encoding="utf-8",
    )

    violations, scanned = infrastructure_imports(copy)

    assert "planted.py" in scanned
    assert sorted((v.path, v.module) for v in violations) == [
        ("planted.py", NON_LITERAL),
        ("planted.py", "anthropic"),
        ("planted.py", "django"),
        ("planted.py", "django.db"),
        ("planted.py", "pytest"),
        ("tests/test_planted.py", "requests"),
    ]


def test_k38_reproves_a_module_that_does_not_compile(tmp_path):
    copy = tmp_path / PACKAGE
    copy.mkdir()
    (copy / "__init__.py").write_text("import (\n", encoding="utf-8")

    violations, _ = infrastructure_imports(copy)

    assert [v.module for v in violations] == ["<não compila>"]


def _runtime_modules() -> list[str]:
    modules = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        relative = path.relative_to(PACKAGE_DIR)
        if relative.parts[0] in TESTING_SUBTREES or "__pycache__" in relative.parts:
            continue
        parts = [PACKAGE, *relative.with_suffix("").parts]
        if parts[-1] == "__init__":
            parts.pop()
        modules.append(".".join(parts))
    return modules


def test_k38_importing_every_module_loads_only_the_standard_library(tmp_path):
    modules = _runtime_modules()
    assert PACKAGE in modules
    probe = textwrap.dedent(
        f"""\
        import importlib, json, sys
        before = set(sys.modules)
        for name in {modules!r}:
            importlib.import_module(name)
        loaded = sorted(set(sys.modules) - before)
        foreign = sorted({{
            name.split(".")[0] for name in loaded
            if name.split(".")[0] not in sys.stdlib_module_names and name.split(".")[0] != {PACKAGE!r}
        }})
        print(json.dumps({{"loaded": loaded, "foreign": foreign}}))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PACKAGE_DIR.parent), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert PACKAGE in report["loaded"]
    assert report["foreign"] == [], f"importar o pacote carregou: {report['foreign']}"
