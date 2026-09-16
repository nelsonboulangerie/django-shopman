"""Admin enrollment and recovery. Secrets stay in the authenticated response/DB."""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.views.decorators.debug import sensitive_variables
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from shopman.backstage.models import AdminTwoFactorEnrollment

PENDING_NAME = "admin-enrollment"
RECOVERY_NAME = "admin-recovery"
PENDING_RECOVERY = "admin-recovery-enrollment"


def lock_user(user):
    locked = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not locked.is_active or not locked.is_staff:
        raise ValueError("Conta administrativa inativa.")
    return locked


@sensitive_variables()
@transaction.atomic
def authorize_enrollment(user, replace=False):
    user = lock_user(user)
    if not user.is_active or not user.is_staff:
        raise ValueError("A inscrição exige uma conta administrativa ativa.")
    if TOTPDevice.objects.filter(user=user, confirmed=True).exists() and not replace:
        raise ValueError("Conta já inscrita. --force prepara substituição sem apagar o fator atual.")
    # Issuing a new pending enrollment never revokes a working factor or recovery.
    TOTPDevice.objects.filter(user=user, confirmed=False, name=PENDING_NAME).delete()
    StaticDevice.objects.filter(user=user, confirmed=False, name=PENDING_RECOVERY).delete()
    return TOTPDevice.objects.create(user=user, name=PENDING_NAME, confirmed=False)


@sensitive_variables()
@transaction.atomic
def check_enrollment_password(user, device_id, password):
    user = lock_user(user)
    device = TOTPDevice.objects.select_for_update().get(pk=device_id, user=user, confirmed=False, name=PENDING_NAME)
    allowed, _ = device.verify_is_allowed()
    if not allowed:
        return False
    if not user.check_password(password):
        device.throttle_increment()
        return False
    device.throttle_reset()
    return True


@sensitive_variables()
@transaction.atomic
def confirm_enrollment_token(user, device_id, token):
    user = lock_user(user)
    device = TOTPDevice.objects.select_for_update().get(pk=device_id, user=user, confirmed=False, name=PENDING_NAME)
    if not device.verify_token(token):
        return None
    StaticDevice.objects.filter(user=user, name=PENDING_RECOVERY, confirmed=False).delete()
    recovery = StaticDevice.objects.create(user=user, name=PENDING_RECOVERY, confirmed=False)
    codes = [secrets.token_urlsafe(12) for _ in range(10)]  # 96-bit, 16-character single-use tokens.
    StaticToken.objects.bulk_create([StaticToken(device=recovery, token=code) for code in codes])
    return recovery.pk, codes


@sensitive_variables()
@transaction.atomic
def finish_enrollment(user, device_id, recovery_id, code):
    user = lock_user(user)
    device = TOTPDevice.objects.select_for_update().get(pk=device_id, user=user, confirmed=False, name=PENDING_NAME)
    recovery = StaticDevice.objects.select_for_update().get(pk=recovery_id, user=user, confirmed=False, name=PENDING_RECOVERY)
    if not recovery.verify_token(code):
        return None
    AdminTwoFactorEnrollment.objects.get_or_create(user=user)
    # Both factors have been proved. Only now retire the replaced factors.
    TOTPDevice.objects.filter(user=user, confirmed=True).delete()
    StaticDevice.objects.filter(user=user, name=RECOVERY_NAME).delete()
    device.confirmed = True
    device.name = "admin"
    device.save(update_fields=["confirmed", "name"])
    recovery.confirmed = True
    recovery.name = RECOVERY_NAME
    recovery.save(update_fields=["confirmed", "name"])
    return device
