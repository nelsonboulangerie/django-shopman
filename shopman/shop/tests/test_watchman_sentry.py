from __future__ import annotations

import json
from pathlib import Path

from scripts.watchman_sentry import _error_matches, _error_payload, _uptime_matches, _uptime_payload, reconcile

ROOT = Path(__file__).resolve().parents[3]


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return next(self.responses)


def _contract():
    return json.loads((ROOT / "ops/watchman/sentry.json").read_text())


def test_check_detects_every_missing_detector_and_wrong_recipient():
    client = FakeClient([[], []])

    changes = reconcile(client, _contract(), apply=False)

    assert len(changes) == 4
    assert any("ti@boulangerie.com.br" in item for item in changes)


def test_apply_creates_two_uptime_and_one_rate_detector_without_guessing_workflow():
    client = FakeClient([[], {}, {}, {}, []])

    changes = reconcile(client, _contract(), apply=True)

    posts = [call for call in client.calls if call[0] == "POST"]
    assert len(posts) == 3
    assert sum(path.endswith("/uptime/") for _, path, _ in posts) == 2
    assert changes == ["notification workflow does not target ti@boulangerie.com.br"]


def test_payloads_preserve_one_minute_cadence_and_resolved_threshold():
    contract = _contract()

    uptime = _uptime_payload(contract["uptime"][0], contract["environment"])
    rate = _error_payload(contract)

    assert uptime["intervalSeconds"] == 60
    assert uptime["downtimeThreshold"] == 3
    assert rate["conditionGroup"]["conditions"][-1]["conditionResult"] == 0


def test_live_detector_comparison_rejects_same_name_with_wrong_configuration():
    contract = _contract()
    uptime = contract["uptime"][0]
    found_uptime = {
        "type": "uptime_domain_failure",
        "enabled": True,
        "config": {"environment": "production", "downtimeThreshold": 3, "recoveryThreshold": 2},
        "dataSources": [
            {"queryObj": {"url": "https://wrong.example/", "method": "GET", "intervalSeconds": 60, "timeoutMs": 10000}}
        ],
    }
    error = _error_payload(contract)
    error["dataSources"][0]["queryObj"] = {"snubaQuery": error["dataSources"][0]}

    assert _uptime_matches(found_uptime, uptime, "production") is False
    assert _error_matches(error, contract) is True


def test_check_reports_configuration_drift_instead_of_name_only_success():
    contract = _contract()
    detectors = [
        {"name": item["name"], "type": "uptime_domain_failure", "enabled": True} for item in contract["uptime"]
    ]
    detectors.append({"name": contract["error_rate"]["name"], "type": "metric_issue", "enabled": True})
    client = FakeClient([detectors, [{"actions": [{"target": "ti@boulangerie.com.br"}]}]])

    changes = reconcile(client, contract, apply=False)

    assert len(changes) == 3
    assert all("has drift" in item for item in changes)
