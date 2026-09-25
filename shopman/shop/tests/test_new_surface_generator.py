"""`make new-surface`: o app nasce registrado em TODO lugar que a trava confere.

O teste que importa é o primeiro: gerar uma superfície numa cópia do repositório e
rodar `scripts/check_surface_registry.py` nela. Se um lugar novo entrar na trava e o
gerador não souber escrever nele, é aqui que reprova — antes de alguém criar um app
de verdade e descobrir na CI.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("check_surface_registry")
generator = _load("new_surface")

FILES = (
    "surfaces/registry.json",
    ".github/dependabot.yml",
    ".github/workflows/surfaces-gate.yml",
    "Makefile",
    "surfaces/operator-router/groups.json",
    "surfaces/Dockerfile.operator-group",
    ".do/app.subdomains.yaml",
    ".do/app.alpha-subdomains.yaml",
    "config/settings.py",
    "shopman/backstage/projections/hub.py",
    "surfaces/operator-kit/app-identity.json",
    "tools/pwa-gate/check.mjs",
    "CLAUDE.md",
    "README.md",
)
MOLD = (
    "package.json",
    "package-lock.json",
    ".gitignore",
    "tsconfig.json",
    "vitest.config.ts",
    "app/assets/css/tailwind.css",
    "public/robots.txt",
)
ARGS = {
    "name": "loyalty",
    "label": "Fidelidade",
    "subdomain": "fidelidade",
    "group": "operator-office",
    "perm": "backstage.view_loyalty",
    "color": "#5b6b2e",
    "symbol": "lucide:heart-handshake",
    "article": "a",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, tmp_path / rel)
    for app in (REPO_ROOT / "surfaces").glob("*-nuxt"):
        for name in ("package.json", "nuxt.config.ts") + (MOLD if app.name == generator.MOLD_DEPENDENCIES else ()):
            (tmp_path / "surfaces" / app.name / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(app / name, tmp_path / "surfaces" / app.name / name)
    return tmp_path


def test_a_generated_surface_passes_the_registry_gate(repo: Path):
    assert guard.run(repo) == []
    generator.create(repo, **ARGS)
    assert guard.run(repo) == []


def test_the_generated_app_extends_the_kit_and_locks_on_its_permission(repo: Path):
    generator.create(repo, **ARGS)
    app = repo / "surfaces" / "loyalty-nuxt"
    assert 'extends: ["../operator-kit"]' in (app / "nuxt.config.ts").read_text()
    assert 'const OPERATOR_PERM = "backstage.view_loyalty"' in (app / "app" / "app.vue").read_text()
    assert (app / "tests" / "shell.test.ts").is_file()
    package = json.loads((app / "package.json").read_text())
    assert package["name"] == "loyalty-nuxt"
    assert package["scripts"]["dev"] == "nuxt dev --host 127.0.0.1 --port 3009"


def test_the_lock_is_the_mold_lock_so_versions_start_aligned(repo: Path):
    generator.create(repo, **ARGS)
    mold = json.loads((repo / "surfaces" / generator.MOLD_DEPENDENCIES / "package-lock.json").read_text())
    lock = json.loads((repo / "surfaces" / "loyalty-nuxt" / "package-lock.json").read_text())
    mold["name"] = mold["packages"][""]["name"] = "loyalty-nuxt"
    assert lock == mold


def test_the_tile_is_fail_closed_until_someone_wires_the_permission(repo: Path):
    generator.create(repo, **ARGS)
    hub = (repo / "shopman/backstage/projections/hub.py").read_text()
    assert (
        '_AppSpec("loyalty", "Fidelidade", "Fidelidade da operação", "heart-handshake", "launch", is_superuser)' in hub
    )


def test_dry_run_touches_nothing(repo: Path):
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    touched = generator.create(repo, **ARGS, dry_run=True).touched
    assert "surfaces/registry.json" in touched
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"name": "pos"}, "pos já existe"),
        ({"name": "Loyalty"}, "minúsculas"),
        ({"subdomain": "pdv"}, "já usado"),
        ({"group": "operator-everything"}, "use um de"),
        ({"perm": "view_loyalty"}, "<app_label>.<codename>"),
        ({"color": "verde"}, "#RRGGBB"),
        ({"symbol": "heart"}, "lucide:<nome>"),
    ],
)
def test_bad_arguments_are_refused_before_writing(repo: Path, override: dict, message: str):
    before = (repo / "surfaces/registry.json").read_text()
    with pytest.raises(generator.SurfaceError, match=message):
        generator.create(repo, **{**ARGS, **override})
    assert (repo / "surfaces/registry.json").read_text() == before


def test_json_writers_preserve_the_hand_formatting():
    """Reescrever o arquivo inteiro não pode virar diff de formatação."""
    for rel in ("surfaces/registry.json", "surfaces/operator-kit/app-identity.json"):
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert generator.dump_json(json.loads(source)) == source, rel
    groups = (REPO_ROOT / "surfaces/operator-router/groups.json").read_text(encoding="utf-8")
    assert generator.dump_groups(json.loads(groups)) == groups
