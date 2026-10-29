from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_tenant_config", ROOT / "scripts/check_tenant_config.py")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def _counts(source: str, rel: str = "shopman/shop/services/example.py") -> dict[str, int]:
    return gate.count_source(source, rel).as_dict()


def test_repository_matches_versioned_baseline():
    grew, _shrank = gate.compare(gate.measure(), gate.load_baseline())
    assert grew == []


def test_counts_tenant_settings_reads_and_respects_import_alias():
    source = (
        "from django.conf import settings as dj\n"
        "a = dj.SHOPMAN_EFI\n"
        "b = getattr(dj, 'STRIPE_KEY', '')\n"
        "c = hasattr(dj, 'IFOOD_CLIENT')\n"
        "d = dj.DEBUG\n"
        "e = getattr(dj, 'TIME_ZONE')\n"
    )
    assert _counts(source) == {"settings": 3}


def test_dynamic_getattr_on_settings_counts():
    source = "from django.conf import settings\nname = 'X'\nv = getattr(settings, f'SHOPMAN_{name}_BASE_URL')\n"
    assert _counts(source) == {"settings": 1}


def test_name_settings_not_imported_from_django_is_ignored():
    source = "settings = object()\nv = settings.SHOPMAN_EFI\n"
    assert _counts(source) == {}


def test_counts_every_runtime_env_read():
    source = (
        "import os\n"
        "from os import environ\n"
        "a = os.environ.get('ANYTHING')\n"
        "b = os.getenv('REDIS_URL')\n"
        "c = os.environ['X']\n"
        "d = environ.get('Y')\n"
    )
    assert _counts(source) == {"env": 4}


def test_settings_module_counts_only_tenant_env_names():
    source = (
        "import os\n"
        "def _env_bool(name, default=False):\n"
        "    return os.environ.get(name) == '1'\n"
        "DATABASE_URL = os.environ.get('DATABASE_URL')\n"
        "EFI = {'client_id': os.environ.get('EFI_CLIENT_ID'), 'again': os.getenv('EFI_CLIENT_ID')}\n"
        "STRIPE = os.environ['STRIPE_SECRET_KEY']\n"
        "MOCK = _env_bool('SHOPMAN_MOCK_PIX')\n"
    )
    assert _counts(source, "config/settings.py") == {"settings_env": 3}


def test_skips_tests_migrations_and_test_modules(tmp_path):
    for rel in (
        "shopman/shop/tests/test_x.py",
        "shopman/shop/migrations/0001_initial.py",
        "packages/payman/shopman/payman/test_helper.py",
        "shopman/conftest.py",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import os\nos.getenv('X')\n", encoding="utf-8")
    kept = tmp_path / "shopman/shop/services/real.py"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("import os\nos.getenv('X')\n", encoding="utf-8")
    assert gate.measure(tmp_path) == {"shopman/shop/services/real.py": {"env": 1}}


def test_growth_fails_and_shrink_is_reported():
    baseline = {"a.py": {"settings": 2}, "b.py": {"env": 1}}
    current = {"a.py": {"settings": 3}, "c.py": {"settings_env": 1}}
    grew, shrank = gate.compare(current, baseline)
    assert grew == ["a.py: settings 2 -> 3", "c.py: settings_env 0 -> 1"]
    assert shrank == ["b.py: env 1 -> 0"]


def test_main_fails_on_growth_and_says_where_config_lives(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    gate.write_baseline({}, baseline)
    monkeypatch.setattr(gate, "BASELINE_PATH", baseline)
    monkeypatch.setattr(gate, "measure", lambda: {"shopman/shop/x.py": {"settings": 1}})
    assert gate.main([]) == 1
    err = capsys.readouterr().err
    assert "shopman/shop/x.py: settings 0 -> 1" in err
    assert "config/instances" in err and "`Shop`" in err and "ADR-042" in err


def test_main_passes_on_shrink_and_suggests_update(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    gate.write_baseline({"shopman/shop/x.py": {"env": 2}}, baseline)
    monkeypatch.setattr(gate, "BASELINE_PATH", baseline)
    monkeypatch.setattr(gate, "measure", lambda: {"shopman/shop/x.py": {"env": 1}})
    assert gate.main([]) == 0
    assert "--update" in capsys.readouterr().out
