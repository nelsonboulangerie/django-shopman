"""Dois furos de identidade do laudo CORE-SOVEREIGNTY (WP-4), de ponta a ponta.

A4-2: o dispositivo confiável resolvia o dono do número por conta própria
(``get_by_phone``, que escolhe por ordenação). Quando o número aparece em dois
cadastros, o porto de identidade do doorman acusa conflito e o login por
código recusa; o dispositivo confiável abria a conta que viesse primeiro.
Agora ele pergunta ao mesmo porto e, havendo conflito, recusa com recado.

A4-3: a troca de número carimbava a origem da verificação como "OTP via
WhatsApp" fixo, mesmo quando o código saiu por SMS (a cadeia de produção
começa no SMS). Agora o carimbo é o canal por onde o código saiu de fato.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.services.auth import IDENTITY_CONFLICT_DETAIL

pytestmark = pytest.mark.django_db

NUMERO = "+5543999997701"
NUMERO_ANTIGO = "+5543999997711"
NUMERO_NOVO = "+5543999997712"


@pytest.fixture(autouse=True)
def _sem_portarias_de_ritmo(settings, monkeypatch):
    settings.RATELIMIT_ENABLE = False
    from shopman.doorman.conf import doorman_settings, reset_adapter

    from shopman.storefront.tests.identity_fakes import CapturingSender

    CapturingSender.last_code = ""
    reset_adapter()
    monkeypatch.setattr(doorman_settings, "ACCESS_CODE_COOLDOWN_SECONDS", 0)
    yield
    reset_adapter()


def _csrf_headers(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/storefront/cart/")
    return {"HTTP_X_CSRFTOKEN": response.cookies["csrftoken"].value}


def _confiar_no_dispositivo(client: Client, customer: Customer) -> None:
    from shopman.doorman import TrustedDevice
    from shopman.doorman.conf import doorman_settings

    _, raw_token = TrustedDevice.create_for(
        "customer", customer.uuid, user_agent="Mozilla/5.0 Test", ip_address="127.0.0.1"
    )
    client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token


def _device_check(client: Client, phone: str):
    return client.post(
        "/api/v1/auth/device-check/",
        data={"target": phone},
        content_type="application/json",
        **_csrf_headers(client),
    )


def _numero_com_dois_donos() -> tuple[Customer, Customer]:
    """A tem o número como contato de WhatsApp; B tem o mesmo número como identificador."""
    dona_do_contato = Customer.objects.create(ref="CUS-A42-A", first_name="Ana")
    ContactPoint.objects.create(
        customer=dona_do_contato,
        type=ContactPoint.Type.WHATSAPP,
        value_normalized=NUMERO,
        is_primary=True,
    )
    dono_do_identificador = Customer.objects.create(ref="CUS-A42-B", first_name="Bruno")
    CustomerIdentifier.objects.create(
        customer=dono_do_identificador,
        identifier_type="phone",
        identifier_value=NUMERO,
    )
    return dona_do_contato, dono_do_identificador


# ── A4-2 · dispositivo confiável pergunta ao porto e falha fechado ────


def test_dispositivo_confiavel_com_numero_de_dois_donos_recusa_com_recado(client: Client):
    dona_do_contato, _ = _numero_com_dois_donos()
    _confiar_no_dispositivo(client, dona_do_contato)

    response = _device_check(client, NUMERO)

    assert response.status_code == 409, response.content
    assert response.json()["detail"] == IDENTITY_CONFLICT_DETAIL
    assert "_auth_user_id" not in client.session


def test_o_pedido_de_codigo_do_mesmo_numero_da_o_mesmo_recado(client: Client):
    """A tela cai para o pedido de código quando o dispositivo recusa: o recado é o mesmo."""
    _numero_com_dois_donos()

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": NUMERO},
        content_type="application/json",
        **_csrf_headers(client),
    )

    assert response.status_code == 400, response.content
    assert response.json()["detail"] == IDENTITY_CONFLICT_DETAIL


def test_o_recado_fala_a_lingua_da_casa():
    assert "—" not in IDENTITY_CONFLICT_DETAIL
    assert "–" not in IDENTITY_CONFLICT_DETAIL


def test_dispositivo_confiavel_com_dono_unico_continua_entrando(client: Client):
    """O porto não muda o caminho feliz: o dono do número entra sem código."""
    customer = Customer.objects.create(ref="CUS-A42-UNICO", first_name="Clara", phone=NUMERO)
    _confiar_no_dispositivo(client, customer)

    response = _device_check(client, NUMERO)

    assert response.status_code == 200, response.content
    assert response.json()["trusted"] is True
    assert client.session.get("_auth_user_id")


def test_dispositivo_confiavel_de_outra_pessoa_nao_entra(client: Client):
    dona = Customer.objects.create(ref="CUS-A42-DONA", first_name="Dora", phone=NUMERO)
    outra = Customer.objects.create(ref="CUS-A42-OUTRA", first_name="Eva", phone="+5543999997702")
    _confiar_no_dispositivo(client, outra)

    response = _device_check(client, dona.phone)

    assert response.status_code == 200
    assert response.json()["trusted"] is False
    assert "_auth_user_id" not in client.session


def test_dispositivo_confiavel_nao_le_o_telefone_fora_do_porto(client: Client, monkeypatch):
    """A resolução por ordenação (`get_by_phone`) não é mais consultada."""
    from shopman.guestman.services import customer as customer_service

    def _proibido(*_args, **_kwargs):
        raise AssertionError("trusted_device_login resolveu identidade fora do porto")

    monkeypatch.setattr(customer_service, "get_by_phone", _proibido)
    customer = Customer.objects.create(ref="CUS-A42-PORTO", first_name="Fabi", phone=NUMERO)
    _confiar_no_dispositivo(client, customer)

    response = _device_check(client, NUMERO)

    assert response.status_code == 200, response.content
    assert response.json()["trusted"] is True


# ── A4-3 · a origem da verificação é o canal que levou o código ──────


def _login_as_customer(client: Client, customer: Customer) -> None:
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    info = make_identity_view(
        subject_id=customer.uuid, name=customer.name, phone=customer.phone, is_active=True
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    from shopman.storefront.tests.identity_fakes import grant_recent_step_up

    grant_recent_step_up(client, customer.uuid, "phone")


def _trocar_numero(client: Client) -> None:
    from shopman.storefront.tests.identity_fakes import CapturingSender

    pedido = client.post(
        "/api/v1/account/phone/request/",
        data={"phone": NUMERO_NOVO},
        content_type="application/json",
        **_csrf_headers(client),
    )
    assert pedido.status_code == 200, pedido.content
    assert CapturingSender.last_code
    confirmacao = client.post(
        "/api/v1/account/phone/confirm/",
        data={"phone": NUMERO_NOVO, "code": CapturingSender.last_code},
        content_type="application/json",
        **_csrf_headers(client),
    )
    assert confirmacao.status_code == 200, confirmacao.content


def _cadeia(settings, chain: list[str], senders: dict[str, str]) -> None:
    from shopman.doorman.conf import reset_adapter

    settings.DOORMAN = {**settings.DOORMAN, "DELIVERY_CHAIN": chain, "DELIVERY_SENDERS": senders}
    reset_adapter()


def _origens_do_numero_novo(customer: Customer) -> set[str]:
    return set(
        ContactPoint.objects.filter(
            customer=customer, value_normalized=NUMERO_NOVO
        ).values_list("verification_method", flat=True)
    )


def test_troca_com_codigo_por_sms_carimba_otp_sms(client: Client, settings):
    """O WhatsApp falha, a cadeia cai para o SMS: a origem gravada é SMS."""
    from shopman.doorman.models import VerificationCode

    _cadeia(
        settings,
        ["whatsapp", "sms"],
        {
            "whatsapp": "shopman.storefront.tests.identity_fakes.FailingSender",
            "sms": "shopman.storefront.tests.identity_fakes.CapturingSender",
        },
    )
    customer = Customer.objects.create(ref="CUS-A43-SMS", first_name="Gabi", phone=NUMERO_ANTIGO)
    _login_as_customer(client, customer)

    _trocar_numero(client)

    codigo = VerificationCode.objects.filter(target_value=NUMERO_NOVO).latest("created_at")
    assert codigo.delivery_method == "sms"
    assert _origens_do_numero_novo(customer) == {ContactPoint.VerificationMethod.OTP_SMS}


def test_troca_com_codigo_por_whatsapp_carimba_otp_whatsapp(client: Client, settings):
    _cadeia(
        settings,
        ["whatsapp"],
        {"whatsapp": "shopman.storefront.tests.identity_fakes.CapturingSender"},
    )
    customer = Customer.objects.create(ref="CUS-A43-WA", first_name="Helena", phone=NUMERO_ANTIGO)
    _login_as_customer(client, customer)

    _trocar_numero(client)

    assert _origens_do_numero_novo(customer) == {ContactPoint.VerificationMethod.OTP_WHATSAPP}


def test_canal_que_nao_prova_telefone_recusa_a_troca():
    from shopman.shop.services import account as account_service

    customer = Customer.objects.create(ref="CUS-A43-EMAIL", first_name="Iris", phone=NUMERO_ANTIGO)

    with pytest.raises(account_service.PhoneChangeRefused):
        account_service._set_primary_phone(customer, NUMERO_NOVO, proof="email")

    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO
