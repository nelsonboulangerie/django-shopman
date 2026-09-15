"""Real authentication boundaries; all accounts and codes are synthetic fixtures."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.admin import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, override_settings
from django.urls import NoReverseMatch, reverse
from django_otp import verify_token
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from shopman.backstage.middleware_2fa import AdminTwoFactorMiddleware
from shopman.backstage.services.admin_two_factor import RECOVERY_NAME, authorize_enrollment

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    from shopman.shop.models import Shop
    Shop.objects.create(name='Loja teste 2FA')
    return get_user_model().objects.create_user('enroll-admin', password='local-fixture-password', is_staff=True)


def current(device):
    return str(totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)).zfill(device.digits)


def begin(client, staff):
    device = authorize_enrollment(staff)
    client.force_login(staff)
    url = reverse('admin_2fa_enroll')
    before = client.get(url)
    assert b'data:image' not in before.content
    assert client.post(url, {'password': 'local-fixture-password'}).status_code == 302
    qr = client.get(url)
    assert b'data:image/png;base64,' in qr.content
    assert 'no-store' in qr['Cache-Control']
    response = client.post(url, {'token': current(device)})
    codes = response.context['codes']
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(len(code) == 16 for code in codes)
    assert not TOTPDevice.objects.get(pk=device.pk).confirmed
    assert all(code.encode() not in client.get(url).content for code in codes)
    return device, codes


def test_enrollment_requires_password_totp_and_recovery_proof(client, staff):
    device, codes = begin(client, staff)
    with pytest.raises(CommandError):
        call_command('check_admin_2fa_ready', stdout=StringIO())
    response = client.post(reverse('admin_2fa_enroll'), {'token': codes[0]})
    assert response.status_code == 200
    device.refresh_from_db()
    assert device.confirmed
    recovery = StaticDevice.objects.get(user=staff, confirmed=True, name=RECOVERY_NAME)
    assert recovery.token_set.count() == 9
    assert not recovery.token_set.filter(token=codes[0]).exists()
    call_command('check_admin_2fa_ready', stdout=StringIO())
    assert not site.is_registered(StaticDevice)


def test_recovery_is_single_use_and_can_replace_lost_authenticator(client, staff):
    device, codes = begin(client, staff)
    client.post(reverse('admin_2fa_enroll'), {'token': codes[0]})
    client.logout()
    client.force_login(staff)
    recovery = StaticDevice.objects.get(user=staff, confirmed=True)
    response = client.post(reverse('admin_2fa_verify'), {'device': recovery.persistent_id, 'token': codes[1]})
    assert response.status_code == 302
    assert verify_token(staff, recovery.persistent_id, codes[1]) is None
    pending = authorize_enrollment(staff, replace=True)
    assert TOTPDevice.objects.filter(pk=device.pk, confirmed=True).exists()
    assert client.get(reverse('admin_2fa_enroll')).status_code == 200
    client.post(reverse('admin_2fa_enroll'), {'password': 'local-fixture-password'})
    response = client.post(reverse('admin_2fa_enroll'), {'token': current(pending)})
    new_codes = response.context['codes']
    assert TOTPDevice.objects.filter(pk=device.pk, confirmed=True).exists()
    client.post(reverse('admin_2fa_enroll'), {'token': new_codes[0]})
    assert not TOTPDevice.objects.filter(pk=device.pk).exists()
    assert not StaticDevice.objects.filter(pk=recovery.pk).exists()


def test_password_session_cannot_replace_existing_factor(client, staff):
    TOTPDevice.objects.create(user=staff, confirmed=True)
    authorize_enrollment(staff, replace=True)
    client.force_login(staff)
    response = client.post(reverse('admin_2fa_enroll'), {'password': 'local-fixture-password'})
    assert response.status_code == 302 and reverse('admin_2fa_verify') in response['Location']
    assert 'admin_2fa_enrollment' not in client.session


def test_enrollment_csrf_and_non_staff_denied(staff):
    authorize_enrollment(staff)
    client = Client(enforce_csrf_checks=True)
    client.force_login(staff)
    assert client.post(reverse('admin_2fa_enroll'), {'password': 'local-fixture-password'}).status_code == 403
    staff.is_staff = False
    staff.save()
    assert client.get(reverse('admin_2fa_enroll')).status_code == 302
    with pytest.raises(ValueError):
        authorize_enrollment(staff)


def test_totp_replay_and_throttle(staff):
    device = TOTPDevice.objects.create(user=staff, confirmed=True)
    code = current(device)
    assert verify_token(staff, device.persistent_id, code)
    assert verify_token(staff, device.persistent_id, code) is None
    device.refresh_from_db()
    assert device.throttling_failure_count == 1
    assert not device.verify_is_allowed()[0]


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
def test_gate_exact_exemptions_and_missing_dependency_fail_closed(staff):
    factory = RequestFactory()
    request = factory.get('/admin/login-extra/')
    request.user = staff  # No OTPMiddleware: must remain blocked.
    assert AdminTwoFactorMiddleware._needs_verification(request)
    request = factory.get('/api/v1/backstage/pos/')
    request.user = staff
    assert not AdminTwoFactorMiddleware._needs_verification(request)
    request = factory.get('/admin/')
    request.user = staff
    middleware = AdminTwoFactorMiddleware(lambda req: None)
    with patch('shopman.backstage.middleware_2fa.reverse', side_effect=NoReverseMatch):
        assert middleware(request).status_code == 503


@pytest.mark.django_db(transaction=True)
def test_simultaneous_recovery_consumption_has_one_winner(staff):
    if connection.vendor != 'postgresql':
        pytest.skip('Row locking requires PostgreSQL')
    device = StaticDevice.objects.create(user=staff, confirmed=True, name=RECOVERY_NAME)
    StaticToken.objects.create(device=device, token='synthetic-code12')
    def attempt(_):
        close_old_connections()
        try:
            return bool(verify_token(get_user_model().objects.get(pk=staff.pk), device.persistent_id, 'synthetic-code12'))
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, range(2))) == 1


def test_individual_enrollment_enforces_admin_only_with_global_flag_off(client, staff):
    _, codes = begin(client, staff)
    client.post(reverse('admin_2fa_enroll'), {'token': codes[0]})
    client.logout()
    client.force_login(staff)
    response = client.get('/admin/')
    assert response.status_code == 302 and reverse('admin_2fa_verify') in response['Location']
    request = RequestFactory().get('/api/v1/backstage/pos/')
    request.user = staff
    assert not AdminTwoFactorMiddleware._needs_verification(request)
    other = get_user_model().objects.create_user('other-staff', is_staff=True)
    request = RequestFactory().get('/admin/')
    request.user = other
    assert not AdminTwoFactorMiddleware._needs_verification(request)


@pytest.mark.parametrize('target', ['https://evil.example/', '/admin/../outside/', '/admin/%2e%2e/outside/',
                                   '/admin/\\evil', 'http://[invalid'])
def test_next_is_strictly_local_admin(target):
    from shopman.backstage.views.two_factor import _safe_next
    request = RequestFactory().get('/admin/2fa/verify/', {'next': target})
    assert _safe_next(request) == '/admin/'


@override_settings(SHOPMAN_ADMIN_REQUIRE_2FA=True)
def test_missing_shop_does_not_loop_authentication(client, staff):
    from shopman.shop.models import Shop
    Shop.objects.all().delete()
    client.force_login(staff)
    assert client.get('/admin/2fa/verify/').status_code == 200


def test_exhaustion_or_removal_of_recovery_never_disables_policy(client, staff):
    from shopman.backstage.models import AdminTwoFactorEnrollment
    _, codes = begin(client, staff)
    client.post(reverse('admin_2fa_enroll'), {'token': codes[0]})
    recovery = StaticDevice.objects.get(user=staff, confirmed=True)
    for code in codes[1:]:
        assert verify_token(staff, recovery.persistent_id, code)
    assert recovery.token_set.count() == 0
    assert AdminTwoFactorEnrollment.objects.filter(user=staff).exists()
    client.logout()
    client.force_login(staff)
    assert reverse('admin_2fa_verify') in client.get('/admin/')['Location']
    recovery.delete()
    TOTPDevice.objects.filter(user=staff).delete()
    blocked = client.get(reverse('admin_2fa_verify'))
    assert 'recuperação supervisionada' in blocked.content.decode()
    assert blocked.context['enroll_url'] is None
    assert reverse('admin_2fa_verify') in client.get('/admin/')['Location']
    authorize_enrollment(staff, replace=True)
    assert reverse('admin_2fa_verify') in client.get(reverse('admin_2fa_enroll'))['Location']


def test_enrollment_password_throttle_and_expiration(client, staff):
    device = authorize_enrollment(staff)
    client.force_login(staff)
    url = reverse('admin_2fa_enroll')
    response = client.post(url, {'password': 'incorrect-fixture-password'})
    assert response.status_code == 200
    assert response.wsgi_request.sensitive_post_parameters == '__ALL__'
    assert b'data:image' not in response.content
    device.refresh_from_db()
    assert device.throttling_failure_count == 1
    assert client.post(url, {'password': 'local-fixture-password'}).status_code == 200
    assert 'admin_2fa_enrollment' not in client.session
    device.throttle_reset()
    client.post(url, {'password': 'local-fixture-password'})
    session = client.session
    session['admin_2fa_enrollment']['until'] = 0
    session.save()
    assert b'data:image' not in client.get(url).content
