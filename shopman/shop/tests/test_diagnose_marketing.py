from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_diagnostic_is_one_safe_read_only_json(django_assert_max_num_queries):
    stdout = StringIO()
    with (
        django_assert_max_num_queries(8),
        patch(
            "shopman.shop.adapters.notification_manychat.send",
            side_effect=AssertionError("diagnostic must not call provider"),
        ),
    ):
        call_command("diagnose_marketing", "--json", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["schema"] == "shopman.marketing.diagnostic.v1"
    assert report["result"] == "OK"
    assert report["mode"] == "read_only"
    assert report["provider_calls"] == 0
    assert report["pii"] is False
    assert report["scope"] == {"receipt_ref": "all", "platform": "all"}
    assert report["next"] == ["observe:no_mutation_indicated"]


def test_diagnostic_rejects_an_invalid_receipt_before_querying():
    with pytest.raises(CommandError, match="UUID técnica válida"):
        call_command("diagnose_marketing", "--receipt", "not-a-uuid")
