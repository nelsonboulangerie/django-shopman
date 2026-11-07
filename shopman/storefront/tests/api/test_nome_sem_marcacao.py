"""O nome do cliente não aceita `<` nem `>` (beta 06/11).

`Bia <img src=x onerror=…>` era aceito como nome e seguia para o ticket da cozinha,
a notificação e o Admin. Recusar com o campo apontado, em vez de limpar calado,
deixa a pessoa ver o que precisa corrigir.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def titular() -> Customer:
    return Customer.objects.create(ref="CUS-NOME-01", first_name="Bia", phone="+5543988883333")


def _login(client: Client, customer: Customer) -> None:
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    from shopman.storefront.tests.identity_fakes import make_identity_view

    info = make_identity_view(
        subject_id=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def _patch(client: Client, **payload):
    return client.patch(
        "/api/v1/account/profile/",
        data=json.dumps(payload),
        content_type="application/json",
    )


@pytest.mark.parametrize("nome", ["Bia <img src=x onerror=alert(1)>", "Bia >", "<b>Bia"])
def test_primeiro_nome_com_marcacao_e_recusado_no_campo(client: Client, titular: Customer, nome: str):
    _login(client, titular)

    resposta = _patch(client, first_name=nome)

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["field"] == "first_name"
    assert corpo["errors"]["first_name"] == [corpo["detail"]]
    assert "<" in corpo["detail"] and ">" in corpo["detail"]
    titular.refresh_from_db()
    assert titular.first_name == "Bia"


def test_sobrenome_com_marcacao_e_recusado_no_campo(client: Client, titular: Customer):
    _login(client, titular)

    resposta = _patch(client, first_name="Bia", last_name="Souza <script>")

    assert resposta.status_code == 400
    assert resposta.json()["field"] == "last_name"
    titular.refresh_from_db()
    assert titular.last_name in ("", None)


def test_nome_de_gente_continua_passando(client: Client, titular: Customer):
    _login(client, titular)

    resposta = _patch(client, first_name="Maria José", last_name="D'Ávila-Souza")

    assert resposta.status_code == 200, resposta.content
    titular.refresh_from_db()
    assert titular.first_name == "Maria José"
    assert titular.last_name == "D'Ávila-Souza"
