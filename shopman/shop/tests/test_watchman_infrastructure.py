from __future__ import annotations

from unittest.mock import Mock, patch

from shopman.watchman.contracts import CheckContext, Status

from shopman.shop.watchman_infrastructure import DeploymentDriftCheck, ExternalMonitoringContractCheck


def _context():
    return CheckContext(profile="infrastructure", deadline=9999999999)


def test_external_monitoring_contract_is_explicitly_skipped_without_live_credential(monkeypatch):
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    result = ExternalMonitoringContractCheck().run(_context())

    assert result.status is Status.SKIPPED
    assert result.evidence == {
        "uptime_monitors": 2,
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


def test_deployment_drift_is_explicitly_skipped_without_live_snapshot(monkeypatch):
    monkeypatch.delenv("WATCHMAN_LIVE_DO_SPEC", raising=False)

    result = DeploymentDriftCheck().run(_context())

    assert result.status is Status.SKIPPED
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
