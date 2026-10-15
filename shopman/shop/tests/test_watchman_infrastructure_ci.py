from pathlib import Path

import yaml

from scripts.run_watchman_infrastructure_ci import classify_results

ROOT = Path(__file__).resolve().parents[3]


def _result(check_id, status, *, evidence=None):
    return {
        "id": check_id,
        "status": status,
        "summary": f"{check_id} {status}",
        "evidence": evidence or {},
    }


def test_only_missing_sentry_read_access_is_non_blocking_pending():
    payload = {
        "results": [
            _result("production_contract", "pass"),
            _result("deployment_drift", "pass"),
            _result(
                "external_monitoring",
                "unknown",
                evidence={"required_env": "SENTRY_AUTH_TOKEN"},
            ),
        ]
    }

    blocking, pending = classify_results(payload)

    assert blocking == []
    assert [item["id"] for item in pending] == ["external_monitoring"]


def test_real_drift_and_unexpected_unknown_are_blocking():
    payload = {
        "results": [
            _result("deployment_drift", "fail"),
            _result("production_contract", "unknown"),
            _result("external_monitoring", "fail"),
        ]
    }

    blocking, pending = classify_results(payload)

    assert pending == []
    assert [item["id"] for item in blocking] == [
        "deployment_drift",
        "production_contract",
        "external_monitoring",
    ]


def test_sentry_unknown_is_blocking_when_reason_is_not_missing_read_token():
    payload = {
        "results": [
            _result("external_monitoring", "unknown", evidence={"error": "timeout"}),
        ]
    }

    blocking, pending = classify_results(payload)

    assert pending == []
    assert [item["id"] for item in blocking] == ["external_monitoring"]


def test_daily_workflow_is_read_only_and_preserves_evidence():
    path = ROOT / ".github/workflows/watchman-infrastructure.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["read-only-contract"]
    rendered = path.read_text(encoding="utf-8")

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["schedule"] == [{"cron": "23 09 * * *"}]
    assert "DIGITALOCEAN_READ_TOKEN" in rendered
    assert "WATCHMAN_LIVE_DO_SPEC" in rendered
    assert "actions/upload-artifact" in rendered
    assert "doctl apps update" not in rendered
    assert "watchman_sentry.py apply" not in rendered
    assert job["timeout-minutes"] == 20
