from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import PrivacyRequestOperation, PrivacyRequestReceipt

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


def _mint_login_code(phone: str) -> str:
    """Create a valid LOGIN verification code for ``phone`` and return the raw digits."""
    from shopman.doorman.models.verification_code import VerificationCode, generate_raw_code

    raw_code, hmac_digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=hmac_digest,
        target_value=phone,
        purpose=VerificationCode.Purpose.LOGIN,
    )
    code.mark_sent()
    return raw_code


def test_delete_requires_step_up(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-DEL", first_name="Ana", phone="+5543999990010")
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"
    customer.refresh_from_db()
    assert customer.phone == "+5543999990010"  # NÃO anonimizado


def test_export_requires_step_up(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-EXP", first_name="Bia", phone="+5543999990011")
    _login_as_customer(client, customer)

    response = client.get("/api/v1/account/export/")

    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"


def test_step_up_with_wrong_code_is_rejected(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-BAD", first_name="Caio", phone="+5543999990012")
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/step-up/",
        data={"code": "000000", "purpose": "delete"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_step_up_then_delete_succeeds(client: Client):
    phone = "+5543999990013"
    customer = Customer.objects.create(ref="CUS-SU-OK", first_name="Duda", phone=phone)
    _login_as_customer(client, customer)
    raw_code = _mint_login_code(phone)

    step_up = client.post(
        "/api/v1/account/step-up/",
        data={"code": raw_code, "purpose": "delete"},
        content_type="application/json",
    )
    assert step_up.status_code == 200

    deleted = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_completed_delete_replays_after_session_was_flushed(client: Client):
    phone = "+5543999990018"
    customer = Customer.objects.create(ref="CUS-SU-LOST", first_name="Lia", phone=phone)
    _login_as_customer(client, customer)
    raw_code = _mint_login_code(phone)
    key = str(uuid.uuid4())
    assert client.post(
        "/api/v1/account/step-up/",
        data={"code": raw_code, "purpose": "delete"},
        content_type="application/json",
    ).status_code == 200
    first = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert first.status_code == 200

    replay = Client().post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert replay.status_code == 200
    assert replay.json() == {
        "ok": True,
        "receipt_ref": first.json()["receipt_ref"],
        "replayed": True,
    }


def test_fresh_step_up_flag_lets_export_through(client: Client):
    from shopman.storefront.api.account import STEP_UP_SESSION_KEY

    customer = Customer.objects.create(ref="CUS-SU-FLAG", first_name="Edu", phone="+5543999990014")
    _login_as_customer(client, customer)

    accepted_at = timezone.now()
    session = client.session
    session[STEP_UP_SESSION_KEY] = {
        "customer_uuid": str(customer.uuid),
        "purpose": "export",
        "accepted_at": accepted_at.isoformat(),
    }
    session.save()

    response = client.get("/api/v1/account/export/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"
    receipt = PrivacyRequestReceipt.objects.get(operation=PrivacyRequestOperation.EXPORT)
    assert response["X-Privacy-Request-Ref"] == str(receipt.ref)
    assert receipt.authorized_at == accepted_at
    assert b'"schema_version":"account_export.v1"' in b"".join(response.streaming_content)


def test_step_up_is_bound_to_customer_and_purpose(client: Client):
    from shopman.storefront.api.account import STEP_UP_SESSION_KEY

    customer = Customer.objects.create(
        ref="CUS-SU-BOUND",
        first_name="Fê",
        phone="+5543999990015",
    )
    _login_as_customer(client, customer)
    session = client.session
    session[STEP_UP_SESSION_KEY] = {
        "customer_uuid": str(uuid.uuid4()),
        "purpose": "delete",
        "accepted_at": timezone.now().isoformat(),
    }
    session.save()

    wrong_customer = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert wrong_customer.status_code == 403

    session = client.session
    session[STEP_UP_SESSION_KEY] = {
        "customer_uuid": str(customer.uuid),
        "purpose": "export",
        "accepted_at": timezone.now().isoformat(),
    }
    session.save()
    wrong_purpose = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert wrong_purpose.status_code == 403


def test_export_failure_keeps_safe_failed_receipt(client: Client):
    from shopman.storefront.api.account import STEP_UP_SESSION_KEY

    customer = Customer.objects.create(
        ref="CUS-SU-EXP-FAIL",
        first_name="Fabi",
        phone="+5543999990017",
    )
    _login_as_customer(client, customer)
    session = client.session
    session[STEP_UP_SESSION_KEY] = {
        "customer_uuid": str(customer.uuid),
        "purpose": "export",
        "accepted_at": timezone.now().isoformat(),
    }
    session.save()

    with patch(
        "shopman.storefront.services.account_export.build_account_export",
        side_effect=RuntimeError("private database detail"),
    ):
        response = client.get("/api/v1/account/export/")

    assert response.status_code == 503
    receipt = PrivacyRequestReceipt.objects.get(operation=PrivacyRequestOperation.EXPORT)
    assert receipt.state == "failed"
    assert receipt.failure_code == "account_export_incomplete"
    assert "private database detail" not in response.content.decode()


def test_delete_acknowledgement_must_be_boolean_true(client: Client):
    customer = Customer.objects.create(
        ref="CUS-SU-ACK",
        first_name="Gi",
        phone="+5543999990016",
    )
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": "false"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 400
