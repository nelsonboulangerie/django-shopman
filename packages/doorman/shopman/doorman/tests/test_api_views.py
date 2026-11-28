"""
Tests for API views error code propagation and access_link_request rate limit detection.
"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory
from shopman.doorman.api.views import RequestCodeView, VerifyCodeView
from shopman.doorman.error_codes import ErrorCode
from shopman.doorman.exceptions import GateError
from shopman.doorman.models import VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.views.access_link_request import AccessLinkRequestView
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.models import ContactPoint, Customer

# ===========================================
# RequestCodeView
# ===========================================


@pytest.mark.django_db
class TestRequestCodeViewErrorCodes:
    """API RequestCodeView includes error_code in error responses and sets correct HTTP status."""

    def setup_method(self):
        self.factory = APIRequestFactory()
        self.view = RequestCodeView.as_view()

    def _post(self, data):
        request = self.factory.post("/api/auth/request-code/", data, format="json")
        return self.view(request)

    def test_rate_limit_returns_429_with_error_code(self, customer):
        with patch(
            "shopman.doorman.services.verification.Gates.rate_limit",
            side_effect=GateError("G9"),
        ):
            response = self._post({"target": customer.phone})

        assert response.status_code == 429
        assert response.data["error_code"] == ErrorCode.RATE_LIMIT

    def test_cooldown_returns_429_with_error_code(self, customer):
        with patch(
            "shopman.doorman.services.verification.Gates.code_cooldown",
            side_effect=GateError("G11"),
        ):
            response = self._post({"target": customer.phone})

        assert response.status_code == 429
        assert response.data["error_code"] == ErrorCode.COOLDOWN

    def test_ip_rate_limit_returns_429_with_error_code(self, customer):
        with patch(
            "shopman.doorman.services.verification.Gates.ip_rate_limit",
            side_effect=GateError("G10"),
        ):
            response = self._post({"target": customer.phone})

        assert response.status_code == 429
        assert response.data["error_code"] == ErrorCode.IP_RATE_LIMIT

    def test_invalid_target_returns_400_with_error_code(self):
        from shopman.doorman.protocols.identity import IdentityHandle

        with patch(
            "shopman.doorman.adapter.DefaultAuthAdapter.login_handle",
            return_value=IdentityHandle("phone", "", False, False),
        ):
            response = self._post({"target": "invalid"})

        assert response.status_code == 400
        assert response.data["error_code"] == ErrorCode.INVALID_TARGET

    def test_phone_alias_is_not_accepted(self, customer):
        response = self._post({"phone": customer.phone})

        assert response.status_code == 400
        assert "target" in response.data["errors"]

    def test_identity_conflict_returns_400_without_auto_create(self, customer, other_customer):
        value = "+5543999990171"
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value=value,
        )
        ContactPoint.objects.create(
            customer=other_customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=value,
        )
        customer_count = Customer.objects.count()

        response = self._post({"target": value})

        assert response.status_code == 400
        assert response.data["error_code"] == ErrorCode.IDENTITY_CONFLICT
        assert Customer.objects.count() == customer_count

    def test_error_response_shape(self, customer):
        with patch(
            "shopman.doorman.services.verification.Gates.rate_limit",
            side_effect=GateError("G9"),
        ):
            response = self._post({"target": customer.phone})

        assert "detail" in response.data
        assert "error_code" in response.data


# ===========================================
# VerifyCodeView
# ===========================================


@pytest.mark.django_db
class TestVerifyCodeViewErrorCodes:
    """API VerifyCodeView includes error_code in error responses."""

    def setup_method(self):
        self.factory = APIRequestFactory()
        self.view = VerifyCodeView.as_view()

    def _post(self, data):
        request = self.factory.post("/api/auth/verify-code/", data, format="json")
        return self.view(request)

    def test_expired_code_returns_400_with_error_code(self, customer):
        response = self._post({"target": customer.phone, "code": "123456"})

        assert response.status_code == 400
        assert response.data["error_code"] == ErrorCode.CODE_EXPIRED

    def test_phone_alias_is_not_accepted(self, verification_code):
        response = self._post({"phone": verification_code.target_value, "code": "000000"})

        assert response.status_code == 400
        assert "target" in response.data["errors"]

    def test_identity_conflict_returns_400_without_auto_create(self, customer, other_customer):
        value = "+5543999990172"
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value=value,
        )
        ContactPoint.objects.create(
            customer=other_customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=value,
        )
        raw_code, digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=digest,
            target_value=value,
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        customer_count = Customer.objects.count()

        response = self._post({"target": value, "code": raw_code})

        assert response.status_code == 400
        assert response.data["error_code"] == ErrorCode.IDENTITY_CONFLICT
        assert Customer.objects.count() == customer_count

    def test_wrong_code_returns_400_with_error_code(self, verification_code):
        response = self._post({"target": verification_code.target_value, "code": "000000"})

        assert response.status_code == 400
        assert response.data["error_code"] == ErrorCode.CODE_INVALID

    def test_error_response_shape(self, verification_code):
        response = self._post({"target": verification_code.target_value, "code": "000000"})

        assert "detail" in response.data
        assert "error_code" in response.data
        assert "attempts_remaining" in response.data


# ===========================================
# AccessLinkRequestView — rate limit via error code
# ===========================================


@pytest.mark.django_db
class TestAccessLinkRequestViewRateLimit:
    """AccessLinkRequestView uses error_code (not string matching) to set 429 status."""

    def setup_method(self):
        from django.test import RequestFactory as DjangoRequestFactory
        self.factory = DjangoRequestFactory()

    def _post_json(self, email):
        body = json.dumps({"email": email})
        request = self.factory.post(
            "/auth/access-link/", body, content_type="application/json"
        )
        return AccessLinkRequestView.as_view()(request)

    def test_email_rate_limit_returns_429(self, customer):
        with patch(
            "shopman.doorman.services.access_link.Gates.access_link_rate_limit",
            side_effect=GateError("G12"),
        ):
            response = self._post_json(customer.email)

        assert response.status_code == 429

    def test_ip_rate_limit_returns_429(self, customer):
        with patch(
            "shopman.doorman.services.access_link.Gates.ip_rate_limit",
            side_effect=GateError("G10"),
        ):
            response = self._post_json(customer.email)

        assert response.status_code == 429

    def test_account_not_found_returns_generic_success(self):
        response = self._post_json("nobody@example.com")
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True

    def test_invalid_email_returns_400(self):
        response = self._post_json("not-an-email")
        assert response.status_code == 400
