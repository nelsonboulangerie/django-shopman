from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from shopman.doorman.models import VerificationCode


@pytest.mark.django_db
def test_data_retention_default_is_complete_non_mutating_json() -> None:
    output = StringIO()

    call_command("data_retention", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    assert payload["mode"] == "dry-run"
    assert payload["pii"] is False
    assert payload["mutations"] == 0
    assert [row["rule"] for row in payload["rules"]] == [
        f"R{index:02d}" for index in range(1, 16)
    ]
    assert all(isinstance(row["candidates"], int) for row in payload["rules"])


@pytest.mark.django_db
def test_data_retention_refuses_apply_before_separate_gate() -> None:
    with pytest.raises(CommandError, match="gate humano separado"):
        call_command("data_retention", "--apply", stdout=StringIO())


@pytest.mark.django_db
def test_data_retention_counts_expired_code_without_deleting_it() -> None:
    code = VerificationCode.objects.create(target_value="+5500000000000")
    VerificationCode.objects.filter(pk=code.pk).update(
        expires_at=timezone.now() - timedelta(days=8),
    )
    output = StringIO()

    call_command("data_retention", "--dry-run", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    r10 = next(row for row in payload["rules"] if row["rule"] == "R10")
    assert r10["counts"]["codigos_vencidos"] == 1
    assert VerificationCode.objects.filter(pk=code.pk).exists()
