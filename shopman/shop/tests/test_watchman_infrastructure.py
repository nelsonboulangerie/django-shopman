from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import Mock, patch

from shopman.watchman.contracts import CheckContext, Status

from shopman.shop import watchman_infrastructure as infrastructure
from shopman.shop.watchman_infrastructure import DeploymentDriftCheck, ExternalMonitoringContractCheck


def _context():
    return CheckContext(profile="infrastructure", deadline=9999999999)


def test_external_monitoring_contract_is_unknown_without_live_credential(monkeypatch):
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence == {
        "uptime_monitors": 1,
        "recipient": "ti@boulangerie.com.br",
        "required_env": "SENTRY_AUTH_TOKEN",
    }


@patch("shopman.shop.watchman_infrastructure._run")
def test_external_monitoring_contract_checks_live_drift_when_credential_exists(run, monkeypatch):
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "test-token")
    run.return_value = Mock(status=Status.PASS)

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.PASS
    command = run.call_args.args[1]
    assert command[-2:] == ["scripts/watchman_sentry.py", "check"]


def test_external_monitoring_contract_rejects_paid_or_non_composite_uptime(monkeypatch, tmp_path):
    original = json.loads((infrastructure.ROOT / "ops/watchman/sentry.json").read_text(encoding="utf-8"))
    paid = deepcopy(original)
    paid["uptime"].append({**paid["uptime"][0], "name": "Second uptime"})
    wrong_target = deepcopy(original)
    wrong_target["uptime"][0]["url"] = "https://api.boulangerie.com.br/health/ready/"
    invalid_limit = deepcopy(original)
    invalid_limit["uptime_policy"]["maximum_active_monitors"] = True
    no_route = deepcopy(original)
    no_route["notification"]["delivery_assurance"]["intended_address"] = "ti"
    contract_path = tmp_path / "ops/watchman/sentry.json"
    contract_path.parent.mkdir(parents=True)
    monkeypatch.setattr(infrastructure, "ROOT", tmp_path)
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    for payload in (paid, wrong_target, invalid_limit, no_route):
        contract_path.write_text(json.dumps(payload), encoding="utf-8")
        result = ExternalMonitoringContractCheck().run(_context())
        assert result.status is Status.FAIL
        assert result.summary == "external monitoring contract is incomplete"


def test_deployment_drift_is_unknown_without_live_snapshot(monkeypatch):
    monkeypatch.delenv("WATCHMAN_LIVE_DO_SPEC", raising=False)
    monkeypatch.delenv("WATCHMAN_DO_EVIDENCE_ERROR", raising=False)

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence["required_env"] == "WATCHMAN_LIVE_DO_SPEC"


def test_deployment_drift_preserves_collection_failure(monkeypatch):
    monkeypatch.delenv("WATCHMAN_LIVE_DO_SPEC", raising=False)
    monkeypatch.setenv("WATCHMAN_DO_EVIDENCE_ERROR", "missing DIGITALOCEAN_READ_TOKEN")

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence == {
        "required_env": "WATCHMAN_LIVE_DO_SPEC",
        "collection_error": "missing DIGITALOCEAN_READ_TOKEN",
    }
    assert "DIGITALOCEAN_READ_TOKEN" in result.summary


@patch("shopman.shop.watchman_infrastructure.subprocess.run")
def test_deployment_drift_uses_existing_read_only_checker(run, monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHMAN_LIVE_DO_SPEC", str(tmp_path / "live.yaml"))
    monkeypatch.delenv("WATCHMAN_VERSIONED_DO_SPEC", raising=False)
    run.return_value = Mock(returncode=0, stdout="drift limpo", stderr="")

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.PASS
    command = run.call_args.args[0]
    assert "scripts/check_do_spec_drift.py" in command
    assert command[command.index("--spec") + 1] == ".do/app.alpha-subdomains.yaml"
    assert "--live-spec" in command
