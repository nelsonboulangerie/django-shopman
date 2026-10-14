from datetime import UTC, datetime

from django.test import override_settings

from shopman.watchman.contracts import CheckResult, Status
from shopman.watchman.runner import Report, run_profile


def _settings(check: str, check_id: str):
    return {
        "CHECKS": [check],
        "PROFILES": {"diagnostic": [check_id], "liveness": [check_id]},
    }


@override_settings(
    WATCHMAN=_settings("shopman.watchman.tests.fixtures.ErrorCheck", "error")
)
def test_check_exception_becomes_unknown_without_escaping():
    report = run_profile("diagnostic")

    assert report.status is Status.UNKNOWN
    assert report.exit_code == 1
    assert report.results[0].summary == "check raised RuntimeError"
    assert "secret exception detail" not in report.results[0].summary


@override_settings(
    WATCHMAN=_settings("shopman.watchman.tests.fixtures.SlowCheck", "slow")
)
def test_declared_deadline_overrun_is_reported_as_unknown():
    report = run_profile("diagnostic")

    assert report.results[0].status is Status.UNKNOWN
    assert report.results[0].summary == "check exceeded its declared deadline"


@override_settings(
    WATCHMAN=_settings("shopman.watchman.tests.fixtures.WrongIdCheck", "expected")
)
def test_wrong_result_id_becomes_unknown():
    report = run_profile("diagnostic")

    assert report.results[0].status is Status.UNKNOWN


def test_report_status_is_deterministic_for_pass_and_skipped_results():
    report = Report(
        profile="diagnostic",
        results=(
            CheckResult(id="skipped", status=Status.SKIPPED, summary="not applicable"),
            CheckResult(id="pass", status=Status.PASS, summary="healthy"),
        ),
        started_at=datetime.now(UTC),
        duration_ms=1.0,
    )

    assert report.status is Status.PASS


def test_report_with_only_skipped_results_is_skipped():
    report = Report(
        profile="diagnostic",
        results=(CheckResult(id="skipped", status=Status.SKIPPED, summary="not applicable"),),
        started_at=datetime.now(UTC),
        duration_ms=1.0,
    )

    assert report.status is Status.SKIPPED
