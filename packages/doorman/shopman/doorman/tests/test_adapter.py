"""
Tests for DefaultAuthAdapter and adapter customization (AUTH-2).

Tests:
- Default adapter delegates to IdentityResolver
- Default adapter delegates to MessageSender
- Custom adapter overrides work
- create_and_send works for email/whatsapp/api channels
- get_adapter() returns singleton
- Adapter hooks are called
"""

import logging
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.doorman.adapter import DefaultAuthAdapter
from shopman.doorman.conf import get_adapter, reset_adapter
from shopman.doorman.protocols.identity import IdentityHandle, IdentityView
from shopman.doorman.services.access_link import AccessLinkService
from shopman.guestman.models import ContactPoint, Customer

# ===========================================
# Default adapter delegates correctly
# ===========================================


@pytest.mark.django_db
def _view(subject_id, *, name="Test", phone=None, email=None, active=True):
    handles = []
    if phone:
        handles.append(IdentityHandle("phone", phone, True, True))
    if email:
        handles.append(IdentityHandle("email", email, True, True))
    return IdentityView(subject_id, name, tuple(handles), active)


def test_default_adapter_resolve_by_phone(customer):
    adapter = DefaultAuthAdapter()
    info = adapter.resolve_identity("phone", f"+{customer.phone}")

    assert info is not None
    assert info.subject_id == customer.uuid


@pytest.mark.django_db
def test_default_adapter_resolve_by_email(customer):
    adapter = DefaultAuthAdapter()
    info = adapter.resolve_identity("email", customer.email)

    assert info is not None
    assert info.subject_id == customer.uuid


@pytest.mark.django_db
def test_default_adapter_resolve_by_uuid(customer):
    adapter = DefaultAuthAdapter()
    info = adapter.identity(customer.uuid)

    assert info is not None
    assert info.subject_id == customer.uuid


@pytest.mark.django_db
def test_default_adapter_resolve_unknown_phone():
    adapter = DefaultAuthAdapter()
    assert adapter.resolve_identity("phone", "+5500000000000") is None


@pytest.mark.django_db
def test_default_adapter_create_customer():
    adapter = DefaultAuthAdapter()
    info = adapter.create_identity(adapter.login_handle("+5541777777777"))

    assert info is not None
    assert (info.handle("phone") or info.handle("whatsapp")).value == "+5541777777777"


@pytest.mark.django_db
def test_default_adapter_create_customer_creates_canonical_phone_contact_point():
    adapter = DefaultAuthAdapter()
    info = adapter.create_identity(adapter.login_handle("+5541777777777"))

    customer = Customer.objects.get(uuid=info.subject_id)
    assert ContactPoint.objects.filter(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized="+5541777777777",
        is_primary=True,
    ).exists()


@pytest.mark.django_db
def test_default_adapter_create_customer_for_email():
    adapter = DefaultAuthAdapter()
    info = adapter.create_identity(adapter.login_handle("person@example.com"))

    assert info is not None
    assert info.handle("email").value == "person@example.com"


@pytest.mark.django_db
def test_default_adapter_resolve_phone_via_contact_point():
    customer = Customer.objects.create(
        ref="AUTH-CONTACT-1",
        first_name="Phone",
    )
    ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized="+554188887777",
        is_primary=True,
        is_verified=True,
    )

    adapter = DefaultAuthAdapter()
    info = adapter.resolve_identity("phone", "+554188887777")

    assert info is not None
    assert info.subject_id == customer.uuid
    assert info.handle("whatsapp").value == "+554188887777"


def test_default_adapter_send_code():
    adapter = DefaultAuthAdapter()
    # Default sender is LogSender from test settings
    result = adapter.send_code("+5541999999999", "123456", "whatsapp")
    assert result is True


def test_delivery_chain_exception_does_not_log_handle_or_code(caplog):
    target = "+5543999990197"
    code = "918273"

    class ExplodingSender:
        def send_code(self, sent_target, sent_code, method):
            raise RuntimeError(f"provider rejected {sent_target} with code {sent_code}")

    adapter = DefaultAuthAdapter()
    logger = logging.getLogger("shopman.doorman.adapter")
    logger.addHandler(caplog.handler)
    try:
        with (
            patch.object(adapter, "get_delivery_chain", return_value=["sms"]),
            patch.object(adapter, "_get_chain_sender", return_value=ExplodingSender()),
        ):
            result = adapter.send_code_with_fallback(target, code)
    finally:
        logger.removeHandler(caplog.handler)

    assert result == (False, "sms")
    assert caplog.text
    assert target not in caplog.text
    assert code not in caplog.text


def test_default_adapter_builds_normalized_phone_login_handle():
    adapter = DefaultAuthAdapter()
    assert adapter.login_handle("41999999999").value == "+5541999999999"


def test_default_adapter_normalizes_email_handle():
    adapter = DefaultAuthAdapter()
    assert adapter.login_handle(" User@Example.COM ").value == "user@example.com"


def test_default_adapter_should_auto_create():
    adapter = DefaultAuthAdapter()
    assert adapter.should_auto_create_customer() is True


@override_settings(DOORMAN={"AUTO_CREATE_CUSTOMER": False})
def test_default_adapter_should_not_auto_create():
    adapter = DefaultAuthAdapter()
    assert adapter.should_auto_create_customer() is False


def test_default_adapter_is_login_allowed():
    adapter = DefaultAuthAdapter()
    assert adapter.is_login_allowed("+5541999999999", "whatsapp") is True


