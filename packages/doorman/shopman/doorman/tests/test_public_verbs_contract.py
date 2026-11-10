"""Contrato dos verbos públicos do Doorman: verificação (OTP), link de acesso e
dispositivo confiável.

Cada verbo é provado pelo que ele promete ao chamador e pelo que ele NÃO toca:
o OTP não cunha nem consome ``AccessLink`` para logar (o atalho que o laudo de
18/04 apontou), o link de acesso não mexe em ``VerificationCode``, e a falha da
ligação identidade verificada → cliente sobe ao chamador em vez de virar
sucesso parcial. A ligação mora no porto de identidade
(``IdentityResolverProtocol.bind_verified_handle``), implementado pelo host;
o kernel não importa o Guestman (trava em
``shopman/shop/tests/test_import_boundaries.py``).
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory
from shopman.doorman import get_access_link_service, get_auth_service
from shopman.doorman.adapter import DefaultAuthAdapter
from shopman.doorman.conf import get_adapter
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.models import AccessLink, CustomerUser, TrustedDevice, VerificationCode
from shopman.doorman.services import AccessLinkService, AuthService, DeviceTrustService

pytestmark = pytest.mark.django_db

OTP_BACKEND = "shopman.doorman.backends.PhoneOTPBackend"
LINK_BACKEND = "django.contrib.auth.backends.ModelBackend"


class _CapturingSender:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send_code(self, target, code, method):
        self.sent.append((target, code, method))
        return True


def _request_with_session(cookies: dict | None = None):
    request = RequestFactory().post("/")
    request.session = SessionStore()
    request.session.create()
    for name, value in (cookies or {}).items():
        request.COOKIES[name] = value
    return request


def _request_and_capture_code(phone: str) -> str:
    sender = _CapturingSender()
    result = AuthService.request_code(phone, sender=sender)
    assert result.success, result.error
    assert len(sender.sent) == 1
    return sender.sent[0][1]


def test_public_entrypoints_name_the_three_services():
    assert get_auth_service() is AuthService
    assert get_access_link_service() is AccessLinkService
    from shopman.doorman import services

    assert set(services.__all__) == {"AccessLinkService", "AuthService", "DeviceTrustService"}


# ---------------------------------------------------------------------------
# Verificação (OTP)
# ---------------------------------------------------------------------------


def test_otp_login_is_self_contained_and_never_uses_access_link():
    phone = "+5543999990201"
    raw_code = _request_and_capture_code(phone)
    request = _request_with_session()

    result = AuthService.verify_for_login(phone, raw_code, request)

    assert result.success, result.error
    assert result.created_customer is True
    code = VerificationCode.objects.get(target_value=phone)
    assert code.status == VerificationCode.Status.VERIFIED
    assert str(code.customer_id) == str(result.customer.subject_id)
    assert request.session[BACKEND_SESSION_KEY] == OTP_BACKEND
    link = CustomerUser.objects.get(customer_id=result.customer.subject_id)
    assert str(request.session[SESSION_KEY]) == str(link.user_id)
    assert not AccessLink.objects.exists()


def test_otp_wrong_code_counts_attempt_and_does_not_login():
    phone = "+5543999990202"
    raw_code = _request_and_capture_code(phone)
    wrong = "000000" if raw_code != "000000" else "111111"
    request = _request_with_session()

    result = AuthService.verify_for_login(phone, wrong, request)

    assert result.success is False
    assert result.error_code == ErrorCode.CODE_INVALID
    assert SESSION_KEY not in request.session
    assert VerificationCode.objects.get(target_value=phone).attempts == 1


def test_bind_conflict_is_reported_not_swallowed(monkeypatch):
    phone = "+5543999990203"
    raw_code = _request_and_capture_code(phone)

    def conflict(_adapter, identity, handle, *, proof):
        from shopman.doorman.protocols.identity import IdentityConflict

        raise IdentityConflict("verified_handle_conflict")

    monkeypatch.setattr(DefaultAuthAdapter, "bind_verified_handle", conflict)
    request = _request_with_session()

    result = AuthService.verify_for_login(phone, raw_code, request)

    assert result.success is False
    assert result.error_code == ErrorCode.IDENTITY_CONFLICT
    assert VerificationCode.objects.get(target_value=phone).status == VerificationCode.Status.SENT
    assert SESSION_KEY not in request.session
    assert not CustomerUser.objects.exists()


def test_unexpected_bind_failure_propagates_and_leaves_no_partial_login(monkeypatch):
    """Caracterização: falha que não é conflito de titularidade sobe ao chamador.

    Era o defeito do antigo ``_link_verified_identifier``: a ligação falhava, o
    ``except`` engolia e o login seguia como sucesso. Hoje a exceção atravessa o
    ``verify_for_login`` (atômico), o código continua não consumido e nenhuma
    sessão nasce.
    """
    phone = "+5543999990204"
    raw_code = _request_and_capture_code(phone)

    def broken(_adapter, identity, handle, *, proof):
        raise RuntimeError("identity store unavailable")

    monkeypatch.setattr(DefaultAuthAdapter, "bind_verified_handle", broken)
    request = _request_with_session()

    with pytest.raises(RuntimeError, match="identity store unavailable"):
        AuthService.verify_for_login(phone, raw_code, request)

    assert VerificationCode.objects.get(target_value=phone).status == VerificationCode.Status.SENT
    assert SESSION_KEY not in request.session
    assert not CustomerUser.objects.exists()


# ---------------------------------------------------------------------------
# Link de acesso
# ---------------------------------------------------------------------------


def test_access_link_exchange_logs_in_without_touching_verification_codes(customer):
    identity = get_adapter().identity(customer.uuid, purpose="session")
    created = AccessLinkService.create_token(identity)
    assert created.success, created.error
    request = _request_with_session()

    result = AccessLinkService.exchange(created.token, request)

    assert result.success, result.error
    assert str(result.customer.subject_id) == str(customer.uuid)
    assert request.session[BACKEND_SESSION_KEY] == LINK_BACKEND
    assert AccessLink.objects.get(customer_id=customer.uuid).used_at is not None
    assert not VerificationCode.objects.exists()


def test_access_link_unknown_token_is_invalid_not_expired():
    request = _request_with_session()

    result = AccessLinkService.exchange("token-que-nao-existe", request)

    assert result.success is False
    assert result.error_code == ErrorCode.TOKEN_INVALID
    assert SESSION_KEY not in request.session


# ---------------------------------------------------------------------------
# Dispositivo confiável
# ---------------------------------------------------------------------------


def test_device_trust_round_trip_is_bound_to_its_subject():
    subject = uuid.uuid4()
    response = HttpResponse()

    device = DeviceTrustService.trust(response, "customer", subject, _request_with_session())

    assert device is not None
    cookie_name = DeviceTrustService.cookie_name_for("customer", subject)
    raw_token = response.cookies[cookie_name].value
    assert DeviceTrustService.check(_request_with_session({cookie_name: raw_token}), "customer", subject)
    other = uuid.uuid4()
    other_cookie = DeviceTrustService.cookie_name_for("customer", other)
    assert not DeviceTrustService.check(_request_with_session({other_cookie: raw_token}), "customer", other)

    assert DeviceTrustService.revoke_all(subject) == 1
    assert not DeviceTrustService.check(_request_with_session({cookie_name: raw_token}), "customer", subject)
    assert not TrustedDevice.objects.filter(subject_id=str(subject), is_active=True).exists()
