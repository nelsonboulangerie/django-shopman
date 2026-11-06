"""Integrações na visão só leitura da Gerente (beta test 05/11/2026, ADM-08).

Sem permissão de editar, os campos que só existem no form (as chaves de
``Shop.integrations``/``Shop.defaults``) saíam com o nome cru ("Integrations
payment pix") e sem valor; o custo das mensagens saía com ponto decimal e o
plural não flexionava ("1 pessoas").
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.urls import reverse

from shopman.shop.admin.shop import _people
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def gerente_client(client):
    call_command("setup_groups")
    user = User.objects.create_user("gerente-integracoes", password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name="Gerente"))
    client.force_login(user)
    return client


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Loja",
        integrations={"payment": {"pix": "shopman.shop.adapters.payment_mock"}},
    )


def test_gerente_le_os_rotulos_do_form_e_nao_o_nome_cru(gerente_client, shop):
    response = gerente_client.get(reverse("admin:shop_shopintegrations_change", args=[shop.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Integrations payment pix" not in body
    assert "Defaults marketing" not in body
    assert "Provedor de PIX" in body


def test_custo_em_reais_e_copy_sem_jargao(gerente_client, shop):
    body = gerente_client.get(
        reverse("admin:shop_shopintegrations_change", args=[shop.pk])
    ).content.decode()
    assert not re.search(r"R\$ \d+\.\d{2}\b", body)
    assert "Sobreescreve" not in body
    assert "deployment (settings" not in body
    assert not re.search(r"\b1 pessoas\b", body)


def test_plural_de_pessoas():
    assert _people(1) == "1 pessoa"
    assert _people(0) == "0 pessoas"
    assert _people(12) == "12 pessoas"
