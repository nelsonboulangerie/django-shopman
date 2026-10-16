from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

from shopman.watchman.contracts import CheckContext, Status

from shopman.shop.watchman_infrastructure import DeploymentDriftCheck, ExternalMonitoringContractCheck


def _context():
    return CheckContext(profile="infrastructure", deadline=9999999999)


ROOT = Path(__file__).resolve().parents[3]


def _root_with_declared_sentry_target(tmp_path):
    payload = json.loads((ROOT / "ops/watchman/sentry.json").read_text())
    payload["notification"]["email_action"]["target_identifier"] = "user-456"
    contract = tmp_path / "ops/watchman/sentry.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_external_monitoring_contract_fails_closed_until_target_id_is_declared(monkeypatch):
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.FAIL
    assert result.evidence["recipient"] == "ti@boulangerie.com.br"
    assert result.evidence["target_declared"] is False


def test_external_monitoring_contract_is_unknown_without_live_credential(monkeypatch, tmp_path):
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("shopman.shop.watchman_infrastructure.ROOT", _root_with_declared_sentry_target(tmp_path))

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence == {
        "uptime_monitors": 2,
        "recipient": "ti@boulangerie.com.br",
        "required_env": "SENTRY_AUTH_TOKEN",
    }


@patch("shopman.shop.watchman_infrastructure._run")
def test_external_monitoring_contract_checks_live_drift_when_credential_exists(run, monkeypatch, tmp_path):
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "test-token")
    monkeypatch.setattr("shopman.shop.watchman_infrastructure.ROOT", _root_with_declared_sentry_target(tmp_path))
    run.return_value = Mock(status=Status.PASS)

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.PASS
    command = run.call_args.args[1]
    assert command[-2:] == ["scripts/watchman_sentry.py", "check"]


def test_deployment_drift_is_unknown_without_live_snapshot(monkeypatch):
    monkeypatch.delenv("WATCHMAN_LIVE_DO_SPEC", raising=False)

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.UNKNOWN
    assert result.evidence["required_env"] == "WATCHMAN_LIVE_DO_SPEC"


@patch("shopman.shop.watchman_infrastructure.subprocess.run")
def test_deployment_drift_uses_existing_read_only_checker(run, monkeypatch, tmp_path):
    monkeypatch.setenv("WATCHMAN_LIVE_DO_SPEC", str(tmp_path / "live.yaml"))
    run.return_value = Mock(returncode=0, stdout="drift limpo", stderr="")

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.PASS
    command = run.call_args.args[0]
    assert "scripts/check_do_spec_drift.py" in command
    assert "--live-spec" in command
