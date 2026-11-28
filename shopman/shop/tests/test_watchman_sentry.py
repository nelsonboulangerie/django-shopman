from __future__ import annotations

import json
import urllib.error
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest

from scripts.watchman_sentry import (
    SentryClient,
    _contract_errors,
    _dedicated_member_target_id,
    _error_matches,
    _next_page_url,
    _uptime_matches,
    _workflow_matches,
    reconcile,
)

ROOT = Path(__file__).resolve().parents[3]


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get_all(self, path):
        self.calls.append(path)
        return next(self.responses)


def _contract():
    return json.loads((ROOT / "ops/watchman/sentry.json").read_text())


def _member(contract, user_id="user-456"):
    address = contract["notification"]["delivery_assurance"]["intended_address"]
    return {
        "email": address,
        "pending": False,
        "expired": False,
        "inviteStatus": "approved",
        "user": {
            "id": user_id,
            "email": address,
            "isActive": True,
            "isSuspended": False,
        },
    }


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


def _workflow(contract, detector_ids, target_identifier="user-456"):
    notification = contract["notification"]
    email = notification["email_action"]
    return {
        "id": "workflow-1",
        "name": notification["name"],
        "enabled": True,
        "environment": contract["environment"],
        "config": {"frequency": notification["frequency_minutes"]},
        "detectorIds": detector_ids,
        "triggers": {
            "logicType": "any-short",
            "conditions": [
                {"type": trigger, "comparison": True, "conditionResult": True}
                for trigger in notification["trigger_types"]
            ],
            "actions": [],
        },
        "actionFilters": [
            {
                "logicType": "all",
                "conditions": [],
                "actions": [
                    {
                        "type": "email",
                        "status": "active",
                        "config": {
                            "targetType": email["target_type"],
                            "targetIdentifier": target_identifier,
                            "targetDisplay": None,
                        },
                    }
                ],
            }
        ],
    }


def _live_objects(contract):
    uptimes = [_uptime(contract, index, str(index + 1)) for index in range(len(contract["uptime"]))]
    error_id = str(len(uptimes) + 1)
    detectors = [*uptimes, _error_rate(contract, error_id)]
    return detectors, _workflow(contract, [str(index + 1) for index in range(len(detectors))])


def test_repository_contract_resolves_target_from_live_membership_instead_of_storing_an_id():
    raw = json.loads((ROOT / "ops/watchman/sentry.json").read_text())

    assert _contract_errors(raw) == []
    assert raw["uptime"][0]["name"] == "Uptime check for api.boulangerie.com.br/health/ready"
    assert raw["error_rate"]["name"] == "Number of errors above 20 over past 5 minutes"
    assert "target_identifier" not in raw["notification"]["email_action"]


def test_check_detects_every_missing_detector_and_workflow():
    contract = _contract()
    client = FakeClient([[], [], []])

    changes = reconcile(client, contract)

    assert len(changes) == len(contract["uptime"]) + 3
    assert "missing dedicated notification member" in changes
    assert any("missing notification workflow" in item for item in changes)
    assert all(path.startswith("/api/0/organizations/") for path in client.calls)


def test_exact_live_contract_passes_using_only_complete_collection_reads():
    contract = _contract()
    detectors, workflow = _live_objects(contract)
    client = FakeClient([detectors, [_member(contract)], [workflow]])

    assert reconcile(client, contract) == []
    assert len(client.calls) == 3
    assert client.calls[1].endswith("/members/")


def test_dedicated_member_resolves_exact_active_accepted_user_id():
    contract = _contract()
    address = contract["notification"]["delivery_assurance"]["intended_address"]

    assert _dedicated_member_target_id([_member(contract)], address) == ("user-456", None)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda member: member.update(pending=True),
        lambda member: member.update(expired=True),
        lambda member: member.update(inviteStatus="pending"),
        lambda member: member["user"].update(isActive=False),
        lambda member: member["user"].update(isSuspended=True),
        lambda member: member["user"].update(id=None),
        lambda member: member["user"].update(email=""),
    ],
)
def test_dedicated_member_fails_closed_until_active_and_accepted(mutation):
    contract = _contract()
    address = contract["notification"]["delivery_assurance"]["intended_address"]
    member = _member(contract)
    mutation(member)

    assert _dedicated_member_target_id([member], address) == (
        None,
        "dedicated notification member is not active and accepted",
    )


