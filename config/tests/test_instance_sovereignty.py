"""Kernel wheels remain installable without the Shopman orchestrator."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KERNELS = ("stockman", "offerman", "doorman")


@pytest.mark.parametrize("kernel", KERNELS)
def test_target_kernel_builds_and_imports_from_an_isolated_wheel(kernel, tmp_path):
    wheelhouse = tmp_path / "wheelhouse"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheelhouse),
            str(ROOT / "packages" / kernel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(wheelhouse.glob("*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        production_modules = [
            name
            for name in archive.namelist()
            if name.endswith(".py") and "/tests/" not in name
        ]
    assert production_modules
    assert all(name.startswith(f"shopman/{kernel}/") for name in production_modules)

    environment = tmp_path / "clean"
    venv.EnvBuilder(with_pip=False).create(environment)
    clean_python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(clean_python),
            "install",
            "--no-deps",
            "--ignore-installed",
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=clean_environment,
    )
    probe = (
        "import importlib.util; "
        f"import shopman.{kernel}; "
        "assert importlib.util.find_spec('shopman.shop') is None"
    )
    subprocess.run(
        [str(clean_python), "-I", "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        env=clean_environment,
    )


@pytest.mark.parametrize("kernel", KERNELS)
def test_target_kernel_keeps_orchestrator_out_and_cross_kernel_bridges_lazy(kernel):
    package_root = ROOT / "packages" / kernel / "shopman" / kernel
    violations = []
    for path in package_root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if not module.startswith("shopman."):
                    continue
                owner = module.split(".", 2)[1]
                if owner == "shop":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{module}")
                    continue
                if owner in {kernel, "refs", "utils"}:
                    continue
                is_named_bridge = bool({"adapters", "contrib"} & set(path.parts))
                is_lazy = node not in tree.body
                if not (is_named_bridge and is_lazy):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{module}")
    assert violations == []
