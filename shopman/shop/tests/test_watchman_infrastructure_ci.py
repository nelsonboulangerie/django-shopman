import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from scripts.run_watchman_infrastructure_ci import capture_sentry_event, classify_results, main

ROOT = Path(__file__).resolve().parents[3]


def _result(check_id, status, *, evidence=None):
    return {
        "id": check_id,
        "status": status,
        "summary": f"{check_id} {status}",
        "evidence": evidence or {},
        "remediation": None,
        "observed_at": "2026-10-15T12:00:00+00:00",
        "duration_ms": 1.0,
    }


def _payload(*results):
    by_id = {
        "production_contract": _result("production_contract", "pass"),
        "deployment_drift": _result("deployment_drift", "pass"),
        "external_monitoring": _result("external_monitoring", "pass"),
        "expiry_lifecycle": _result("expiry_lifecycle", "pass"),
    }
    for result in results:
        by_id[result["id"]] = result
    statuses = {result["status"] for result in by_id.values()}
    report_status = next(
        (status for status in ("fail", "unknown", "warn", "pass") if status in statuses),
        "skipped",
    )
    return {
        "schema_version": 1,
        "profile": "infrastructure",
        "status": report_status,
        "started_at": "2026-10-15T12:00:00+00:00",
        "duration_ms": 4.0,
        "checks": list(by_id.values()),
    }


def test_missing_sentry_read_access_is_blocking():
    payload = _payload(
        _result(
            "external_monitoring",
            "unknown",
            evidence={"required_env": "SENTRY_AUTH_TOKEN"},
        )
    )

    blocking, pending, warnings = classify_results(payload)

    assert [item["id"] for item in blocking] == ["external_monitoring"]
    assert pending == []
    assert warnings == []


def test_real_drift_and_unexpected_unknown_are_blocking():
    payload = _payload(
        _result("deployment_drift", "fail"),
        _result("production_contract", "unknown"),
        _result("external_monitoring", "fail"),
    )

    blocking, pending, warnings = classify_results(payload)

    assert pending == []
    assert warnings == []
    assert [item["id"] for item in blocking] == [
        "production_contract",
        "deployment_drift",
        "external_monitoring",
    ]


def test_missing_digitalocean_evidence_does_not_hide_external_monitoring_result():
    payload = _payload(
        _result(
            "deployment_drift",
            "unknown",
            evidence={
                "required_env": "WATCHMAN_LIVE_DO_SPEC",
                "collection_error": "missing DIGITALOCEAN_READ_TOKEN",
            },
        ),
        _result("external_monitoring", "pass"),
        _result("expiry_lifecycle", "warn"),
    )

    blocking, pending, warnings = classify_results(payload)

    assert [item["id"] for item in blocking] == ["deployment_drift"]
    assert pending == []
    assert [item["id"] for item in warnings] == ["expiry_lifecycle"]
    assert next(item for item in payload["checks"] if item["id"] == "external_monitoring")["status"] == "pass"


def test_sentry_unknown_is_blocking_when_reason_is_not_missing_read_token():
    payload = _payload(_result("external_monitoring", "unknown", evidence={"error": "timeout"}))

    blocking, pending, warnings = classify_results(payload)

    assert pending == []
    assert warnings == []
    assert [item["id"] for item in blocking] == ["external_monitoring"]


def test_warning_is_classified_as_actionable():
    payload = _payload(_result("expiry_lifecycle", "warn"))

    blocking, pending, warnings = classify_results(payload)

    assert blocking == []
    assert pending == []
    assert [item["id"] for item in warnings] == ["expiry_lifecycle"]


def test_runner_reads_the_complete_report_schema_emitted_by_watchman():
    payload = _payload(_result("deployment_drift", "fail"))

    blocking, _, _ = classify_results(payload)

    assert [item["id"] for item in blocking] == ["deployment_drift"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": 1, "profile": "infrastructure", "checks": []},
        {"schema_version": 2, "profile": "infrastructure", "checks": [_result("deployment_drift", "pass")]},
        {"schema_version": 1, "profile": "infrastructure", "checks": "not-a-list"},
        {"schema_version": 1, "profile": "infrastructure", "checks": [None]},
    ],
)
def test_empty_or_unknown_report_schema_fails_closed(payload):
    blocking, pending, warnings = classify_results(payload)

    assert pending == []
    assert warnings == []
    assert [item["id"] for item in blocking] == ["watchman_report_contract"]


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (lambda checks: checks.pop(), "missing check ids"),
        (lambda checks: checks.append(checks[0].copy()), "duplicate check ids"),
        (lambda checks: checks.append(_result("unexpected", "pass")), "unexpected check ids"),
        (lambda checks: checks[0].update(status="maybe"), "status is invalid"),
        (lambda checks: checks[0].update(summary=None), "summary must be a non-empty string"),
        (lambda checks: checks[0].update(evidence=[]), "evidence must be an object"),
        (lambda checks: checks[0].update(status=[]), "status is invalid"),
        (lambda checks: checks[0].update(observed_at="yesterday"), "observed_at must be"),
        (lambda checks: checks[0].update(duration_ms=-1), "duration_ms must be"),
    ],
)
def test_partial_duplicate_or_malformed_reports_fail_closed(mutate, expected_error):
    payload = _payload()
    mutate(payload["checks"])

    blocking, pending, warnings = classify_results(payload)

    assert pending == []
    assert warnings == []
    assert [item["id"] for item in blocking] == ["watchman_report_contract"]
    assert any(expected_error in error for error in blocking[0]["evidence"]["errors"])


