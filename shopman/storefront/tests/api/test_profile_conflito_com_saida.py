"""Trocar o e-mail para um que já é de outro cliente: motivo, campo e SAÍDA.

O beco: a view capturava ``except Exception``, descartava a mensagem real e
devolvia "Não foi possível atualizar seu perfil agora. Tente novamente." O
cliente tentava de novo, e de novo, e nunca descobria que o problema era o
e-mail — a informação existia (``ContactAlreadyTaken``) e era jogada fora.

⚠️ E a metade mais delicada: a recusa NÃO pode dizer de quem é o e-mail. O PDV
diz, e deve — é superfície de operador. A loja é superfície de CLIENTE: nomear o
dono para quem digitou um endereço qualquer é vazar dado pessoal de terceiro.
A loja diz que o e-mail não está disponível e oferece caminho.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.models import ContactPoint, Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer: Customer) -> None:
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


def _patch_profile(client: Client, **payload):
    return client.patch(
        "/api/v1/account/profile/",
        data=json.dumps(payload),
        content_type="application/json",
    )


@pytest.fixture
def titular() -> Customer:
    return Customer.objects.create(
        ref="CUS-PERFIL-01", first_name="Ana", phone="+5543988881111", email="ana@exemplo.com"
    )


@pytest.fixture
def dona_do_email() -> Customer:
    return Customer.objects.create(
        ref="CUS-PERFIL-02",
        first_name="Beatriz",
        last_name="Tamura",
        phone="+5543988882222",
        email="beatriz@exemplo.com",
    )


def test_email_de_outro_cadastro_recusa_com_campo_e_motivo(client, titular, dona_do_email):
    _login_as_customer(client, titular)

    resp = _patch_profile(client, first_name="Ana", email="beatriz@exemplo.com")

    assert resp.status_code == 409
    body = resp.json()
    assert body["field"] == "email"
    assert body["detail"] == "Este e-mail já está em uso em outra conta."
    assert body["errors"]["email"] == [body["detail"]]
    assert body["error_code"] == "contact_already_taken"
    # A recusa genérica de antes não pode voltar por nenhuma porta.
    assert "Tente novamente" not in body["detail"]

    titular.refresh_from_db()
    assert titular.email == "ana@exemplo.com"


def test_recusa_nao_vaza_a_identidade_do_dono(client, titular, dona_do_email):
    """A prova de privacidade: nada no corpo diz QUEM tem o e-mail."""
    _login_as_customer(client, titular)

    resp = _patch_profile(client, first_name="Ana", email="beatriz@exemplo.com")
    corpo = json.dumps(resp.json(), ensure_ascii=False)

    assert "Beatriz" not in corpo
    assert "Tamura" not in corpo
    assert dona_do_email.ref not in corpo
    assert dona_do_email.phone not in corpo
    # O e-mail digitado é do próprio solicitante — ele acabou de mandá-lo. O que
    # não pode aparecer é o cadastro por trás dele. `candidates` é a chave que o
    # PDV usa para nomear os dois lados; na loja ela não existe.
    assert "candidates" not in corpo


def test_recusa_oferece_entrar_e_falar_com_a_padaria(client, titular, dona_do_email):
    from shopman.shop.models import Shop

    shop = Shop.load() or Shop.objects.create(name="Padaria do Teste")
    shop.social_links = ["https://wa.me/554333231997"]
    shop.save(update_fields=["social_links"])

    _login_as_customer(client, titular)
    body = _patch_profile(client, first_name="Ana", email="beatriz@exemplo.com").json()

    refs = [action["ref"] for action in body["actions"]]
    assert refs == ["sign_in_with_email", "contact_whatsapp"]

    entrar = body["actions"][0]
    assert entrar["href"].startswith("/entrar")
    assert entrar["label"] == "Entrar com esse e-mail"

    padaria = body["actions"][1]
    assert padaria["href"] == "https://wa.me/554333231997"
    assert padaria["label"] == "Falar com a padaria"


def test_trocar_o_proprio_email_funciona_de_ponta_a_ponta(client, titular):
    """A troca legítima passa — e passa pelo Core (`set_as_primary`), sem violar UNIQUE."""
    _login_as_customer(client, titular)

    resp = _patch_profile(client, first_name="Ana", email="ana.nova@exemplo.com")

    assert resp.status_code == 200
    assert resp.json()["email"] == "ana.nova@exemplo.com"

    titular.refresh_from_db()
    assert titular.email == "ana.nova@exemplo.com"

    primarios = ContactPoint.objects.filter(
        customer=titular, type=ContactPoint.Type.EMAIL, is_primary=True
    )
    assert primarios.count() == 1
    assert primarios.first().value_normalized == "ana.nova@exemplo.com"


def test_promover_um_email_que_o_proprio_cliente_ja_tinha_como_secundario(client, titular):
    """O caso que o caminho antigo quebrava.

    Renomear o ContactPoint primário no lugar esbarrava no UNIQUE global quando o
    cliente já tinha aquele valor como contato secundário — e a violação saía
    como "não foi possível atualizar seu perfil agora". Pelo Core, é só uma
    promoção.
    """
    ContactPoint.objects.create(
        customer=titular,
        type=ContactPoint.Type.EMAIL,
        value_normalized="ana.antiga@exemplo.com",
        value_display="ana.antiga@exemplo.com",
        is_primary=False,
    )
    _login_as_customer(client, titular)

    resp = _patch_profile(client, first_name="Ana", email="ana.antiga@exemplo.com")

    assert resp.status_code == 200
    titular.refresh_from_db()
    assert titular.email == "ana.antiga@exemplo.com"
    primario = ContactPoint.objects.get(
        customer=titular, type=ContactPoint.Type.EMAIL, is_primary=True
    )
    assert primario.value_normalized == "ana.antiga@exemplo.com"
