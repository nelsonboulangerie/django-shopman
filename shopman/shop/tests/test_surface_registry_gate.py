"""Trava do registro de superfícies — ela grita, e grita com o nome do arquivo.

`scripts/check_surface_registry.py` confere cada lugar que enumera superfícies
contra `surfaces/registry.json`. Guard que passa sempre não prova nada, então
estes testes quebram uma cópia do repositório de propósito e cobram que a
mensagem aponte o arquivo e o item que faltam. O caso que motivou tudo — uma
superfície que existe no disco e em nenhum outro lugar — é o primeiro.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_surface_registry.py"

_spec = importlib.util.spec_from_file_location("check_surface_registry", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard  # o @dataclass do script procura o próprio módulo
_spec.loader.exec_module(guard)

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
    "CLAUDE.md",
    "README.md",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, tmp_path / rel)
    for app in (REPO_ROOT / "surfaces").glob("*-nuxt"):
        (tmp_path / "surfaces" / app.name).mkdir(parents=True)
        for name in ("package.json", "nuxt.config.ts"):
            shutil.copy(app / name, tmp_path / "surfaces" / app.name / name)
    return tmp_path


def edit(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    source = path.read_text(encoding="utf-8")
    assert old in source, f"{rel} mudou; o teste precisa de outra âncora"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def test_the_real_repository_agrees_with_the_registry():
    assert guard.run(REPO_ROOT) == []


def test_the_copy_used_by_these_tests_is_faithful(repo: Path):
    assert guard.run(repo) == []


def test_a_surface_that_exists_only_on_disk_is_reported(repo: Path):
    (repo / "surfaces" / "loyalty-nuxt").mkdir()
    assert guard.run(repo) == ["surfaces/: o diretório loyalty-nuxt não está em surfaces/registry.json"]


def test_a_surface_missing_from_dependabot_names_the_file(repo: Path):
    """O caso do `purchase-nuxt`: testado no gate, esquecido na cadência."""
    edit(repo, ".github/dependabot.yml", "      - /surfaces/purchase-nuxt\n", "")
    assert guard.run(repo) == [".github/dependabot.yml: falta o diretório npm purchase-nuxt"]


def test_a_dev_port_missing_from_csrf_origins_names_the_host(repo: Path):
    """O caso do B.I. e do Marketing até 24/09/2026."""
    edit(repo, "config/settings.py", '        "http://localhost:3007",\n', "")
    assert guard.run(repo) == [
        "config/settings.py (CSRF_TRUSTED_ORIGINS, localhost): falta a porta de dev 3007",
    ]


def test_a_new_registry_entry_lists_every_place_that_still_lacks_it(repo: Path):
    registry = json.loads((repo / "surfaces/registry.json").read_text())
    registry["surfaces"]["loyalty"] = {
        "dir": "loyalty-nuxt",
        "kind": "operator",
        "dev_port": 3009,
        "service": "operator-office",
        "subdomain": "fidelidade",
        "base_url_env": "SHOPMAN_LOYALTY_BASE_URL",
        "hub_tile": "loyalty",
    }
    (repo / "surfaces/registry.json").write_text(json.dumps(registry))

    reported = {error.split(":", 1)[0].split(" (")[0] for error in guard.run(repo)}
    assert reported == {
        "surfaces/",
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
        "CLAUDE.md",
        "README.md",
    }


def test_hub_dev_url_on_the_wrong_port_is_reported(repo: Path):
    edit(
        repo, "shopman/backstage/projections/hub.py", '"bi": "http://127.0.0.1:3007/"', '"bi": "http://127.0.0.1:3070/"'
    )
    errors = guard.run(repo)
    assert "shopman/backstage/projections/hub.py (DEV_SURFACE_URLS): falta o tile ('bi', 3007)" in errors


def test_operator_host_pointing_to_the_wrong_group_is_reported(repo: Path):
    edit(
        repo,
        ".do/app.alpha-subdomains.yaml",
        "marketing=mkt.boulangerie.com.br,",
        "",
    )
    errors = guard.run(repo)
    assert errors == [
        ".do/app.alpha-subdomains.yaml (OPERATOR_HOSTS de operator-office): "
        "falta o par ('marketing', 'mkt.boulangerie.com.br')",
    ]


def test_registry_rejects_unknown_fields_and_duplicated_ports(repo: Path):
    registry = json.loads((repo / "surfaces/registry.json").read_text())
    registry["surfaces"]["bi"]["dev_port"] = 3006
    registry["surfaces"]["bi"]["port"] = 3007
    (repo / "surfaces/registry.json").write_text(json.dumps(registry))
    errors = guard.run(repo)
    assert "surfaces/registry.json: bi com campo desconhecido ['port']" in errors
    assert "surfaces/registry.json: dev_port 3006 repetido" in errors


def test_main_exits_nonzero_and_prints_the_file(repo: Path, capsys):
    edit(repo, "Makefile", " bi-nuxt", "")
    assert guard.main(["--root", str(repo)]) == 1
    assert "Makefile (SURFACES): falta o app bi-nuxt" in capsys.readouterr().err
