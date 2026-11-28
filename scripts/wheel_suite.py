#!/usr/bin/env python3
"""O wheel de um pacote instala limpo e passa a própria suíte (critério global 1).

Uso:
    python scripts/wheel_suite.py --all             # todo pacote fora de PENDING
    python scripts/wheel_suite.py <pacote> [...]    # pacotes nomeados, PENDING inclusive

Para cada pacote de ``packages/``:

1. constrói o wheel de TODOS os pacotes (``pip wheel --no-deps``), para que as
   dependências ``shopman-*`` declaradas no ``pyproject`` resolvam pelo wheel
   irmão, nunca pela árvore de código;
2. cria um venv limpo e instala ``<distribuição>[<extra de teste>]`` desse
   diretório de wheels mais o PyPI. Só entra o que o pacote DECLARA;
3. roda a suíte do pacote importada do site-packages do venv
   (``pytest --pyargs <módulo>.tests``), num diretório de trabalho que
   só tem os arquivos de apoio da raiz do pacote (settings, urls, conftest).
   O código-fonte do repositório não está no ``sys.path``: se a suíte precisa
   de algo que o pacote não declara, ela quebra aqui.

Dois tipos de pacote, lidos do ``pyproject`` de cada um (``_profile``):

- **App Django da suíte** (``shopman.<pacote>``, ``DJANGO_SETTINGS_MODULE`` no
  ``[tool.pytest.ini_options]``): extra ``[dev]``, mais ``pytest`` e
  ``pytest-django``. É o caso dos 13 irmãos, e nada nele mudou.
- **Pacote puro** (fora do namespace ``shopman.``, sem
  ``DJANGO_SETTINGS_MODULE``; hoje só o ``conversational-commerce``, ADR-049):
  extra ``[testing]``, mais ``pytest`` e nada de ``pytest-django``. Aqui o
  script também exige que o Django NÃO esteja instalado no venv: o pacote
  promete não depender dele, e é este venv que prova.

O ``pythonpath`` do ``[tool.pytest.ini_options]`` do pacote é ignorado de
propósito: é ele que, na árvore, deixa a suíte enxergar pacote irmão sem
declarar a dependência.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
TEST_DEPENDENCIES = ("pytest",)
DJANGO_TEST_DEPENDENCIES = ("pytest-django",)
# Extra que traz a suíte: ``dev`` nos apps Django da suíte, ``testing`` no
# pacote puro. Pacote sem nenhum dos dois não entra no gate (erro, não pulo).
TEST_EXTRAS = ("dev", "testing")

# Pacote cujo wheel instala, mas cuja suíte precisa de algo que o pacote não
# declara, com a causa escrita. A dívida medida em 19/10/2026 (laudo de
# soberania, critério global 1) zerou: os 13 pacotes estão no gate. Entrada
# nova aqui é regressão declarada, nunca atalho; pacote fora daqui que quebra
# reprova o job.
PENDING: dict[str, str] = {}


def _run(cmd: list[str], **kwargs) -> None:
    print("$", " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"valor de ini não suportado: {value!r}")


def _pytest_config(package: str) -> dict:
    pyproject = tomllib.loads((PACKAGES_ROOT / package / "pyproject.toml").read_text())
    config = dict(pyproject["tool"]["pytest"]["ini_options"])
    # A árvore não entra: só o diretório de trabalho (arquivos de apoio).
    config["pythonpath"] = ["."]
    config.pop("testpaths", None)
    return config


def _distribution(package: str) -> str:
    pyproject = tomllib.loads((PACKAGES_ROOT / package / "pyproject.toml").read_text())
    return pyproject["project"]["name"]


def _profile(package: str) -> tuple[str, str, bool]:
    """(módulo importável, extra de teste, é app Django?) do pacote.

    Falha alto quando o pyproject não cabe em nenhum dos dois tipos: um pacote
    mal declarado não pode entrar no gate por um caminho mais frouxo.
    """
    pyproject = tomllib.loads((PACKAGES_ROOT / package / "pyproject.toml").read_text())
    includes = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    if len(includes) != 1 or not includes[0].endswith("*"):
        raise SystemExit(f"{package}: packages.find.include deve ter um padrão só, '<módulo>*': {includes}")
    module = includes[0].removesuffix("*")
    is_django = "DJANGO_SETTINGS_MODULE" in pyproject["tool"]["pytest"]["ini_options"]
    if module.startswith("shopman.") or is_django:
        # App Django da suíte: o contrato de sempre, sem afrouxar nada.
        if module != f"shopman.{package}" or not is_django:
            raise SystemExit(
                f"{package}: app da suíte precisa ser 'shopman.{package}' com DJANGO_SETTINGS_MODULE "
                f"(achei módulo {module!r}, Django={is_django})"
            )
    elif "." in module:
        raise SystemExit(f"{package}: pacote puro precisa de módulo de topo, achei {module!r}")
    extras = pyproject["project"].get("optional-dependencies", {})
    extra = next((name for name in TEST_EXTRAS if name in extras), None)
    if extra is None:
        raise SystemExit(f"{package}: sem extra de teste ({' ou '.join(TEST_EXTRAS)}) no pyproject")
    return module, extra, is_django


def build_wheels(workdir: Path, dist_dir: Path) -> None:
    """Constrói fora da árvore: o setuptools deixa ``build/`` e ``*.egg-info`` onde roda."""
    for package_dir in sorted(p for p in PACKAGES_ROOT.iterdir() if (p / "pyproject.toml").exists()):
        source = workdir / "src" / package_dir.name
        shutil.copytree(
            package_dir, source,
            ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__", ".pytest_cache"),
        )
        _run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet", "-w", str(dist_dir), str(source)])


def run_package(package: str, workdir: Path, dist_dir: Path) -> int:
    module, extra, is_django = _profile(package)
    venv = workdir / f"venv-{package}"
    _run([sys.executable, "-m", "venv", str(venv)])
    python = venv / "bin" / "python"
    _run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    test_dependencies = TEST_DEPENDENCIES + (DJANGO_TEST_DEPENDENCIES if is_django else ())
    _run([
        str(python), "-m", "pip", "install", "--quiet",
        "--find-links", str(dist_dir),
        f"{_distribution(package)}[{extra}]", *test_dependencies,
    ])
    if not is_django:
        django_spec = subprocess.run(
            [str(python), "-c", "import importlib.util; print(importlib.util.find_spec('django') is not None)"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if django_spec != "False":
            print(f"ERRO: {package} é pacote puro e o venv limpo dele tem Django instalado", flush=True)
            return 1
        print(f"{package}: venv limpo sem Django", flush=True)

    rundir = workdir / f"run-{package}"
    rundir.mkdir()
    for support in sorted((PACKAGES_ROOT / package).glob("*.py")):
        shutil.copy2(support, rundir / support.name)
    lines = ["[tool.pytest.ini_options]"]
    lines += [f"{key} = {_toml_value(value)}" for key, value in _pytest_config(package).items()]
    (rundir / "pyproject.toml").write_text("\n".join(lines) + "\n")

    origin = subprocess.run(
        [str(python), "-c", f"import {module}; print({module}.__file__)"],
        cwd=rundir, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if not Path(origin).resolve().is_relative_to(venv.resolve()):
        print(f"ERRO: {module} foi importado de {origin}, fora do venv limpo", flush=True)
        return 1
    print(f"{module} importado de {origin}", flush=True)

    # A suíte é importada do site-packages, e o pytest só procura conftest.py
    # subindo a partir dela: o da raiz do pacote (fixtures autouse que limpam
    # registro, resolvedor etc.) nunca seria visto. Entra como plugin.
    root_conftest = ["-p", "conftest"] if (rundir / "conftest.py").exists() else []
    result = subprocess.run(
        [
            str(python), "-m", "pytest", "--pyargs", f"{module}.tests",
            "-q", "-p", "no:cacheprovider", *root_conftest,
        ],
        cwd=rundir,
        env={"PATH": f"{venv / 'bin'}:/usr/bin:/bin", "HOME": str(workdir)},
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packages", nargs="*", help="diretórios de packages/ (ex.: utils stockman)")
    parser.add_argument("--all", action="store_true", help="todo pacote de packages/ fora de PENDING")
    parser.add_argument("--keep", action="store_true", help="não apagar o diretório temporário")
    args = parser.parse_args()
    if args.all:
        everything = sorted(p.name for p in PACKAGES_ROOT.iterdir() if (p / "pyproject.toml").exists())
        unknown = sorted(set(PENDING) - set(everything))
        if unknown:
            parser.error(f"PENDING cita pacote que não existe: {unknown}")
        args.packages = [package for package in everything if package not in PENDING]
        for package, cause in sorted(PENDING.items()):
            print(f"pendente (fora do gate): {package}: {cause}", flush=True)
    if not args.packages:
        parser.error("nomeie pacotes ou use --all")

    workdir = Path(tempfile.mkdtemp(prefix="wheel-suite-")).resolve()
    try:
        dist_dir = workdir / "dist"
        build_wheels(workdir, dist_dir)
        failed = [package for package in args.packages if run_package(package, workdir, dist_dir) != 0]
    finally:
        if args.keep:
            print(f"diretório mantido: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    if failed:
        print("Wheel que não passa a própria suíte num venv limpo: " + ", ".join(failed))
        return 1
    print("Wheel limpo e suíte verde: " + ", ".join(args.packages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
