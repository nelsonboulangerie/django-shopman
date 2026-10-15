from __future__ import annotations

import json
from pathlib import Path

from scripts.watchman_sentry import _error_payload, _uptime_payload, reconcile

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
    assert any("notification workflow" in item for item in changes)


def test_payloads_preserve_one_minute_cadence_and_resolved_threshold():
    contract = _contract()

    uptime = _uptime_payload(contract["uptime"][0], contract["environment"])
    rate = _error_payload(contract)

    assert uptime["intervalSeconds"] == 60
    assert uptime["downtimeThreshold"] == 3
    assert rate["conditionGroup"]["conditions"][-1]["conditionResult"] == 0
