from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from shopman.doorman.models import AccessLink, TrustedDevice, VerificationCode


@pytest.mark.parametrize("days", (0, -1, 1, 6, 8, 30, 90, 91))
def test_auth_cleanup_rejects_unsafe_retention_window_without_calling_services(days: int) -> None:
    with (
        patch("shopman.doorman.services.access_link.AccessLinkService.cleanup_expired_tokens") as links,
        patch("shopman.doorman.services.verification.AuthService.cleanup_expired_codes") as codes,
        patch("shopman.doorman.services.device_trust.DeviceTrustService.cleanup") as devices,
        pytest.raises(CommandError, match="nenhum dado foi alterado"),
    ):
        call_command("auth_cleanup", days=days, stdout=StringIO())

    links.assert_not_called()
    codes.assert_not_called()
    devices.assert_not_called()


def test_auth_cleanup_dry_run_uses_the_exact_seven_day_boundary(db) -> None:
    fixed_now = timezone.now()
    for index, delta_seconds in enumerate((-1, 0, 1)):
        expires_at = fixed_now - timedelta(days=7) + timedelta(seconds=delta_seconds)
        AccessLink.objects.create(
            token_hash=f"{index:064x}",
            customer_id=uuid.uuid4(),
            expires_at=expires_at,
        )
        VerificationCode.objects.create(
            code_hash=f"{index + 10:064x}",
            target_value=f"qa-{index}@example.test",
            expires_at=expires_at,
        )
        TrustedDevice.objects.create(
            subject_id=f"qa-{index}",
            token_hash=f"{index + 20:064x}",
            expires_at=expires_at,
        )

    output = StringIO()
    with patch("django.utils.timezone.now", return_value=fixed_now):
        call_command("auth_cleanup", dry_run=True, stdout=output)

    rendered = output.getvalue()
    assert "links_de_acesso=1" in rendered
    assert "codigos_de_verificacao=1" in rendered
    assert "aparelhos_confiaveis=1" in rendered


def test_auth_cleanup_dry_run_is_non_mutating_and_uses_pt_br_output(db) -> None:
    output = StringIO()
    with (
        patch("shopman.doorman.services.access_link.AccessLinkService.cleanup_expired_tokens") as links,
        patch("shopman.doorman.services.verification.AuthService.cleanup_expired_codes") as codes,
        patch("shopman.doorman.services.device_trust.DeviceTrustService.cleanup") as devices,
    ):
        call_command("auth_cleanup", dry_run=True, stdout=output)

    rendered = output.getvalue()
    assert "DRY-RUN" in rendered
    assert "nenhuma alteração" in rendered
    assert "links_de_acesso=0" in rendered
    links.assert_not_called()
    codes.assert_not_called()
    devices.assert_not_called()


def test_auth_cleanup_isolates_a_failure_and_finishes_the_other_steps(caplog) -> None:
    output = StringIO()
    with (
        patch(
            "shopman.doorman.services.access_link.AccessLinkService.cleanup_expired_tokens",
            side_effect=RuntimeError("segredo que não pode ir para a saída"),
        ) as links,
        patch(
            "shopman.doorman.services.verification.AuthService.cleanup_expired_codes",
            return_value=2,
        ) as codes,
        patch(
            "shopman.doorman.services.device_trust.DeviceTrustService.cleanup",
            return_value=3,
        ) as devices,
        pytest.raises(CommandError) as caught,
    ):
        call_command("auth_cleanup", days=7, stdout=output)

    links.assert_called_once_with(days=7)
    codes.assert_called_once_with(days=7)
    devices.assert_called_once_with(days=7)
    assert "links_de_acesso" in str(caught.value)
    assert "segredo" not in str(caught.value)
    assert "segredo" not in caplog.text
    assert "codigos_de_verificacao=2" in output.getvalue()
    assert "aparelhos_confiaveis=3" in output.getvalue()
