"""WP-RELEASE-01 R0: inventário de release coerente e classe de risco do diff.

Quebra se `surfaces/registry.json`, `surfaces/operator-router/groups.json` e a
tabela do `scripts/deploy_components.py` deixarem de concordar sobre quem serve
cada superfície.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location("release_inventory_under_test", ROOT / "scripts" / "release_inventory.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass procura o módulo em sys.modules
    spec.loader.exec_module(module)
    return module


RI = _load()


def test_inventory_is_exactly_the_four_release_components():
    inv = RI.inventory()
    assert tuple(inv) == ("web", "storefront-nuxt", "operator-floor", "operator-office")
    assert inv["operator-floor"] == ["pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt", "hub-nuxt"]
    assert inv["operator-office"] == ["marketing-nuxt", "bi-nuxt", "purchase-nuxt"]


def test_registry_groups_and_deploy_agree():
    assert RI.inventory_errors() == []


@pytest.fixture
def repo_copy(tmp_path):
    for rel in ("surfaces/registry.json", "surfaces/operator-router/groups.json"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, target)
    return tmp_path


def test_divergence_between_registry_and_groups_is_reported(repo_copy):
    registry_path = repo_copy / "surfaces" / "registry.json"
    registry = json.loads(registry_path.read_text())
    registry["surfaces"]["bi"]["service"] = "operator-floor"
    registry_path.write_text(json.dumps(registry))

    errors = RI.inventory_errors(repo_copy)

    assert any("bi" in e and "operator-office" in e for e in errors), errors


def test_surface_missing_from_groups_is_reported(repo_copy):
    groups_path = repo_copy / "surfaces" / "operator-router" / "groups.json"
    groups = json.loads(groups_path.read_text())
    groups["operator-office"]["apps"] = [a for a in groups["operator-office"]["apps"] if a["id"] != "purchase"]
    groups_path.write_text(json.dumps(groups))

    errors = RI.inventory_errors(repo_copy)

    assert any("purchase" in e and "nenhum componente" in e for e in errors), errors


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("packages/orderman/shopman/orderman/migrations/0003_x.py", "schema"),
        (".do/app.alpha-subdomains.yaml", "config"),
        (".github/workflows/deploy-images.yml", "config"),
        ("surfaces/operator-kit/server/utils/releaseIdentity.ts", "kit_router"),
        ("surfaces/operator-router/src/router.mjs", "kit_router"),
        ("shopman/shop/handlers/fiscal.py", "mutation"),
        ("shopman/shop/adapters/payment_efi.py", "mutation"),
        ("surfaces/pos-nuxt/package-lock.json", "dependency"),
        ("surfaces/Dockerfile.surface", "dependency"),
        ("shopman/backstage/projections/kds.py", "api"),
        ("shopman/storefront/api/cart.py", "api"),
        ("surfaces/kds-nuxt/app/pages/index.vue", "ui"),
        ("docs/reference/release-contract.md", "none"),
        ("shopman/shop/tests/test_x.py", "none"),
    ],
)
def test_classify(path, expected):
    assert RI.classify(path) == expected


def test_risk_report_names_components_and_highest_class():
    report = RI.risk_report(
        ["surfaces/kds-nuxt/app/pages/index.vue", "shopman/shop/handlers/fiscal.py", "docs/x.md"]
    )

    assert report["components"] == ["web", "operator-floor"]
    assert report["highest"] == "mutation"
    markdown = RI.render_risk_markdown(report)
    assert "`operator-floor`" in markdown
    assert "Mutation/efeito externo" in markdown
