"""The deployed Shopman probes and the reusable Watchman registry stay aligned."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from shopman.watchman.contracts import Status
from shopman.watchman.registry import build_registry
from shopman.watchman.runner import run_profile


def test_shopman_profiles_describe_the_three_deployed_probe_contracts():
    registry = build_registry()

    assert [check.id for check in registry.for_profile("liveness")] == ["process", "pool"]
    assert [check.id for check in registry.for_profile("platform_readiness")] == ["database"]
    assert [check.id for check in registry.for_profile("readiness")] == [
        "database",
        "cache",
        "migrations",
        "queue",
    ]


def test_pool_failure_is_structured_for_cli_but_redacted_from_public_probe(client):
    with patch("shopman.shop.pool_liveness.check_pool", return_value=("fail", "pool_stuck")):
        report = run_profile("liveness")
        response = client.get("/health/live/")

    pool = next(result for result in report.results if result.id == "pool")
    assert pool.status is Status.FAIL
    assert pool.evidence == {"reason": "pool_stuck"}
    assert response.status_code == 503
    assert response.json() == {"status": "error", "checks": {"process": "ok", "pool": "fail"}}
    assert "pool_stuck" not in response.content.decode()


def test_management_command_lists_the_same_profiles_as_runtime():
    stdout = StringIO()

    call_command("watchman", "list", "--format", "json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["profiles"]["liveness"] == ["process", "pool"]
    assert payload["profiles"]["platform_readiness"] == ["database"]
    assert payload["profiles"]["readiness"] == ["database", "cache", "migrations", "queue"]


def test_unknown_observer_result_does_not_restart_the_process(client):
    with patch("shopman.shop.pool_liveness.check_pool", side_effect=RuntimeError("observer broke")):
        report = run_profile("liveness")
        response = client.get("/health/live/")

    pool = next(result for result in report.results if result.id == "pool")
    assert pool.status is Status.UNKNOWN
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"process": "ok"}}
    assert "observer broke" not in response.content.decode()
