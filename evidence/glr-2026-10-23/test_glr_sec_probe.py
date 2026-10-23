# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
import pytest
from shopman.guestman.models import Customer

from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY

pytestmark = [pytest.mark.django_db]

@pytest.fixture(autouse=True)
def _web(db):
    from shopman.shop.models import Channel
    Channel.objects.get_or_create(ref="web", defaults={"name": "web"})

def _sign_in(client, person, strength=None):
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import CustomerUser
    User = get_user_model()
    user = User.objects.create_user(username=f"c-{person.ref}", password="x")
    CustomerUser.objects.create(user=user, customer_id=person.uuid)
    client.force_login(user)
    s = client.session
    if strength: s[IDENTITY_SESSION_KEY] = strength
    s.save()
    return user

@pytest.fixture
def person(db):
    return Customer.objects.create(ref="CLI-GLR", first_name="Ana", phone="+5543999998001")

def test_weak_session_passkeys_refused(client, person):
    _sign_in(client, person, IDENTITY_NUMBER)
    r = client.get("/api/v1/account/passkeys/")
    assert r.status_code == 403

def test_weak_session_can_request_phone_change(client, person):
    _sign_in(client, person, IDENTITY_NUMBER)
    r = client.post("/api/v1/account/phone/request/", {"phone": "+5543988887777"}, content_type="application/json")
    assert r.status_code == 200

def test_weak_session_can_trust_device(client, person):
    _sign_in(client, person, IDENTITY_NUMBER)
    r = client.post("/api/v1/auth/trust-device/", {"trust": True}, content_type="application/json")
    assert r.status_code == 200 and r.json()["trusted"] is True
    # novo navegador com o cookie de confiança: entra forte
    dt = r.cookies["doorman_dt"].value
    from django.test import Client
    fresh = Client()
    fresh.cookies["doorman_dt"] = dt
    client = fresh
    r2 = client.post("/api/v1/auth/device-check/", {"phone": "+5543999998001"}, content_type="application/json")
    assert r2.status_code == 200 and r2.json().get("trusted") is True
    r3 = client.get("/api/v1/account/passkeys/")
    assert r3.status_code == 200

def test_schema_public(client):
    r = client.get("/api/schema/")
    assert r.status_code == 200 and len(r.content) > 100_000
