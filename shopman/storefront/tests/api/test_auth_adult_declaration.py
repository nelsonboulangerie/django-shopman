"""A declaração de maioridade é feita ao ENTRAR — e todo caminho de entrada carimba.

Decisão do dono (16/09): pedir data de nascimento para receber novidades é
atrito demais. A nota ao lado do botão da loja diz "Ao continuar, você confirma
ser maior de idade e aceita os Termos de uso"; quem autentica declarou, e o
cadastro ganha ``Customer.metadata["adult_declaration"]``.

O que este arquivo trava:

- os QUATRO caminhos carimbam: código (verify-code), aparelho reconhecido
  (device-check), access link (auth/access) e passkey;
- o carimbo é idempotente — a primeira declaração fica — e guarda a versão dos
  termos que o marketing reconhece (``ADULT_DECLARING_TERMS_VERSIONS``);
- já carimbado, o login não toca o banco para carimbar de novo;
- clientes antigos ganham a declaração no próximo login (é isso que o teste do
  aparelho reconhecido mostra: cadastro sem carimbo, entra, sai carimbado).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.test import Client
from shopman.guestman.models import Customer

from shopman.shop.services import account as account_service
from shopman.shop.services.marketing_age import (
    ADULT_DECLARATION_KEY,
    ADULT_DECLARING_TERMS_VERSIONS,
    declares_adult,
    is_proved_adult,
)

from .test_auth_session import _csrf_headers

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings):
    settings.RATELIMIT_ENABLE = False


def _stamp(customer: Customer) -> dict:
    customer.refresh_from_db()
    return customer.metadata.get(ADULT_DECLARATION_KEY) or {}


def _assert_declared(customer: Customer) -> dict:
    stamp = _stamp(customer)
    assert stamp["terms_version"] == account_service.LOGIN_TERMS_VERSION
    assert stamp["source"] == "storefront_login"
    # ISO 8601 com fuso: comparável e não ambíguo, como o carimbo da pergunta de novidades.
    assert "T" in stamp["at"] and ("+" in stamp["at"] or stamp["at"].endswith("Z"))
    assert declares_adult(customer.metadata) is True
    return stamp


def test_the_login_terms_version_is_one_the_marketing_recognizes():
    """O gêmeo que falta: quem sobe a versão da entrada tem de ensinar o marketing."""
    assert account_service.LOGIN_TERMS_VERSION in ADULT_DECLARING_TERMS_VERSIONS


# ── Código (OTP) ────────────────────────────────────────────────────────


def _login_with_code(client: Client, monkeypatch, customer: Customer):
    from shopman.storefront.api import auth as auth_api

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(
        auth_api.auth_service,
        "verify_for_login",
        lambda *, phone, code_input, request: SimpleNamespace(
            success=True, customer=SimpleNamespace(uuid=customer.uuid)
        ),
    )
    monkeypatch.setattr(auth_api.auth_service, "confirmed_customer_name", lambda auth_result: "Ana")
    return client.post(
        "/api/v1/auth/verify-code/",
        data={"target": customer.phone, "code": "123456"},
        content_type="application/json",
        **_csrf_headers(client),
    )


def test_verify_code_stamps_the_declaration(client: Client, monkeypatch):
    customer = Customer.objects.create(ref="CUS-ADULT-OTP", first_name="Ana", phone="+5543999990101")

    response = _login_with_code(client, monkeypatch, customer)

    assert response.status_code == 200
    _assert_declared(customer)


def test_the_first_declaration_stays(client: Client, monkeypatch):
    customer = Customer.objects.create(ref="CUS-ADULT-TWICE", first_name="Ana", phone="+5543999990102")

    _login_with_code(client, monkeypatch, customer)
    first = _stamp(customer)
    _login_with_code(client, monkeypatch, customer)

    assert _stamp(customer) == first


def test_an_already_stamped_login_does_not_write_again(client: Client, monkeypatch, django_assert_num_queries):
    customer = Customer.objects.create(ref="CUS-ADULT-NOWRITE", first_name="Ana", phone="+5543999990103")
    _login_with_code(client, monkeypatch, customer)
    customer.refresh_from_db()

    # Já carimbado: nem trava a linha, nem grava. O objeto que o view recebe
    # veio de uma leitura recente, e é nele que se olha.
    with django_assert_num_queries(0):
        account_service.record_adult_declaration(customer)


def test_a_stamp_without_a_known_version_proves_nothing():
    assert declares_adult({ADULT_DECLARATION_KEY: {"terms_version": "outra-coisa"}}) is False
    assert declares_adult({ADULT_DECLARATION_KEY: {"at": "2026-09-16T10:00:00+00:00"}}) is False
    assert declares_adult({ADULT_DECLARATION_KEY: "sim"}) is False
    assert declares_adult(None) is False
    assert declares_adult({}) is False


def test_the_birthday_that_proves_a_minor_beats_the_declaration():
    from django.utils import timezone

    today = timezone.localdate()
    declared = {ADULT_DECLARATION_KEY: {"terms_version": account_service.LOGIN_TERMS_VERSION}}
    assert is_proved_adult(None, declared) is True
    assert is_proved_adult(today.replace(year=today.year - 30), {}) is True
    assert is_proved_adult(today.replace(year=today.year - 17), declared) is False
    assert is_proved_adult(None, {}) is False


# ── Aparelho reconhecido ───────────────────────────────────────────────


def test_trusted_device_login_stamps_an_old_customer(client: Client):
    """Cliente de antes desta regra: entra pelo aparelho reconhecido e sai declarado."""
    from shopman.doorman import TrustedDevice
    from shopman.doorman.conf import doorman_settings

    customer = Customer.objects.create(ref="CUS-ADULT-DEVICE", first_name="Dora", phone="+5543999990104")
    assert ADULT_DECLARATION_KEY not in customer.metadata
    _, raw_token = TrustedDevice.create_for(
        "customer", customer.uuid, user_agent="Mozilla/5.0 Test", ip_address="127.0.0.1"
    )
    client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

    response = client.post(
        "/api/v1/auth/device-check/",
        data={"target": customer.phone},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["trusted"] is True
    _assert_declared(customer)


def test_an_unrecognized_device_does_not_declare_anyone(client: Client):
    customer = Customer.objects.create(ref="CUS-ADULT-NODEVICE", first_name="Dora", phone="+5543999990105")

    response = client.post(
        "/api/v1/auth/device-check/",
        data={"target": customer.phone},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["trusted"] is False
    assert _stamp(customer) == {}


# ── Access link ────────────────────────────────────────────────────────


def test_access_link_exchange_stamps_the_declaration(settings):
    from django.core.cache import cache
    from django.test import override_settings

    cache.clear()
    customer = Customer.objects.create(ref="CUS-ADULT-LINK", first_name="Ana", phone="5543999990106")
    with override_settings(
        DOORMAN={
            "ACCESS_LINK_API_KEY": "test-access-key",
            "ACCESS_LINK_ENTRY_URL": "https://loja.test",
            "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
        }
    ):
        create = Client().post(
            "/api/auth/access/create/",
            data=json.dumps({"customer_id": str(customer.uuid), "next": "/menu"}),
            content_type="application/json",
            HTTP_X_API_KEY="test-access-key",
        )
        assert create.status_code == 200, create.content
        exchange = Client().post(
            "/api/v1/auth/access/",
            data=json.dumps({"token": create.json()["token"]}),
            content_type="application/json",
        )

    assert exchange.status_code == 200, exchange.content
    assert exchange.json()["is_authenticated"] is True
    _assert_declared(customer)


# ── Passkey ────────────────────────────────────────────────────────────


def test_passkey_login_stamps_the_declaration(client: Client):
    from shopman.storefront.tests.web.test_passkey import (
        LOGIN,
        LOGIN_OPTIONS,
        _as_device_options,
        _as_json_credential,
        _enroll,
        _sign_in,
    )

    person = Customer.objects.create(ref="CUS-ADULT-PASSKEY", first_name="Ana", phone="+5543999990107")
    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()
    # Cadastrar a chave não declara nada; entrar com ela, sim.
    assert _stamp(person) == {}

    options = client.post(LOGIN_OPTIONS, content_type="application/json")
    assertion = device.get({"publicKey": _as_device_options(options.json())}, "http://testserver")
    response = client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    _assert_declared(person)
