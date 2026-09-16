"""Os PADRÕES do cliente nascem junto com o cadastro novo.

No modal do cliente do PDV os dois interruptores (CPF na nota / nota por
e-mail) aparecem também para quem ainda não tem cadastro. Sem ref não há
perfil para gravar, então o rascunho viaja no "Cadastrar cliente": o resolve
aceita ``fiscal_prefs`` e persiste em ``Customer.metadata["fiscal_prefs"]``
pelo MESMO escritor do endpoint de perfil (``_merge_fiscal_prefs``) — mesma
validação, mesma escrita, chave a chave.

O gravador passivo do fechamento (``_remember_fiscal_prefs``) só LIGA; o
explícito diz o valor, e vem depois dele.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Shift
from shopman.guestman.models import Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos import (
    resolve_or_create_customer,
    update_pos_customer_profile,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def _pdv():
    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})


def _prefs(ref: str) -> dict:
    return dict((Customer.objects.get(ref=ref).metadata or {}).get("fiscal_prefs") or {})


def test_cadastro_novo_nasce_com_os_padroes_virados(_pdv):
    result = resolve_or_create_customer(
        name="Outra Pessoa",
        phone="43999990033",
        fiscal_prefs={"cpf_na_nota": True, "email_receipt": False},
        operator_username="op",
    )

    assert result["created"] is True
    assert _prefs(result["ref"]) == {"cpf_na_nota": True, "email_receipt": False}


def test_sem_fiscal_prefs_o_cadastro_novo_nao_ganha_a_chave(_pdv):
    result = resolve_or_create_customer(name="Outra Pessoa", phone="43999990033", operator_username="op")

    assert result["created"] is True
    assert "fiscal_prefs" not in (Customer.objects.get(ref=result["ref"]).metadata or {})


def test_o_valor_e_sempre_bool_e_so_as_chaves_conhecidas_entram(_pdv):
    result = resolve_or_create_customer(
        name="Outra Pessoa",
        phone="43999990033",
        fiscal_prefs={"cpf_na_nota": "sim", "imprimir": True},
        operator_username="op",
    )

    assert _prefs(result["ref"]) == {"cpf_na_nota": True}


def test_o_mesmo_escritor_do_perfil_desliga_o_que_o_cadastro_ligou(_pdv):
    """Perfil e resolve gravam pela mesma função: um desliga o que o outro ligou."""
    result = resolve_or_create_customer(
        name="Outra Pessoa",
        phone="43999990033",
        fiscal_prefs={"cpf_na_nota": True},
        operator_username="op",
    )
    assert _prefs(result["ref"]) == {"cpf_na_nota": True}

    update_pos_customer_profile(customer_ref=result["ref"], payload={"fiscal_prefs": {"cpf_na_nota": False}})

    assert _prefs(result["ref"]) == {"cpf_na_nota": False}


def test_fiscal_prefs_malformado_e_recusado_antes_de_gravar(_pdv):
    with pytest.raises(ValueError, match="fiscal_prefs inválido."):
        resolve_or_create_customer(
            name="Outra Pessoa",
            phone="43999990033",
            fiscal_prefs=["cpf_na_nota"],
            operator_username="op",
        )

    assert Customer.objects.count() == 0


def test_cliente_existente_pelo_resolve_tambem_aceita_o_padrao(_pdv):
    """O front só manda sem ref; o servidor não depende disso para ser coerente."""
    customer = Customer.objects.create(
        ref=Customer.generate_ref(),
        first_name="Ana",
        last_name="Prado",
        phone="+5543999990011",
        metadata={"fiscal_prefs": {"email_receipt": True}},
    )

    resolve_or_create_customer(
        ref=customer.ref,
        name="Ana Prado",
        fiscal_prefs={"cpf_na_nota": True},
        operator_username="op",
    )

    assert _prefs(customer.ref) == {"email_receipt": True, "cpf_na_nota": True}


# ── A porta HTTP: o mesmo 400 nomeado do endpoint de perfil ──────────────────


@pytest.fixture
def _operator_client(client, _pdv):
    user = get_user_model().objects.create_user(username="pos-padroes", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
    client.force_login(user)
    return client


def _post(client, payload: dict):
    return client.post(
        "/api/v1/backstage/pos/customer/resolve/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_a_view_grava_os_padroes_e_devolve_o_lookup_com_eles(_operator_client):
    response = _post(
        _operator_client,
        {
            "customer_name": "Outra Pessoa",
            "customer_phone": "43999990033",
            "fiscal_prefs": {"cpf_na_nota": True},
        },
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["created"] is True
    assert body["customer"]["fiscal_prefs"] == {"cpf_na_nota": True}
    assert _prefs(body["customer"]["ref"]) == {"cpf_na_nota": True}


def test_a_view_recusa_fiscal_prefs_malformado_com_400_e_campo_nomeado(_operator_client):
    response = _post(
        _operator_client,
        {
            "customer_name": "Outra Pessoa",
            "customer_phone": "43999990033",
            "fiscal_prefs": "sim",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "fiscal_prefs inválido.", "field": "fiscal_prefs"}
    assert Customer.objects.count() == 0
