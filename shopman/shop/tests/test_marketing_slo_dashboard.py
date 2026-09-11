from __future__ import annotations

import json
from pathlib import Path

from shopman.shop.services.marketing_observability import METRIC_SPECS

DASHBOARD = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "observability"
    / "marketing-slo-dashboard.v1.json"
)
FORBIDDEN_DIMENSIONS = {
    "announcement",
    "body",
    "campaign",
    "content",
    "customer",
    "phone",
    "prompt",
    "provider_response",
    "recipient",
    "url",
}


def test_dashboard_is_local_gated_and_every_panel_uses_registered_safe_labels():
    manifest = json.loads(DASHBOARD.read_text())

    assert manifest["status"] == "local_candidate"
    assert manifest["activation_gate"] == "G-H08"
    assert manifest["production_write_performed"] is False
    assert manifest["data_classification"] == "aggregate_no_pii"
    for dashboard in manifest["dashboards"]:
        assert dashboard["owner"]
        for panel in dashboard["panels"]:
            spec = METRIC_SPECS[panel["metric"]]
            assert set(panel["group_by"]) <= set(spec.labels)
            assert not (set(panel["group_by"]) & FORBIDDEN_DIMENSIONS)


def test_dashboard_covers_human_approved_budgets_and_actionable_alerts():
    manifest = json.loads(DASHBOARD.read_text())
    budgets = manifest["budgets"]

    assert budgets["board_projection"] == {
        "p95_seconds": 0.5,
        "max_bytes": 307200,
        "max_queries": 25,
    }
    assert budgets["audience_100k"] == {"p95_seconds": 2.0, "max_queries": 30}
    assert budgets["duplicate_confirmed"]["maximum"] == 0
    assert budgets["post_optout_or_expiry"]["maximum"] == 0
    assert budgets["worker"] == {"chunk_size": 100, "concurrency": 4, "lease_seconds": 60}

    for alert in manifest["alerts"]:
        assert alert["filter"]
        assert alert["owner"]
        assert alert["runbook"].startswith("docs/runbooks/marketing-")
    assert any("G-H08" in item for item in manifest["activation_requirements"])
