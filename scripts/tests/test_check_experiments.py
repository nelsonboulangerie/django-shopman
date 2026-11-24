from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_experiments", ROOT / "scripts/check_experiments.py")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

TODAY = date(2026, 11, 23)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_has_no_expired_experiment():
    assert gate.run(ROOT, date.today()) == []


def test_expired_annotation_in_a_surface_fails(tmp_path):
    _write(
        tmp_path,
        "surfaces/storefront-nuxt/app/pages/index.vue",
        "<script setup>\n// EXPERIMENT(para-quando) remove_after 2026-11-22\n</script>\n",
    )
    [finding] = gate.run(tmp_path, TODAY)
    assert finding.path == "surfaces/storefront-nuxt/app/pages/index.vue"
    assert finding.line == 2
    assert "venceu em 2026-11-22" in finding.message


def test_annotation_on_its_last_day_passes(tmp_path):
    _write(
        tmp_path,
        "surfaces/storefront-nuxt/app/composables/x.ts",
        "// EXPERIMENT(para-quando) remove_after 2026-11-23\n"
        "<!-- EXPERIMENT(recompra) remove_after 2027-01-10 -->\n",
    )
    assert gate.run(tmp_path, TODAY) == []


def test_malformed_annotation_fails(tmp_path):
    _write(
        tmp_path,
        "surfaces/storefront-nuxt/app/x.ts",
        "// EXPERIMENT(para-quando)\n// EXPERIMENT(Para Quando) remove_after 2027-01-01\n"
        "// EXPERIMENT(ok) remove_after 31/12/2026\n",
    )
    messages = [f.message for f in gate.run(tmp_path, TODAY)]
    assert len(messages) == 3
    assert "malformada" in messages[0]
    assert "ref de experimento inválido" in messages[1]
    assert "ilegível" in messages[2]


def test_build_output_and_node_modules_are_ignored(tmp_path):
    for rel in (
        "surfaces/storefront-nuxt/node_modules/lib/x.js",
        "surfaces/storefront-nuxt/.output/public/x.js",
        "surfaces/storefront-nuxt/.nuxt/x.js",
    ):
        _write(tmp_path, rel, "// EXPERIMENT(velho) remove_after 2020-01-01\n")
    assert gate.run(tmp_path, TODAY) == []


def test_expired_rule_in_the_seed_fails_and_computed_date_passes(tmp_path):
    _write(
        tmp_path,
        "config/management/commands/seed.py",
        "RuleConfig.objects.update_or_create(ref='experience.velho', defaults={\n"
        "    'rule_path': 'shopman.shop.rules.experience.ExperienceRule',\n"
        "    'params': {'ref': 'velho', 'variants': ['a', 'b'], 'remove_after': '2026-10-01'},\n"
        "})\n"
        "ok = {'ref': 'novo', 'variants': ['a', 'b'], 'remove_after': (hoje + delta).isoformat()}\n",
    )
    [finding] = gate.run(tmp_path, TODAY)
    assert finding.path == "config/management/commands/seed.py"
    assert "'velho'" in finding.message and "2026-10-01" in finding.message


def test_expired_rule_in_an_instance_descriptor_or_fixture_fails(tmp_path):
    descriptor = {
        "rules": [{
            "ref": "experience.velho",
            "enabled": True,
            "config": {
                "rule_path": "shopman.shop.rules.experience.ExperienceRule",
                "params": {"ref": "velho", "variants": ["a", "b"], "remove_after": "2026-01-01"},
            },
        }]
    }
    _write(tmp_path, "config/instances/loja.json", json.dumps(descriptor))
    fixture = [{
        "model": "shop.ruleconfig",
        "fields": {
            "rule_path": "shopman.shop.rules.experience.ExperienceRule",
            "params": {"ref": "fixo", "variants": ["a", "b"], "remove_after": "2025-05-05"},
        },
    }]
    _write(tmp_path, "shopman/shop/fixtures/rules.json", json.dumps(fixture))

    refs = sorted(f.message.split("'")[1] for f in gate.run(tmp_path, TODAY))
    assert refs == ["fixo", "velho"]


def test_tests_are_not_seeds(tmp_path):
    """Teste prova o vencido de propósito: não é configuração semeada."""
    _write(
        tmp_path,
        "config/tests/test_x.py",
        "p = {'ref': 'velho', 'variants': ['a', 'b'], 'remove_after': '2020-01-01'}\n",
    )
    assert gate.run(tmp_path, TODAY) == []


def test_main_exit_code(tmp_path, capsys):
    _write(tmp_path, "surfaces/x/app.ts", "// EXPERIMENT(velho) remove_after 2020-01-01\n")
    assert gate.main(["--root", str(tmp_path), "--today", "2026-11-23"]) == 1
    assert "EXPERIMENT(velho) venceu" in capsys.readouterr().err
    assert gate.main(["--root", str(tmp_path), "--today", "2019-01-01"]) == 0