def test_dedicated_member_fails_closed_when_missing_or_duplicated():
    contract = _contract()
    address = contract["notification"]["delivery_assurance"]["intended_address"]
    member = _member(contract)

    assert _dedicated_member_target_id([], address) == (None, "missing dedicated notification member")
    assert _dedicated_member_target_id([member, deepcopy(member)], address) == (
        None,
        "duplicate dedicated notification members",
    )


def test_reconcile_rejects_workflow_target_that_differs_from_resolved_member_id():
    contract = _contract()
    detectors, workflow = _live_objects(contract)
    workflow["actionFilters"][0]["actions"][0]["config"]["targetIdentifier"] = "wrong-user"
    client = FakeClient([detectors, [_member(contract)], [workflow]])

    assert reconcile(client, contract) == [f"notification workflow has drift: {contract['notification']['name']}"]


def test_live_detector_comparison_rejects_same_name_with_wrong_configuration():
    contract = _contract()
    uptime = _uptime(contract, 0, "1")
    uptime["dataSources"][0]["queryObj"]["url"] = "https://wrong.example/"
    rate = _error_rate(contract, "3")

    assert _uptime_matches(uptime, contract["uptime"][0], "production") is False
    assert _error_matches(rate, contract) is True


def test_workflow_requires_all_detectors_frequency_opening_resolution_and_structural_email_target():
    contract = _contract()
    expected_ids = {"1", "2"}
    workflow = _workflow(contract, ["1"])
    assert _workflow_matches(workflow, contract, expected_ids, "user-456") is False

    workflow["detectorIds"].append("2")
    assert _workflow_matches(workflow, contract, expected_ids, "user-456") is True

    workflow["triggers"]["conditions"] = [{"type": "issue_resolved_trigger"}]
    assert _workflow_matches(workflow, contract, expected_ids, "user-456") is False

    workflow = _workflow(contract, ["1", "2"])
    workflow["triggers"]["conditions"] = [{"type": "first_seen_event"}]
    assert _workflow_matches(workflow, contract, expected_ids, "user-456") is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda workflow: workflow["actionFilters"][0]["actions"][0].update(status="inactive"),
        lambda workflow: workflow["actionFilters"][0]["actions"][0].update(type="slack"),
        lambda workflow: workflow["actionFilters"][0]["actions"][0]["config"].update(targetIdentifier="wrong-user"),
        lambda workflow: workflow["actionFilters"][0]["actions"][0]["config"].update(targetType="issue_owners"),
    ],
)
def test_workflow_rejects_inactive_wrong_type_or_wrong_identity_email_actions(mutation):
    contract = _contract()
    workflow = _workflow(contract, ["1", "2"])
    mutation(workflow)

    assert _workflow_matches(workflow, contract, {"1", "2"}, "user-456") is False


def test_recipient_text_elsewhere_cannot_create_false_positive():
    contract = _contract()
    workflow = _workflow(contract, ["1", "2"])
    workflow["actionFilters"] = []
    workflow["description"] = "manda para ti@boulangerie.com.br user-456"

    assert _workflow_matches(workflow, contract, {"1", "2"}, "user-456") is False


def test_email_behind_an_extra_filter_cannot_create_false_positive():
    contract = _contract()
    workflow = _workflow(contract, ["1", "2"])
    workflow["actionFilters"][0]["conditions"] = [
        {"type": "tagged_event", "comparison": {"key": "never", "value": "matches"}}
    ]

    assert _workflow_matches(workflow, contract, {"1", "2"}, "user-456") is False


def test_disabled_trigger_or_wrong_trigger_logic_cannot_create_false_positive():
    contract = _contract()
    workflow = _workflow(contract, ["1", "2"])
    workflow["triggers"]["conditions"][0]["conditionResult"] = False
    assert _workflow_matches(workflow, contract, {"1", "2"}, "user-456") is False

    workflow = _workflow(contract, ["1", "2"])
    workflow["triggers"]["logicType"] = "all"
    assert _workflow_matches(workflow, contract, {"1", "2"}, "user-456") is False


def test_duplicate_expected_live_detector_and_workflow_names_fail_closed():
    contract = _contract()
    detectors, workflow = _live_objects(contract)
    detectors.append(deepcopy(detectors[0]))
    client = FakeClient([detectors, [_member(contract)], [workflow, deepcopy(workflow)]])

    changes = reconcile(client, contract)

    assert f"duplicate detector name: {contract['uptime'][0]['name']}" in changes
    assert f"duplicate notification workflow name: {contract['notification']['name']}" in changes