def test_exact_infrastructure_check_ids_are_required():
    payload = {
        "schema_version": 1,
        "profile": "infrastructure",
        "status": "pass",
        "started_at": "2026-10-15T12:00:00+00:00",
        "duration_ms": 4.0,
        "checks": [
            _result("production_contract", "pass"),
            _result("deployment_drift", "pass"),
            _result("external_monitoring", "pass"),
            _result("expiry_lifecycle", "pass"),
        ],
    }

    blocking, pending, warnings = classify_results(payload)

    assert blocking == []
    assert pending == []
    assert warnings == []


def test_report_status_must_match_its_check_results():
    payload = _payload(_result("deployment_drift", "fail"))
    payload["status"] = "pass"

    blocking, pending, warnings = classify_results(payload)

    assert [item["id"] for item in blocking] == ["watchman_report_contract"]
    assert pending == []
    assert warnings == []
    assert any("does not match checks" in error for error in blocking[0]["evidence"]["errors"])


def test_skipped_check_is_blocking_even_though_it_is_a_valid_status():
    blocking, pending, warnings = classify_results(_payload(_result("external_monitoring", "skipped")))

    assert [item["id"] for item in blocking] == ["external_monitoring"]
    assert pending == []
    assert warnings == []


def test_warning_is_reported_but_keeps_daily_job_green(monkeypatch, tmp_path, capsys):
    from shopman.watchman import runner

    report = Mock()
    report.to_dict.return_value = _payload(_result("expiry_lifecycle", "warn"))
    monkeypatch.setattr(runner, "run_profile", lambda profile: report)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    output = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["run_watchman_infrastructure_ci.py", "--output", str(output)])

    assert main() == 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result == {
        "status": "pass",
        "pending": [],
        "warnings": ["expiry_lifecycle"],
        "sentry_event_captured": False,
    }
    assert json.loads(output.read_text(encoding="utf-8"))["profile"] == "infrastructure"


def test_sentry_capture_is_honest_when_dsn_is_missing(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    assert capture_sentry_event([_result("deployment_drift", "fail")], blocking=True) is False


@pytest.mark.parametrize(("event_id", "expected"), [("event-id", True), (None, False)])
def test_sentry_capture_only_reports_a_returned_event_id(monkeypatch, event_id, expected):
    class Scope:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def set_level(self, level):
            pass

        def set_tag(self, key, value):
            pass

        def set_context(self, key, value):
            pass

    sentry = SimpleNamespace(
        push_scope=lambda: Scope(),
        capture_message=lambda message: event_id,
        flush=lambda timeout: None,
    )
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", sentry)

    assert capture_sentry_event([_result("deployment_drift", "fail")], blocking=True) is expected


def test_warning_capture_uses_warning_level(monkeypatch):
    observed = {}

    class Scope:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def set_level(self, level):
            observed["level"] = level

        def set_tag(self, key, value):
            pass

        def set_context(self, key, value):
            pass

    sentry = SimpleNamespace(
        push_scope=lambda: Scope(),
        capture_message=lambda message: "event-id",
        flush=lambda timeout: None,
    )
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", sentry)

    assert capture_sentry_event([_result("expiry_lifecycle", "warn")], blocking=False) is True
    assert observed["level"] == "warning"


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
    assert job["env"]["WATCHMAN_VERSIONED_DO_SPEC"] == ".do/app.alpha-subdomains.yaml"


def test_daily_workflow_always_runs_aggregate_after_digitalocean_collection_failure():
    path = ROOT / ".github/workflows/watchman-infrastructure.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["read-only-contract"]["steps"]
    by_name = {step["name"]: step for step in steps}

    assert by_name["Record missing DigitalOcean read-only credential"]["if"] == "${{ env.DO_READ_TOKEN == '' }}"
    assert by_name["Set up doctl with read-only credential"]["continue-on-error"] is True
    assert by_name["Read live DigitalOcean spec"]["if"] == "${{ always() && env.DO_READ_TOKEN != '' }}"
    assert by_name["Run Watchman infrastructure profile"]["if"] == "always()"
    assert "WATCHMAN_DO_EVIDENCE_ERROR" in path.read_text(encoding="utf-8")


def test_live_spec_prefetch_proves_apps_and_databases_read_access():
    path = ROOT / ".github/workflows/watchman-infrastructure.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["read-only-contract"]["steps"]
    live_read = next(step for step in steps if step["name"] == "Read live DigitalOcean spec")["run"]

    database_probe = "doctl databases list --format ID --no-header"
    app_probe = "doctl apps list --format ID,Spec.Name --no-header"
    spec_read = "doctl apps spec get"
    assert database_probe in live_read
    assert app_probe in live_read
    assert spec_read in live_read
    assert live_read.index(database_probe) < live_read.index(app_probe) < live_read.index(spec_read)
    assert "DigitalOcean token cannot read databases" in live_read
