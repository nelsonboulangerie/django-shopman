from datetime import datetime

import pytest

from shopman.watchman.contracts import CheckResult, Status


def test_result_requires_timezone_aware_observation():
    with pytest.raises(ValueError, match="timezone-aware"):
        CheckResult(id="x", status=Status.PASS, summary="ok", observed_at=datetime.now())


def test_result_rejects_non_json_evidence():
    with pytest.raises(ValueError, match="JSON-serializable"):
        CheckResult(id="x", status=Status.PASS, summary="ok", evidence={"bad": object()})


def test_public_dict_can_omit_evidence():
    result = CheckResult(id="x", status=Status.PASS, summary="ok", evidence={"secret": "value"})

    payload = result.to_dict(include_evidence=False)

    assert "evidence" not in payload
    assert "remediation" not in payload