def test_duplicate_detector_names_in_contract_are_rejected_before_api_access():
    contract = _contract()
    contract["uptime"].append(deepcopy(contract["uptime"][0]))
    client = FakeClient([])

    assert reconcile(client, contract) == [
        f"invalid contract: duplicate expected detector name: {contract['uptime'][0]['name']}",
        "invalid contract: free-plan policy requires exactly one uptime detector",
    ]
    assert client.calls == []


@pytest.mark.parametrize("invalid_limit", [None, True, 0, 2])
def test_free_plan_limit_must_be_exactly_one_integer(invalid_limit):
    contract = _contract()
    contract["uptime_policy"]["maximum_active_monitors"] = invalid_limit

    assert "invalid contract: free-plan policy requires exactly one uptime detector" in _contract_errors(contract)


def test_free_plan_policy_rejects_any_unexpected_active_uptime_detector():
    contract = _contract()
    detectors, workflow = _live_objects(contract)
    legacy = deepcopy(detectors[0])
    legacy.update(id="legacy", name="Legacy uptime")
    client = FakeClient([[*detectors, legacy], [_member(contract)], [workflow]])

    assert reconcile(client, contract) == ["unexpected active uptime detector: Legacy uptime"]


def test_indirect_email_routing_is_rejected_without_a_machine_verifiable_adapter():
    contract = _contract()
    contract["notification"]["delivery_assurance"]["method"] = "evidenced_email_routing"

    assert _contract_errors(contract) == ["invalid contract: notification delivery assurance is not machine-verifiable"]


def test_check_reports_configuration_drift_instead_of_name_only_success():
    contract = _contract()
    detectors, workflow = _live_objects(contract)
    detectors[0]["config"]["downtimeThreshold"] = 99
    workflow["actionFilters"] = []
    client = FakeClient([detectors, [_member(contract)], [workflow]])

    assert reconcile(client, contract) == [
        f"uptime detector has drift: {contract['uptime'][0]['name']}",
        f"notification workflow has drift: {contract['notification']['name']}",
    ]


def test_pagination_follows_all_pages_and_preserves_query(monkeypatch):
    client = SentryClient(base_url="https://sentry.example", token="secret")
    pages = iter(
        [
            ([{"id": "1"}], '<https://sentry.example/api/items/?cursor=next>; rel="next"; results="true"'),
            ([{"id": "2"}], '<https://sentry.example/api/items/?cursor=done>; rel="next"; results="false"'),
        ]
    )
    calls = []

    def fake_get_page(path):
        calls.append(path)
        return next(pages)

    monkeypatch.setattr(client, "_get_page", fake_get_page)

    assert client.get_all("/api/items/?project=shopman") == [{"id": "1"}, {"id": "2"}]
    assert calls == ["/api/items/?project=shopman&per_page=100", "/api/items/?cursor=next"]


def test_pagination_fails_closed_on_cycle_external_host_and_malformed_next(monkeypatch):
    client = SentryClient(base_url="https://sentry.example", token="secret")
    monkeypatch.setattr(
        client,
        "_get_page",
        lambda path: ([], '<https://sentry.example/api/items/?per_page=100>; rel="next"; results="true"'),
    )
    with pytest.raises(RuntimeError, match="cycle"):
        client.get_all("/api/items/")

    monkeypatch.setattr(
        client,
        "_get_page",
        lambda path: ([], '<https://attacker.example/api/items/>; rel="next"; results="true"'),
    )
    with pytest.raises(RuntimeError, match="outside"):
        client.get_all("/api/items/")

    with pytest.raises(RuntimeError, match="invalid next-page"):
        _next_page_url('broken; rel="next"; results="true"')

    with pytest.raises(RuntimeError, match="ambiguous next-page"):
        _next_page_url('<https://sentry.example/api/items/>; rel="next"')


def test_api_permission_failure_does_not_echo_response_content(monkeypatch):
    contract = _contract()
    address = contract["notification"]["delivery_assurance"]["intended_address"]
    error = urllib.error.HTTPError(
        "https://sentry.example/api/0/organizations/example/members/",
        403,
        "Forbidden",
        {},
        BytesIO(address.encode()),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    client = SentryClient(base_url="https://sentry.example", token="secret")

    with pytest.raises(RuntimeError, match="returned 403") as exc_info:
        client.get_all("/api/0/organizations/example/members/")

    assert address not in str(exc_info.value)
