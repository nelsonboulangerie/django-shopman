from __future__ import annotations

import json
from pathlib import Path

from scripts.watchman_sentry import _error_matches, _uptime_matches, _workflow_matches, reconcile

ROOT = Path(__file__).resolve().parents[3]


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return next(self.responses)


def _contract():
    return json.loads((ROOT / "ops/watchman/sentry.json").read_text())


def _uptime(contract, index, detector_id):
    item = contract["uptime"][index]
    return {
        "id": detector_id,
        "name": item["name"],
        "type": "uptime_domain_failure",
        "enabled": True,
        "config": {
            "environment": contract["environment"],
            "downtimeThreshold": item["downtime_threshold"],
            "recoveryThreshold": item["recovery_threshold"],
        },
        "dataSources": [
            {
                "queryObj": {
                    "url": item["url"],
                    "method": "GET",
                    "intervalSeconds": item["interval_seconds"],
                    "timeoutMs": item["timeout_ms"],
                }
            }
        ],
    }


def _error_rate(contract, detector_id):
    item = contract["error_rate"]
    return {
        "id": detector_id,
        "name": item["name"],
        "type": "metric_issue",
        "enabled": True,
        "dataSources": [
            {
                "queryObj": {
                    "snubaQuery": {
                        "aggregate": item["aggregate"],
                        "dataset": item["dataset"],
                        "environment": contract["environment"],
                        "query": item["query"],
                        "timeWindow": item["time_window_seconds"],
                    }
                }
            }
        ],
        "conditionGroup": {
            "conditions": [
                {"type": "gt", "comparison": item["open_above"], "conditionResult": 75},
                {"type": "lte", "comparison": item["resolve_at_or_below"], "conditionResult": 0},
            ]
        },
    }


def _workflow(contract, detector_ids):
    notification = contract["notification"]
    return {
        "id": "workflow-1",
        "name": notification["name"],
        "enabled": True,
        "environment": contract["environment"],
        "config": {"frequency": notification["frequency_minutes"]},
        "detectorIds": detector_ids,
        "triggers": {"conditions": [{"type": "issue_resolved_trigger"}]},
        "actionFilters": [
            {
                "actions": [
                    {
                        "type": "email",
                        "config": {"targetDisplay": notification["recipient"]},
                    }
                ]
            }
        ],
    }


def test_check_detects_every_missing_detector_and_workflow():
    client = FakeClient([[], []])

    changes = reconcile(client, _contract())

    assert len(changes) == 4
    assert any("missing notification workflow" in item for item in changes)
    assert all(path.startswith("/api/0/organizations/") for path in client.calls)


def test_exact_live_contract_passes_using_only_get_requests():
    contract = _contract()
    detectors = [_uptime(contract, 0, "1"), _uptime(contract, 1, "2"), _error_rate(contract, "3")]
    client = FakeClient([detectors, [_workflow(contract, ["1", "2", "3"])]] )

    changes = reconcile(client, contract)

    assert changes == []
    assert len(client.calls) == 2


def test_live_detector_comparison_rejects_same_name_with_wrong_configuration():
    contract = _contract()
    uptime = _uptime(contract, 0, "1")
    uptime["dataSources"][0]["queryObj"]["url"] = "https://wrong.example/"
    rate = _error_rate(contract, "3")

    assert _uptime_matches(uptime, contract["uptime"][0], "production") is False
    assert _error_matches(rate, contract) is True


def test_workflow_must_bind_all_detectors_recipient_frequency_and_resolution():
    contract = _contract()
    workflow = _workflow(contract, ["1", "2"])

    assert _workflow_matches(workflow, contract, {"1", "2", "3"}) is False

    workflow["detectorIds"].append("3")
    assert _workflow_matches(workflow, contract, {"1", "2", "3"}) is True

    workflow["config"]["frequency"] = 60
    assert _workflow_matches(workflow, contract, {"1", "2", "3"}) is False


def test_check_reports_configuration_drift_instead_of_name_only_success():
    contract = _contract()
    detectors = [_uptime(contract, 0, "1"), _uptime(contract, 1, "2"), _error_rate(contract, "3")]
    detectors[0]["config"]["downtimeThreshold"] = 99
    workflow = _workflow(contract, ["1", "2", "3"])
    workflow["actionFilters"] = []
    client = FakeClient([detectors, [workflow]])

    changes = reconcile(client, contract)

    assert changes == [
        f"uptime detector has drift: {contract['uptime'][0]['name']}",
        f"notification workflow has drift: {contract['notification']['name']}",
    ]
