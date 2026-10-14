import pytest
from django.test import override_settings

from shopman.watchman.exceptions import WatchmanConfigurationError
from shopman.watchman.registry import build_registry


@override_settings(
    WATCHMAN={
        "CHECKS": [
            "shopman.watchman.checks.ProcessCheck",
            "shopman.watchman.checks.ProcessCheck",
        ],
        "PROFILES": {"liveness": ["process"]},
    }
)
def test_duplicate_check_ids_are_rejected():
    with pytest.raises(WatchmanConfigurationError, match="duplicate"):
        build_registry()


@override_settings(
    WATCHMAN={
        "CHECKS": ["shopman.watchman.checks.ProcessCheck"],
        "PROFILES": {"liveness": ["missing"]},
    }
)
def test_profile_cannot_reference_an_unknown_check():
    with pytest.raises(WatchmanConfigurationError, match="unknown checks"):
        build_registry()


def test_default_registry_has_process_check():
    registry = build_registry()

    assert registry.by_id("process").id == "process"
    assert [check.id for check in registry.for_profile("liveness")] == ["process"]
