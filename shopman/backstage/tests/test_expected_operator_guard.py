"""A gravação feita em nome de quem a tela já não mostra é recusada (beta 07/11).

PDV e Cozinha no mesmo navegador dividem a sessão: a Fran destrava o PDV e passa
a operar a Cozinha ao lado, que ainda mostra a Joyce. O app manda o operador que
a tela mostra (``X-Shopman-Operator``); se a sessão é de outra pessoa, nada é
gravado. Ver ``ExpectedOperatorMiddleware``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db

WRITE = "/api/v1/backstage/kds/tickets/1/done/"


@pytest.fixture
def fran(client):
    user = User.objects.create_user("fran", password="x", is_staff=True, first_name="Fran")
    client.force_login(user)
    return user


def test_a_tela_que_mostra_outra_pessoa_nao_grava(client, fran):
    joyce = User.objects.create_user("joyce", password="x", is_staff=True, first_name="Joyce")

    response = client.post(WRITE, HTTP_X_SHOPMAN_OPERATOR=str(joyce.pk))

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "operator_changed"
    assert "Quem opera agora é Fran" in body["detail"]
    assert "Nada foi gravado" in body["detail"]


def test_a_mesma_pessoa_segue_para_a_view(client, fran):
    response = client.post(WRITE, HTTP_X_SHOPMAN_OPERATOR=str(fran.pk))

    assert response.status_code != 409


def test_sem_cabecalho_leitura_e_troca_de_pessoa_seguem(client, fran):
    assert client.post(WRITE).status_code != 409  # Admin, integrações
    assert client.get(WRITE, HTTP_X_SHOPMAN_OPERATOR="999").status_code != 409  # leitura
    lock = client.post("/api/v1/backstage/operator/lock/", HTTP_X_SHOPMAN_OPERATOR="999")
    assert lock.status_code != 409  # travar e destravar SÃO a troca
