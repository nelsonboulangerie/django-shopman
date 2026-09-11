from __future__ import annotations

import json
import pathlib
import re

from shopman.shop.services.marketing_observability import _ALERT_POLICY

ROOT = pathlib.Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "docs" / "operations" / "marketing-runbook-drills.v1.json"
RUNBOOKS = {
    "docs/runbooks/marketing-stuck-command.md",
    "docs/runbooks/marketing-partial-retry.md",
    "docs/runbooks/marketing-unknown-provider-effect.md",
    "docs/runbooks/marketing-channel-readiness-outage.md",
    "docs/runbooks/marketing-consent-or-privacy-incident.md",
    "docs/runbooks/marketing-bad-content-or-link.md",
    "docs/runbooks/marketing-cancel-and-reconcile.md",
    "docs/runbooks/marketing-rollout-rollback.md",
}
REQUIRED_SECTIONS = (
    "## Quando abrir",
    "## Primeiros 2 minutos",
    "## Diagnóstico read-only",
    "## Freeze/circuit",
    "## Decisões proibidas",
    "## Comunicação",
    "## Recuperação idempotente",
    "## Fechamento e reconciliação",
    "## Drill local",
)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_exact_eight_planned_runbooks_have_the_full_operator_contract():
    manifest = _manifest()
    assert manifest["scope"] == "local_synthetic_only"
    assert manifest["production_write_performed"] is False
    assert manifest["provider_calls_expected"] == 0
    assert manifest["single_command"] == "make marketing-drills"
    assert len(manifest["scenarios"]) == 8
    assert {item["runbook"] for item in manifest["scenarios"]} == RUNBOOKS

    for relative_path in RUNBOOKS:
        source = (ROOT / relative_path).read_text()
        for section in REQUIRED_SECTIONS:
            assert section in source, f"{relative_path} missing {section}"
        assert "make marketing-diagnose" in source
        first_steps = source.split("## Primeiros 2 minutos", 1)[1].split("## ", 1)[0]
        assert len(re.findall(r"^\d+\. ", first_steps, flags=re.MULTILINE)) <= 4


def test_every_dashboard_and_runtime_alert_links_to_an_existing_planned_runbook():
    dashboard = json.loads(
        (ROOT / "docs" / "observability" / "marketing-slo-dashboard.v1.json").read_text()
    )
    dashboard_paths = {alert["runbook"] for alert in dashboard["alerts"]}
    runtime_paths = {policy[2] for policy in _ALERT_POLICY.values()}

    assert dashboard_paths <= RUNBOOKS
    assert runtime_paths <= RUNBOOKS
    for relative_path in dashboard_paths | runtime_paths:
        assert (ROOT / relative_path).is_file()


def test_readme_and_single_command_remove_navigation_and_retyping():
    readme = (ROOT / "docs" / "runbooks" / "README.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    manifest = _manifest()

    for relative_path in RUNBOOKS:
        assert pathlib.Path(relative_path).name in readme
    assert "marketing-diagnose:" in makefile
    assert "marketing-drills:" in makefile
    for scenario in manifest["scenarios"]:
        assert scenario["automated_test"] in makefile
        assert scenario["operator_decision"]
