from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory
from shopman.doorman.models import CustomerUser
from shopman.guestman.models import Customer

from shopman.shop.models import NotificationCategory, UserNotification
from shopman.shop.services import customer_sign_in

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/account/accesses/"


@pytest.fixture
def person_and_user():
    customer = Customer.objects.create(
        ref="CUS-ACCESS-SECURITY",
        first_name="Ana",
        phone="+5543999997001",
    )
    user = get_user_model().objects.create_user(username="customer-access-security")
    CustomerUser.objects.create(user=user, customer_id=customer.uuid)
    return customer, user


def _request_with_session(*, user, user_agent="Mozilla/5.0 (iPhone) Safari/605.1"):
    request = RequestFactory().post(
        "/api/v1/auth/verify-code/",
        REMOTE_ADDR="127.0.0.1",
        HTTP_USER_AGENT=user_agent,
    )
    SessionMiddleware(lambda req: None).process_request(request)
    request.session.save()
    customer_sign_in.mark_method(request, "otp")
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return request


def test_customer_login_creates_personal_alert(person_and_user):
    _customer, user = person_and_user

    request = _request_with_session(user=user)

    alert = UserNotification.objects.get(
        user=user,
        source_condition=customer_sign_in.SOURCE_CONDITION,
    )
    assert alert.category == NotificationCategory.SIGN_IN
    assert alert.title == "Novo acesso na sua conta"
    assert alert.action_url == "/conta/seguranca"
    assert alert.action_data["method"] == "otp"
    assert alert.action_data["session_ref"]
    assert request.session.session_key not in str(alert.action_data)
    assert alert.retention_until > alert.created_at


def test_unmarked_test_or_internal_login_does_not_create_false_alert(person_and_user):
    _customer, user = person_and_user
    client = Client()

    client.force_login(user)

    assert not UserNotification.objects.filter(
        user=user,
        source_condition=customer_sign_in.SOURCE_CONDITION,
    ).exists()


def test_customer_can_see_and_end_another_active_session(person_and_user):
    _customer, user = person_and_user
    current = Client()
    other = Client()
    current.force_login(user)
    other.force_login(user)
    other_key = other.session.session_key
    assert other_key
    other_ref = customer_sign_in._session_ref(other_key)
    UserNotification.objects.create(
        user=user,
        category=NotificationCategory.SIGN_IN,
        title="Novo acesso na sua conta",
        source_condition=customer_sign_in.SOURCE_CONDITION,
        source_ref=other_ref,
        action_data={
            "session_ref": other_ref,
            "device_label": "Chrome no Android",
            "method_label": "dispositivo reconhecido",
            "approximate_city": "Londrina, PR · Brasil",
        },
    )

    response = current.get(LIST_URL)

    assert response.status_code == 200
    row = next(item for item in response.json()["accesses"] if item["id"] == other_ref)
    assert row == {
        "id": other_ref,
        "device_label": "Chrome no Android",
        "method_label": "dispositivo reconhecido",
        "approximate_city": "Londrina, PR · Brasil",
        "created_at": UserNotification.objects.get().created_at.isoformat(),
        "created_at_display": UserNotification.objects.get().created_at.astimezone().strftime("%d/%m/%Y às %H:%M"),
        "is_active": True,
        "is_current": False,
    }

    ended = current.delete(f"{LIST_URL}{other_ref}/")

    assert ended.status_code == 200
    assert ended.json()["revoked"] is True
    assert other.get(LIST_URL).status_code == 401
    assert current.get(LIST_URL).status_code == 200


def test_end_other_accesses_keeps_the_current_session(person_and_user):
    _customer, user = person_and_user
    current = Client()
    other = Client()
    current.force_login(user)
    other.force_login(user)

    response = current.delete(LIST_URL)

    assert response.status_code == 200
    assert response.json()["revoked"] == 1
    assert current.get(LIST_URL).status_code == 200
    assert other.get(LIST_URL).status_code == 401


def test_anonymous_person_cannot_read_or_revoke_accesses(client: Client):
    assert client.get(LIST_URL).status_code == 401
    assert client.delete(LIST_URL).status_code == 401
