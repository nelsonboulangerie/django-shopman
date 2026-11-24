"""O cadastro do cliente diz "É da equipe: <operador>" (decisão do dono, 24/11/2026, #3437).

A marca mora em ``Customer.metadata["team_operator_id"]`` e é o que
``experience.operator_customer_refs`` lê para a coorte interna da versão de teste
da loja. O campo é composto pelo orquestrador sobre o Admin do Guestman.
"""

from __future__ import annotations

import json

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.test import Client
from shopman.guestman.models import Customer

from shopman.backstage.admin.customer_team import FIELD, install_customer_team_link
from shopman.shop.services.experience import TEAM_OPERATOR_KEY, operator_customer_refs

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _loja():
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")


def _operador(username: str, *, first_name: str = "", group: str = "Caixa") -> User:
    user = User.objects.create_user(username=username, first_name=first_name, is_staff=True)
    user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


def _gestor() -> Client:
    client = Client()
    client.force_login(User.objects.create_superuser("gestor", "gestor@example.com", "senha-local"))
    return client


def _url(customer: Customer) -> str:
    return f"/admin/guestman/customer/{customer.pk}/change/"


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
            if isinstance(value, dict):
                value = json.dumps(value)
            data[form.add_prefix(name)] = value
    return data


def _salvar(client: Client, customer: Customer, **campos) -> None:
    tela = client.get(_url(customer))
    assert tela.status_code == 200
    data = _form_data(tela)
    data.update(campos)
    resposta = client.post(_url(customer), data)
    if resposta.status_code != 302 and resposta.context:
        pytest.fail(f"o Admin recusou: {resposta.context['adminform'].form.errors}")
    assert resposta.status_code == 302


def test_o_campo_aparece_na_secao_equipe_so_com_operadores_ativos():
    _operador("fran", first_name="Fran")
    User.objects.create_user(username="customer_qualquer")  # conta de cliente da loja
    inativo = _operador("ana", first_name="Ana")
    inativo.is_active = False
    inativo.save()
    customer = Customer.objects.create(ref="CLI-1", first_name="Fran")

    tela = _gestor().get(_url(customer))

    assert tela.status_code == 200
    form = tela.context["adminform"].form
    escolhas = [label for _value, label in form.fields[FIELD].choices]
    assert escolhas == ["Não é da equipe", "Fran (fran)"]
    titulos = [fieldset.name for fieldset in tela.context["adminform"]]
    assert titulos.index("Equipe") == titulos.index("Segmentação") + 1
    assert "É da equipe" in tela.content.decode()


def test_marcar_grava_no_metadata_e_a_pessoa_entra_na_coorte():
    fran = _operador("fran", first_name="Fran")
    customer = Customer.objects.create(ref="CLI-FRAN", first_name="Fran", metadata={"house_account": True})

    _salvar(_gestor(), customer, **{FIELD: str(fran.pk)})

    customer.refresh_from_db()
    assert customer.metadata[TEAM_OPERATOR_KEY] == fran.pk
    assert customer.metadata["house_account"] is True
    assert operator_customer_refs() == frozenset({"CLI-FRAN"})


def test_desmarcar_tira_a_chave():
    fran = _operador("fran")
    customer = Customer.objects.create(ref="CLI-FRAN", first_name="Fran", metadata={TEAM_OPERATOR_KEY: fran.pk})

    _salvar(_gestor(), customer, **{FIELD: ""})

    customer.refresh_from_db()
    assert TEAM_OPERATOR_KEY not in customer.metadata
    assert operator_customer_refs() == frozenset()


def test_operador_desligado_continua_marcado_ao_salvar_outro_campo():
    """Salvar o cadastro por outro motivo não apaga a marca calado; ela só não vale."""
    diofer = _operador("diofer", first_name="Diofer", group="Cozinha")
    customer = Customer.objects.create(ref="CLI-DIOFER", first_name="Diofer", metadata={TEAM_OPERATOR_KEY: diofer.pk})
    diofer.is_active = False
    diofer.save()
    gestor = _gestor()

    tela = gestor.get(_url(customer))
    form = tela.context["adminform"].form
    assert form[FIELD].value() == diofer.pk
    assert "Diofer (diofer), desligado" in [label for _v, label in form.fields[FIELD].choices]

    _salvar(gestor, customer, last_name="Silva")

    customer.refresh_from_db()
    assert customer.last_name == "Silva"
    assert customer.metadata[TEAM_OPERATOR_KEY] == diofer.pk
    assert operator_customer_refs() == frozenset()


def test_conta_que_nao_e_operador_e_recusada():
    conta = User.objects.create_user(username="customer_qualquer")
    customer = Customer.objects.create(ref="CLI-1", first_name="Ana")
    gestor = _gestor()
    data = _form_data(gestor.get(_url(customer)))
    data[FIELD] = str(conta.pk)

    resposta = gestor.post(_url(customer), data)

    assert resposta.status_code == 200
    assert FIELD in resposta.context["adminform"].form.errors
    customer.refresh_from_db()
    assert TEAM_OPERATOR_KEY not in customer.metadata


def test_instalar_de_novo_nao_empilha():
    antes = type(admin.site._registry[Customer])
    install_customer_team_link()
    assert type(admin.site._registry[Customer]) is antes
