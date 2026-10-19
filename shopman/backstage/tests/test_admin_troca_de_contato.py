"""Editar o telefone ou o e-mail do cliente no Admin é TROCAR, não adicionar (A4-1).

Decisão da coordenação: o valor antigo deixa de autenticar. Ele sai como
contato, e a chave de login do mesmo valor sai junto (o ``post_delete`` do
contrib de identificadores, #1874). Adicionar um segundo contato continua sendo
o gesto explícito do inline de contatos.

Antes, escrever no campo e salvar caía no ``_sync_contact_points``: ou o banco
recusava dois principais, ou o número antigo ficava como contato que ainda
abria a conta por OTP.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
from shopman.guestman.models import ContactPoint, Customer

pytestmark = pytest.mark.django_db

NUMERO_ANTIGO = "+5543999996001"
NUMERO_NOVO = "+5543999996002"
NUMERO_NUNCA_VISTO = "+5543999996003"
EMAIL_ANTIGO = "ana.antiga@example.com"
EMAIL_NOVO = "ana.nova@example.com"
EMAIL_SECUNDARIO = "ana.trabalho@example.com"


@pytest.fixture(autouse=True)
def _ambiente(settings, monkeypatch):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
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


def _form_data(response) -> dict:
    """O POST que o navegador mandaria: o form do jeito que a tela o mostrou."""
    data: dict = {}
    forms = [response.context["adminform"].form]
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        forms.append(formset.management_form)
        forms.extend(formset.forms)
    for form in forms:
        for name in form.fields:
            value = form[name].value()
            if value is None or value is False:
                continue
            if value is True:
                value = "on"
            data[form.add_prefix(name)] = value
    return data


def _editar_no_admin(customer: Customer, **campos) -> None:
    gestor = Client()
    gestor.force_login(User.objects.create_superuser("gestor", "gestor@example.com", "senha-local"))
    url = f"/admin/guestman/customer/{customer.pk}/change/"
    tela = gestor.get(url)
    assert tela.status_code == 200
    data = _form_data(tela)
    data.update(campos)
    resposta = gestor.post(url, data)
    if resposta.status_code != 302 and resposta.context:
        erros = [resposta.context["adminform"].form.errors]
        erros += [inline.formset.errors for inline in resposta.context["inline_admin_formsets"]]
        pytest.fail(f"o Admin recusou: {erros}")
    assert resposta.status_code == 302


def test_trocar_o_telefone_no_admin_tira_o_numero_antigo_da_porta():
    cliente = Client()
    sessao = _entrar_por_otp(cliente, NUMERO_ANTIGO)
    customer = Customer.objects.get(ref=sessao["customer_ref"])
    Customer.objects.filter(pk=customer.pk).update(first_name="Ana")
    assert CustomerIdentifier.objects.filter(identifier_value=NUMERO_ANTIGO).exists()
    cliente.logout()

    _editar_no_admin(customer, phone=NUMERO_NOVO)

    customer.refresh_from_db()
    assert customer.phone == NUMERO_NOVO
    assert not ContactPoint.objects.filter(value_normalized=NUMERO_ANTIGO).exists()
    assert not CustomerIdentifier.objects.filter(identifier_value=NUMERO_ANTIGO).exists()

    # Pedir código para o número antigo responde igual a um número que nunca
    # existiu: nada conta que houve conta ali.
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


def test_trocar_o_email_no_admin_tira_o_antigo_e_mantem_o_secundario():
    from shopman.doorman.conf import get_adapter
    from shopman.doorman.services.verification import AuthService

    from shopman.storefront.tests.identity_fakes import CapturingSender

    assert AuthService.request_code(EMAIL_ANTIGO, delivery_method="email", sender=CapturingSender()).success
    entrada = AuthService.verify_for_login(EMAIL_ANTIGO, _last_code())
    assert entrada.success, entrada.error
    customer = Customer.objects.get(uuid=entrada.customer.subject_id)
    Customer.objects.filter(pk=customer.pk).update(first_name="Ana")
    # Um segundo e-mail adicionado de propósito: adicionar é outro gesto, e fica.
    ContactPoint.objects.create(
        customer=customer, type=ContactPoint.Type.EMAIL, value_normalized=EMAIL_SECUNDARIO,
    )

    _editar_no_admin(customer, email=EMAIL_NOVO)

    customer.refresh_from_db()
    assert customer.email == EMAIL_NOVO
    assert set(
        ContactPoint.objects.filter(customer=customer, type="email").values_list("value_normalized", "is_primary")
    ) == {(EMAIL_NOVO, True), (EMAIL_SECUNDARIO, False)}
    assert not CustomerIdentifier.objects.filter(identifier_value=EMAIL_ANTIGO).exists()
    assert get_adapter().resolve_identity("email", EMAIL_ANTIGO, purpose="login") is None
    assert str(get_adapter().resolve_identity("email", EMAIL_NOVO, purpose="login").subject_id) == str(customer.uuid)


def test_salvar_sem_mexer_no_contato_nao_troca_nada():
    customer = Customer.objects.create(ref="CUS-ADM-03", first_name="Ana", phone=NUMERO_ANTIGO)
    antes = set(ContactPoint.objects.filter(customer=customer).values_list("pk", flat=True))

    _editar_no_admin(customer, last_name="Silva")

    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO
    assert set(ContactPoint.objects.filter(customer=customer).values_list("pk", flat=True)) == antes
