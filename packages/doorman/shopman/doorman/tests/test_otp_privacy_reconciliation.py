from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from shopman.doorman.models import VerificationCode
from shopman.doorman.services.verification import AuthService

pytestmark = pytest.mark.django_db


def _started_pending_code(*, expired: bool = False) -> VerificationCode:
    now = timezone.now()
    return VerificationCode.objects.create(
        target_value="+5543999990001",
        status=VerificationCode.Status.PENDING,
        delivery_started_at=now - timedelta(minutes=2),
        expires_at=now - timedelta(minutes=1) if expired else now + timedelta(minutes=5),
    )


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    (
        ("accepted", VerificationCode.Status.SENT),
        ("rejected", VerificationCode.Status.FAILED),
    ),
)
def test_reconcile_started_delivery_records_evidence_and_releases_pending_fence(
    outcome,
    expected_status,
):
    code = _started_pending_code(expired=True)

    call_command(
        "reconcile_otp_delivery_privacy",
        code_id=str(code.pk),
        outcome=outcome,
        evidence_ref="provider-ticket/OTP-2026-001",
        stdout=StringIO(),
    )

    code.refresh_from_db()
    assert code.status == expected_status
    assert code.delivery_reconciled_at is not None
    assert code.delivery_evidence_ref == "provider-ticket/OTP-2026-001"
    assert code.is_valid is False


def test_reconcile_refuses_prepared_but_never_started_delivery():
    code = VerificationCode.objects.create(target_value="+5543999990002")

    with pytest.raises(CommandError, match="não está pendente"):
        call_command(
            "reconcile_otp_delivery_privacy",
            code_id=str(code.pk),
            outcome="rejected",
            evidence_ref="provider-ticket/OTP-2026-002",
        )


def test_reconcile_refuses_evidence_that_may_contain_personal_text():
    code = _started_pending_code()

    with pytest.raises(CommandError, match="sem dados pessoais"):
        call_command(
            "reconcile_otp_delivery_privacy",
            code_id=str(code.pk),
            outcome="rejected",
            evidence_ref="telefone +55 43 99999-0000",
        )


def test_cleanup_keeps_started_unknown_but_removes_never_started_expired_intent():
    started = _started_pending_code(expired=True)
    never_started = VerificationCode.objects.create(
        target_value="+5543999990003",
        status=VerificationCode.Status.PENDING,
        expires_at=timezone.now() - timedelta(days=8),
    )

    deleted = AuthService.cleanup_expired_codes(days=7)

    assert deleted == 1
    assert VerificationCode.objects.filter(pk=started.pk).exists()
    assert not VerificationCode.objects.filter(pk=never_started.pk).exists()
