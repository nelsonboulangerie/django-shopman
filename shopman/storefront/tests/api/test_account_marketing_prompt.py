"""POST /api/v1/account/marketing-prompt/ — a pergunta de novidades, respondida uma vez.

O que este arquivo trava:

- "Deixar para depois" e "não marquei a caixa" gravam SÓ o carimbo em
  ``Customer.metadata``. Nunca ``opted_out``: um opt-out gravado é proibição e
  cala até o recado do próprio pedido naquele canal
  (`shop/services/notification.py::_revoked_notification_channels`).
- Marcar a caixa concede ``opted_in`` no whatsapp e SÓ nele. O caminho de
  Preferências (`set_notification_consent`) completa os outros canais com
  ``opted_out`` explícito; no gate o cliente não viu esses canais.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import Client
from shopman.guestman import ConsentService
from shopman.guestman.contrib.consent.models import CommunicationConsent
from shopman.guestman.models import Customer

from .test_auth_session import _csrf_headers, _login_as_customer

pytestmark = pytest.mark.django_db

URL = "/api/v1/account/marketing-prompt/"
STAMP = "marketing_prompt_answered_at"


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings):
    settings.RATELIMIT_ENABLE = False


def _customer(ref: str = "CUS-PROMPT", phone: str = "+5543999991001", **extra) -> Customer:
    return Customer.objects.create(ref=ref, first_name="Ana", last_name="Silva", phone=phone, **extra)


def _post(client: Client, body: dict | None, **headers):
    return client.post(URL, data=json.dumps(body if body is not None else {}), content_type="application/json", **headers)


def _consent_rows(customer: Customer) -> dict[str, str]:
    return dict(CommunicationConsent.objects.filter(customer=customer).values_list("channel", "status"))


def test_anonymous_is_refused(client: Client):
    response = _post(client, {})

    assert response.status_code == 401
    assert CommunicationConsent.objects.count() == 0


def test_post_requires_csrf():
    client = Client(enforce_csrf_checks=True)
    customer = _customer()
    _login_as_customer(client, customer)

    response = _post(client, {})

    assert response.status_code == 403
    customer.refresh_from_db()
    assert STAMP not in customer.metadata


def test_skip_writes_only_the_stamp_and_never_an_opt_out(client: Client):
    customer = _customer()
    _login_as_customer(client, customer)

    response = _post(client, {}, **_csrf_headers(client))

    assert response.status_code == 200
    assert response.json()["whatsapp_opted_in"] is False
    customer.refresh_from_db()
    stamp = customer.metadata[STAMP]
    assert stamp == response.json()["answered_at"]
    # ISO 8601 com fuso: o carimbo é comparável e não ambíguo.
    assert "T" in stamp and ("+" in stamp or stamp.endswith("Z"))
    assert _consent_rows(customer) == {}
    # O gate parou de perguntar.
    session = client.get("/api/v1/auth/session/").json()
    assert session["welcome_asks_marketing"] is False
    assert session["requires_welcome"] is False


def test_unchecked_box_is_the_same_as_skip(client: Client):
    customer = _customer()
    _login_as_customer(client, customer)

    response = _post(client, {"whatsapp": False}, **_csrf_headers(client))

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.metadata[STAMP]
    assert _consent_rows(customer) == {}


def test_stamp_is_idempotent_and_keeps_the_first_answer(client: Client):
    customer = _customer()
    _login_as_customer(client, customer)
    headers = _csrf_headers(client)

    first = _post(client, {}, **headers).json()["answered_at"]
    second = _post(client, {}, **headers).json()["answered_at"]

    assert first == second
    customer.refresh_from_db()
    assert customer.metadata[STAMP] == first


def test_checked_box_without_birthday_is_refused_by_name(client: Client):
    customer = _customer()
    _login_as_customer(client, customer)

    response = _post(client, {"whatsapp": True}, **_csrf_headers(client))

    assert response.status_code == 400
    assert response.json()["field"] == "birthday"
    customer.refresh_from_db()
    # Recusa não carimba: o gate volta a perguntar, com a razão dita.
    assert STAMP not in customer.metadata
    assert _consent_rows(customer) == {}


def test_checked_box_grants_whatsapp_only_after_the_profile_took_the_birthday(client: Client):
    """O fluxo da tela: PATCH profile (nome + aniversário) → POST marketing-prompt."""
    customer = Customer.objects.create(ref="CUS-PROMPT-NEW", first_name="", last_name="", phone="+5543999991002")
    _login_as_customer(client, customer)
    headers = _csrf_headers(client)

    profile = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "Ana", "birthday": "1990-05-15"}),
        content_type="application/json",
        **headers,
    )
    assert profile.status_code == 200, profile.json()

    response = _post(client, {"whatsapp": True}, **headers)

    assert response.status_code == 200
    assert response.json()["whatsapp_opted_in"] is True
    customer.refresh_from_db()
    assert customer.birthday.isoformat() == "1990-05-15"
    assert customer.first_name == "Ana"
    assert customer.metadata[STAMP]
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True
    # SÓ o whatsapp ganha linha. E-mail/SMS/push seguem sem registro: o cliente
    # não viu essas chaves, então não há recusa a gravar por ele.
    assert _consent_rows(customer) == {"whatsapp": "opted_in"}
    session = client.get("/api/v1/auth/session/").json()
    assert session["requires_welcome"] is False


def test_evidence_records_the_sentence_the_person_read(client: Client):
    from shopman.guestman.contrib.consent.models import CommunicationConsentEvent

    from shopman.storefront.api.account import MARKETING_PROMPT_DISCLOSURE, MARKETING_PROMPT_DISCLOSURE_VERSION

    customer = _customer(birthday="1990-05-15")
    _login_as_customer(client, customer)

    _post(client, {"whatsapp": True}, **_csrf_headers(client))

    event = CommunicationConsentEvent.objects.get(customer=customer, channel="whatsapp")
    assert event.disclosure_text == MARKETING_PROMPT_DISCLOSURE
    assert event.disclosure_version == MARKETING_PROMPT_DISCLOSURE_VERSION
    assert event.source == "storefront_welcome"


def test_the_sentence_in_evidence_is_the_sentence_on_screen():
    """A evidência guarda o que a pessoa LEU. Se a copy da tela mudar, este teste
    obriga a mudar a frase gravada (e a versão) junto."""
    from shopman.storefront.api.account import MARKETING_PROMPT_DISCLOSURE

    page = Path(__file__).resolve().parents[4] / "surfaces" / "storefront-nuxt" / "app" / "pages" / "entrar.vue"
    if not page.exists():
        pytest.skip("superfície Nuxt ausente neste checkout")
    source = page.read_text(encoding="utf-8")
    for sentence in MARKETING_PROMPT_DISCLOSURE.split(". "):
        assert sentence.rstrip(".") in source, sentence


def test_known_minor_is_stamped_but_never_opted_in(client: Client):
    customer = _customer(birthday="2015-01-01")
    _login_as_customer(client, customer)

    response = _post(client, {"whatsapp": True}, **_csrf_headers(client))

    assert response.status_code == 200
    assert response.json()["whatsapp_opted_in"] is False
    customer.refresh_from_db()
    assert customer.metadata[STAMP]
    assert _consent_rows(customer) == {}


def test_granting_twice_does_not_duplicate_evidence(client: Client):
    customer = _customer(birthday="1990-05-15")
    _login_as_customer(client, customer)
    headers = _csrf_headers(client)

    _post(client, {"whatsapp": True}, **headers)
    before = ConsentService.get_consents(customer.ref)[0].last_event_ref
    _post(client, {"whatsapp": True}, **headers)
    after = ConsentService.get_consents(customer.ref)[0].last_event_ref

    assert before == after
    assert _consent_rows(customer) == {"whatsapp": "opted_in"}


def test_non_boolean_answer_is_refused(client: Client):
    customer = _customer()
    _login_as_customer(client, customer)

    response = _post(client, {"whatsapp": "sim"}, **_csrf_headers(client))

    assert response.status_code == 400
    assert response.json()["field"] == "whatsapp"
