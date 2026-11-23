"""Quem vê a foto do entregador da corrida (#3150, decisão do dono em 22/11).

A foto é dado pessoal do entregador, guardada só em cache e só enquanto a
corrida vive (LGPD, decisão de 13/11). Até aqui só o Gestor a via (quem
gerencia pedidos ou expede). O dono decidiu que o Caixa também vê, no painel da
corrida do PDV. A porta continua fechada para quem não opera nenhuma das duas
telas, e a foto continua presa à corrida viva.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

pytestmark = pytest.mark.django_db

RIDE = "776753357"
URL = f"/api/v1/backstage/deliveries/{RIDE}/driver-photo/"
PHOTO = (b"\x89PNG-foto", "image/png")


def _login(client, *codenames: str):
    user = get_user_model().objects.create_user(username="pessoa", password="x", is_staff=True)
    for code in codenames:
        app_label, codename = code.split(".")
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    client.force_login(user)
    return user


def _get(client, photo=PHOTO):
    with mock.patch("shopman.shop.services.courier.driver_photo", return_value=photo) as served:
        response = client.get(URL)
    return response, served


# Quem opera o caixa (o novo, #3150), quem gerencia pedidos e quem expede (a Saída).
@pytest.mark.parametrize("codename", ["cashman.operate_pos", "shop.manage_orders", "backstage.operate_kds"])
def test_o_caixa_e_o_gestor_veem_a_foto_da_corrida_viva(client, codename):
    _login(client, codename)

    response, served = _get(client)

    assert response.status_code == 200
    assert response.content == PHOTO[0]
    assert response["Content-Type"] == "image/png"
    # O navegador também não guarda (a foto some com a corrida).
    assert response["Cache-Control"] == "no-store"
    served.assert_called_once_with(RIDE)


@pytest.mark.parametrize("codenames", [(), ("shop.manage_catalog",), ("craftsman.view_workorder",)])
def test_quem_nao_opera_o_caixa_nem_o_gestor_nao_ve(client, codenames):
    """Staff sem nenhuma das telas da corrida, o Catálogo e a Produção: porta fechada."""
    _login(client, *codenames)

    response, served = _get(client)

    assert response.status_code in (401, 403)
    served.assert_not_called()


def test_anonimo_nao_ve(client):
    response, served = _get(client)

    assert response.status_code in (401, 403)
    served.assert_not_called()


def test_corrida_encerrada_nao_tem_foto_nem_para_o_caixa(client):
    _login(client, "cashman.operate_pos")

    response, _ = _get(client, photo=None)

    assert response.status_code == 404
