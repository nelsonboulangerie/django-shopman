import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


def test_check_command_emits_versioned_json():
    stdout = StringIO()

    call_command("watchman", "check", "--profile", "diagnostic", "--format", "json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["schema_version"] == 1
    assert payload["status"] == "pass"
    assert payload["checks"][0]["id"] == "process"


def test_list_and_explain_are_machine_readable():
    listed = StringIO()
    explained = StringIO()

    call_command("watchman", "list", "--format", "json", stdout=listed)
    call_command("watchman", "explain", "process", "--format", "json", stdout=explained)

    assert json.loads(listed.getvalue())["profiles"]["liveness"] == ["process"]
    assert json.loads(explained.getvalue())["id"] == "process"


@override_settings(
    WATCHMAN={
        "CHECKS": ["shopman.watchman.tests.fixtures.FailCheck"],
        "PROFILES": {"diagnostic": ["failure"]},
    }
)
def test_failing_check_returns_exit_code_one():
    with pytest.raises(CommandError) as raised:
        call_command("watchman", "check", "--profile", "diagnostic")

    assert raised.value.returncode == 1


@override_settings(WATCHMAN={"CHECKS": "not-a-sequence"})
def test_invalid_configuration_returns_exit_code_two():
    with pytest.raises(CommandError) as raised:
        call_command("watchman", "list")

    assert raised.value.returncode == 2
