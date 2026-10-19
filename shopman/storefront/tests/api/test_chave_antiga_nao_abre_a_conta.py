"""Depois da troca, o telefone ou o e-mail ANTIGO não abre mais a conta (A4-1).

O teste irmão em ``test_troca_de_telefone.py`` entra com ``force_login`` e por
isso nunca cria o ``CustomerIdentifier`` que o login OTP grava. Foi assim que a
regressão do #1853 passou verde: o porto de identidade passou a ler o
identificador, a troca só apagava o contato, e a chave velha seguia abrindo a
porta. Aqui o primeiro login é OTP de verdade, nos dois canais.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db

NUMERO_ANTIGO = "+5543999998001"
NUMERO_NOVO = "+5543999998002"
NUMERO_NUNCA_VISTO = "+5543999998003"
EMAIL_ANTIGO = "ana.antiga@example.com"
EMAIL_NOVO = "ana.nova@example.com"


@pytest.fixture(autouse=True)
def _otp_sem_provedor(settings, monkeypatch):
    settings.RATELIMIT_ENABLE = False
    settings.DOORMAN = {
        **settings.DOORMAN,
        "DELIVERY_CHAIN": [],
        "MESSAGE_SENDER_CLASS": "shopman.storefront.tests.identity_fakes.CapturingSender",
    }
    from shopman.doorman.conf import doorman_settings, reset_adapter

    from shopman.storefront.tests.identity_fakes import CapturingSender

    CapturingSender.last_code = ""
    reset_adapter()
    monkeypatch.setattr(doorman_settings, "ACCESS_CODE_COOLDOWN_SECONDS", 0)


def _csrf(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/storefront/cart/")
    return {"HTTP_X_CSRFTOKEN": response.cookies["csrftoken"].value}


def _last_code() -> str:
    from shopman.storefront.tests.identity_fakes import CapturingSender

    assert CapturingSender.last_code
    code = CapturingSender.last_code
    CapturingSender.last_code = ""
    return code


def _pedir_codigo_de_login(client: Client, phone: str):
    return client.post(
        "/api/v1/auth/request-code/",
        data={"phone": phone},
        content_type="application/json",
    )


def _entrar_por_otp(client: Client, phone: str) -> dict:
    pedido = _pedir_codigo_de_login(client, phone)
    assert pedido.status_code == 200, pedido.content
    entrada = client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": phone, "code": _last_code()},
        content_type="application/json",
        **_csrf(client),
    )
    assert entrada.status_code == 200, entrada.content
    return client.get("/api/v1/auth/session/").json()


def _trocar_numero(client: Client, phone: str) -> None:
    pedido = client.post(
        "/api/v1/account/phone/request/",
        data={"phone": phone},
        content_type="application/json",
        **_csrf(client),
    )
    assert pedido.status_code == 200, pedido.content
    confirmacao = client.post(
        "/api/v1/account/phone/confirm/",
        data={"phone": phone, "code": _last_code()},
        content_type="application/json",
        **_csrf(client),
    )
    assert confirmacao.status_code == 200, confirmacao.content


def _sem_o_numero(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in {"phone", "code_expires_at"}}


def test_numero_antigo_nao_abre_a_conta_depois_da_troca_e_o_novo_abre(client: Client):
    primeira = _entrar_por_otp(client, NUMERO_ANTIGO)
    customer = Customer.objects.get(ref=primeira["customer_ref"])
    # A pré-condição que o teste irmão não tinha: o OTP gravou a chave.
    assert CustomerIdentifier.objects.filter(
        customer=customer, identifier_value=NUMERO_ANTIGO
    ).exists()

    _trocar_numero(client, NUMERO_NOVO)
    client.logout()

    assert not CustomerIdentifier.objects.filter(identifier_value=NUMERO_ANTIGO).exists()
    from shopman.doorman.conf import get_adapter

    assert get_adapter().resolve_identity("phone", NUMERO_ANTIGO, purpose="login") is None

    # Pedir código para o número antigo responde igual a pedir para um número
    # que nunca existiu: a resposta não conta que houve uma conta ali.
    antigo = _pedir_codigo_de_login(client, NUMERO_ANTIGO)
    nunca_visto = _pedir_codigo_de_login(client, NUMERO_NUNCA_VISTO)
    assert antigo.status_code == nunca_visto.status_code == 200
    assert _sem_o_numero(antigo.json()) == _sem_o_numero(nunca_visto.json())

    # Quem recebeu o número reciclado entra numa conta NOVA, vazia.
    estranho = _entrar_por_otp(client, NUMERO_ANTIGO)
    assert estranho["customer_ref"] != customer.ref
    client.logout()

    # E a dona da conta entra pelo número novo.
    dona = _entrar_por_otp(client, NUMERO_NOVO)
    assert dona["customer_ref"] == customer.ref
    assert dona["customer_phone"] == NUMERO_NOVO


def test_email_antigo_nao_abre_a_conta_depois_da_troca_e_o_novo_abre(client: Client):
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.services.verification import AuthService

    from shopman.storefront.tests.identity_fakes import CapturingSender

    def entrar_por_email(email: str):
        pedido = AuthService.request_code(
            email,
            delivery_method="email",
            sender=CapturingSender(),
        )
        assert pedido.success, pedido.error
        resultado = AuthService.verify_for_login(email, _last_code())
        assert resultado.success, resultado.error
        return resultado.customer

    primeira = entrar_por_email(EMAIL_ANTIGO)
    customer = Customer.objects.get(uuid=primeira.subject_id)
    assert CustomerIdentifier.objects.filter(
        customer=customer, identifier_type="email", identifier_value=EMAIL_ANTIGO
    ).exists()

    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    user, _ = get_or_create_user_for_customer(primeira)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    troca = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "Ana", "email": EMAIL_NOVO}),
        content_type="application/json",
        **_csrf(client),
    )
    assert troca.status_code == 200, troca.content
    client.logout()

    assert not CustomerIdentifier.objects.filter(identifier_value=EMAIL_ANTIGO).exists()
    assert get_adapter().resolve_identity("email", EMAIL_ANTIGO, purpose="login") is None

    estranho = entrar_por_email(EMAIL_ANTIGO)
    assert str(estranho.subject_id) != str(customer.uuid)

    dona = entrar_por_email(EMAIL_NOVO)
    assert str(dona.subject_id) == str(customer.uuid)
