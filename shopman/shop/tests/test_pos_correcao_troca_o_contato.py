"""Corrigir o telefone ou o e-mail no balcão é TROCAR: o antigo não abre a conta (A4-1).

Decisão da coordenação. Antes, a correção do PDV deixava o número antigo como
contato secundário, "no histórico", e ele seguia abrindo a conta por OTP. Os
pedidos antigos guardam o contato de cada pedido; o cadastro não precisa reter
a chave para lembrar.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos import resolve_or_create_customer

pytestmark = pytest.mark.django_db

NUMERO_ANTIGO = "+5543999994001"
NUMERO_NOVO = "+5543999994002"
NUMERO_NUNCA_VISTO = "+5543999994003"
EMAIL_ANTIGO = "ana.antiga@example.com"
EMAIL_NOVO = "ana.nova@example.com"


@pytest.fixture(autouse=True)
def _ambiente(settings, monkeypatch):
    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
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


def _last_code() -> str:
    from shopman.storefront.tests.identity_fakes import CapturingSender

    assert CapturingSender.last_code
    code = CapturingSender.last_code
    CapturingSender.last_code = ""
    return code


def _csrf(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/storefront/cart/")
    return {"HTTP_X_CSRFTOKEN": response.cookies["csrftoken"].value}


def _pedir_codigo(client: Client, phone: str):
    return client.post(
        "/api/v1/auth/request-code/",
        data={"phone": phone},
        content_type="application/json",
    )


def _entrar_por_otp(client: Client, phone: str) -> dict:
    assert _pedir_codigo(client, phone).status_code == 200
    entrada = client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": phone, "code": _last_code()},
        content_type="application/json",
        **_csrf(client),
    )
    assert entrada.status_code == 200, entrada.content
    return client.get("/api/v1/auth/session/").json()


def test_corrigir_o_telefone_no_balcao_tira_o_numero_antigo_da_porta():
    cliente = Client()
    sessao = _entrar_por_otp(cliente, NUMERO_ANTIGO)
    customer = Customer.objects.get(ref=sessao["customer_ref"])
    Customer.objects.filter(pk=customer.pk).update(first_name="Ana", last_name="Prado")
    assert CustomerIdentifier.objects.filter(identifier_value=NUMERO_ANTIGO).exists()
    cliente.logout()

    resolvido = resolve_or_create_customer(
        ref=customer.ref,
        name="Ana Prado",
        phone=NUMERO_NOVO,
        contact_correction=True,
        operator_username="op",
    )

    assert resolvido["ref"] == customer.ref
    customer.refresh_from_db()
    assert customer.phone == NUMERO_NOVO
    assert not ContactPoint.objects.filter(value_normalized=NUMERO_ANTIGO).exists()
    assert not CustomerIdentifier.objects.filter(identifier_value=NUMERO_ANTIGO).exists()

    ignorar = {"phone", "code_expires_at"}
    antigo = _pedir_codigo(cliente, NUMERO_ANTIGO)
    nunca_visto = _pedir_codigo(cliente, NUMERO_NUNCA_VISTO)
    assert antigo.status_code == nunca_visto.status_code == 200
    assert {k: v for k, v in antigo.json().items() if k not in ignorar} == {
        k: v for k, v in nunca_visto.json().items() if k not in ignorar
    }

    estranho = _entrar_por_otp(cliente, NUMERO_ANTIGO)
    assert estranho["customer_ref"] != customer.ref
    cliente.logout()

    dona = _entrar_por_otp(cliente, NUMERO_NOVO)
    assert dona["customer_ref"] == customer.ref


def test_corrigir_o_email_no_balcao_tira_o_antigo_da_porta():
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.services.verification import AuthService

    from shopman.storefront.tests.identity_fakes import CapturingSender

    assert AuthService.request_code(EMAIL_ANTIGO, delivery_method="email", sender=CapturingSender()).success
    entrada = AuthService.verify_for_login(EMAIL_ANTIGO, _last_code())
    assert entrada.success, entrada.error
    customer = Customer.objects.get(uuid=entrada.customer.subject_id)
    Customer.objects.filter(pk=customer.pk).update(first_name="Ana", last_name="Prado")

    resolve_or_create_customer(
        ref=customer.ref, email=EMAIL_NOVO, contact_correction=True, operator_username="op",
    )

    customer.refresh_from_db()
    assert customer.email == EMAIL_NOVO
    assert not ContactPoint.objects.filter(value_normalized=EMAIL_ANTIGO).exists()
    assert not CustomerIdentifier.objects.filter(identifier_value=EMAIL_ANTIGO).exists()
    assert get_adapter().resolve_identity("email", EMAIL_ANTIGO, purpose="login") is None
    assert str(get_adapter().resolve_identity("email", EMAIL_NOVO, purpose="login").subject_id) == str(customer.uuid)
