"""A tela de Configuração só mostra o que a pessoa abre (beta test 05/11/2026, ADM-06).

Como Gerente, "Usuários", "Grupos" e "Referências" levavam a um 403 cru, sem
layout e sem saída, e a contagem dizia "46 telas" como se todas abrissem. A
porta de cada cartão é a mesma do menu e do dashboard (``admin.gates``).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import RequestFactory

from shopman.backstage.projections.settings_hub import build_settings_hub
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def gerente():
    call_command("setup_groups")
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("gerente-config", password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name="Gerente"))
    return User.objects.get(pk=user.pk)


def _labels(hub) -> set[str]:
    return {card["label"] for group in hub["groups"] for card in group["cards"]}


def _request(user):
    request = RequestFactory().get("/admin/settings/")
    request.user = user
    return request


def test_gerente_nao_ve_cartao_que_responde_403(gerente):
    assert not gerente.has_perm("auth.view_user")
    labels = _labels(build_settings_hub(request=_request(gerente)))
    assert "Usuários" not in labels
    assert "Grupos" not in labels


def test_contagem_e_a_da_pessoa(gerente):
    dono = User.objects.create_superuser("dono-config", password="pw")
    da_gerente = build_settings_hub(request=_request(gerente))
    do_dono = build_settings_hub(request=_request(dono))
    assert da_gerente["total"] < do_dono["total"]
    assert da_gerente["total"] == len(_labels(da_gerente))
    assert {"Usuários", "Grupos"} <= _labels(do_dono)


def test_porta_trancada_tem_layout_e_saida(client, gerente):
    """O endereço antigo ainda dá 403, mas com a casa em volta e o caminho de volta."""
    client.force_login(gerente)
    response = client.get("/admin/auth/user/")
    assert response.status_code == 403
    body = response.content.decode()
    assert "Sem acesso a esta tela" in body
    assert 'href="/admin/"' in body
    assert "Voltar ao início" in body


def test_tela_de_configuracao_da_gerente_nao_leva_a_403(client, gerente):
    client.force_login(gerente)
    response = client.get("/admin/settings/")
    assert response.status_code == 200
    hub = response.context["settings_hub"]
    for group in hub["groups"]:
        for card in group["cards"]:
            assert client.get(card["url"]).status_code != 403, card["label"]