def test_default_adapter_redirect_urls():
    adapter = DefaultAuthAdapter()
    assert adapter.get_login_redirect_url(None, None) == "/"
    assert adapter.get_logout_redirect_url(None) == "/"


# ===========================================
# Custom adapter override
# ===========================================


class CustomAdapter(DefaultAuthAdapter):
    """Test adapter with custom behavior."""

    def should_auto_create_customer(self) -> bool:
        return False

    def is_login_allowed(self, target, method) -> bool:
        return target != "+5500000000000"

    def on_customer_authenticated(self, request, customer, user, method):
        # Side effect for testing
        request._custom_hook_called = True

    def get_login_redirect_url(self, request, customer):
        return "/custom-login-redirect/"


CUSTOM_ADAPTER_PATH = f"{CustomAdapter.__module__}.CustomAdapter"


@override_settings(DOORMAN={"AUTH_ADAPTER": CUSTOM_ADAPTER_PATH})
def test_custom_adapter_loaded():
    reset_adapter()
    adapter = get_adapter()
    assert isinstance(adapter, CustomAdapter)
    assert adapter.should_auto_create_customer() is False


@override_settings(DOORMAN={"AUTH_ADAPTER": CUSTOM_ADAPTER_PATH})
def test_custom_adapter_login_allowed():
    reset_adapter()
    adapter = get_adapter()
    assert adapter.is_login_allowed("+5541999999999", "whatsapp") is True
    assert adapter.is_login_allowed("+5500000000000", "whatsapp") is False


@override_settings(DOORMAN={"AUTH_ADAPTER": CUSTOM_ADAPTER_PATH})
def test_custom_adapter_redirect_url():
    reset_adapter()
    adapter = get_adapter()
    assert adapter.get_login_redirect_url(None, None) == "/custom-login-redirect/"


# ===========================================
# get_adapter() singleton
# ===========================================


def test_get_adapter_returns_singleton():
    reset_adapter()
    a1 = get_adapter()
    a2 = get_adapter()
    assert a1 is a2


def test_get_adapter_default_is_default_adapter():
    reset_adapter()
    adapter = get_adapter()
    assert isinstance(adapter, DefaultAuthAdapter)


# ===========================================
# send_access_link via adapter
# ===========================================


def test_send_access_link_email_channel():
    adapter = DefaultAuthAdapter()
    customer = _view(uuid.uuid4(), phone="+5541999999999", email="test@example.com")
    with patch.object(adapter, "_send_access_link_email", return_value=True) as mock:
        result = adapter.send_access_link("email", customer, "https://example.com/link")

    assert result is True
    mock.assert_called_once_with(customer, "https://example.com/link")


def test_adapter_access_link_email_exception_redacts_pii(caplog):
    email = "private@example.com"
    url = "https://example.com/a?t=secret-token"
    adapter = DefaultAuthAdapter()
    customer = _view(uuid.uuid4(), email=email)
    logger = logging.getLogger("shopman.doorman.adapter")
    logger.addHandler(caplog.handler)
    try:
        with patch(
            "django.template.loader.render_to_string",
            side_effect=RuntimeError(f"template rejected {email} at {url}"),
        ):
            result = adapter._send_access_link_email(customer, url)
    finally:
        logger.removeHandler(caplog.handler)

    assert result is False
    assert caplog.text
    assert email not in caplog.text
    assert url not in caplog.text


def test_send_access_link_api_channel():
    adapter = DefaultAuthAdapter()
    customer = _view(uuid.uuid4(), phone="+5541999999999")
    # API channel returns True without sending
    result = adapter.send_access_link("api", customer, "https://example.com/link")
    assert result is True


def test_send_access_link_whatsapp_channel():
    adapter = DefaultAuthAdapter()
    customer = _view(uuid.uuid4(), phone="+5541999999999")
    # LogSender always returns True (from test settings)
    result = adapter.send_access_link("whatsapp", customer, "https://example.com/link")
    assert result is True


# ===========================================
# create_and_send (unified)
# ===========================================


@pytest.mark.django_db
def test_create_and_send_email(customer):
    info = _view(customer.uuid, name=customer.first_name, phone=f"+{customer.phone}", email=customer.email)
    with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_access_link", return_value=True):
        with patch.object(AccessLinkService, "_build_url", return_value="https://test.local/link"):
            result = AccessLinkService.create_and_send(info, channel="email")

    assert result.success


@pytest.mark.django_db
def test_create_and_send_api(customer):
    info = _view(customer.uuid, name=customer.first_name, phone=f"+{customer.phone}")
    with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_access_link", return_value=True):
        with patch.object(AccessLinkService, "_build_url", return_value="https://test.local/link"):
            result = AccessLinkService.create_and_send(info, channel="api")

    assert result.success


@pytest.mark.django_db
def test_create_and_send_failure(customer):
    info = _view(customer.uuid, name=customer.first_name, phone=f"+{customer.phone}")
    with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_access_link", return_value=False):
        with patch.object(AccessLinkService, "_build_url", return_value="https://test.local/link"):
            result = AccessLinkService.create_and_send(info, channel="whatsapp")

    assert not result.success
    assert "Failed" in result.error


# ===========================================
# Adapter hooks
# ===========================================


def test_adapter_hooks_are_noop_by_default():
    adapter = DefaultAuthAdapter()
    # These should not raise
    adapter.on_customer_authenticated(None, None, None, "test")
    adapter.on_device_trusted(None, None, None)
    adapter.on_login_failed(None, "+5541999999999", "test")
