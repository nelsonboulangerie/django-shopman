"""Auth test fixtures."""

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.doorman.models import AccessLink, VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.guestman.models import ContactPoint, Customer

TEST_API_KEY = "test-auth-api-key-2026"


def proven(customer: Customer) -> Customer:
    """O cliente que já provou o telefone e o e-mail (entrou por código antes).

    Contato só gravado, sem prova, não abre a conta (D4, OC-08): os fixtures que
    representam "o dono desta conta entrando" nascem com a prova, e o caso do
    contato digitado no balcão é testado à parte, com nome próprio.
    """
    methods = {
        ContactPoint.Type.PHONE: ContactPoint.VerificationMethod.OTP_SMS,
        ContactPoint.Type.WHATSAPP: ContactPoint.VerificationMethod.OTP_WHATSAPP,
        ContactPoint.Type.EMAIL: ContactPoint.VerificationMethod.OTP_EMAIL,
    }
    for contact in customer.contact_points.all():
        contact.mark_verified(methods[contact.type])
    return customer


@pytest.fixture
def customer(db):
    """Create a test customer."""
    return proven(
        Customer.objects.create(
            ref="TEST-001",
            first_name="Test",
            last_name="Customer",
            phone="5541999999999",
            email="test@example.com",
        )
    )


@pytest.fixture
def other_customer(db):
    """Create another test customer."""
    return proven(
        Customer.objects.create(
            ref="TEST-002",
            first_name="Other",
            last_name="Customer",
            phone="5541888888888",
            email="other@example.com",
        )
    )


@pytest.fixture
def access_link(customer):
    """Create a valid access link.

    The raw token is stored as ``link._raw_token`` so tests can
    exchange it while the DB stores only the HMAC digest.
    """
    link, raw_token = AccessLink.create_with_token(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.MANYCHAT,
    )
    link._raw_token = raw_token
    return link


@pytest.fixture
def expired_access_link(customer):
    """Create an expired access link."""
    link, raw_token = AccessLink.create_with_token(
        customer_id=customer.uuid,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    link._raw_token = raw_token
    return link


@pytest.fixture
def verification_code(db):
    """Create a valid verification code.

    The raw 6-digit code is stored as ``code._raw_code`` so tests
    can pass it to ``verify_for_login`` while the DB stores the HMAC.
    """
    raw_code, hmac_digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=hmac_digest,
        target_value="+5541999999999",
        purpose=VerificationCode.Purpose.LOGIN,
    )
    code.mark_sent()
    code._raw_code = raw_code
    return code


@pytest.fixture
def expired_verification_code(db):
    """Create an expired verification code."""
    return VerificationCode.objects.create(
        target_value="+5541999999999",
        purpose=VerificationCode.Purpose.LOGIN,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
