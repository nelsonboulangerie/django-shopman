"""A arrumação das colunas do Gestor fica lembrada por POSTO, no servidor (SUITE-UX §16, L7).

O posto é a estação confiável (``Terminal``); a arrumação mora em
``Terminal.metadata["gestor_board"]`` sem tocar nas outras chaves. Sem posto não há
de quem ser a arrumação: a leitura volta vazia e a gravação é recusada com 409.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import resolve, reverse
from shopman.cashman.models import Terminal

from shopman.backstage import station_trust
from shopman.backstage.services import order_board_layout
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

URL = "api-backstage-order-board-layout"

SAIDA = {
    "intake": {"open": False, "weight": 1},
    "prep": {"open": False, "weight": 1},
    "expedition": {"open": True, "weight": 1},
}


class _Resposta:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, nome, valor, **kw):
        self.cookies[nome] = valor

    def delete_cookie(self, nome, **kw):
        self.cookies.pop(nome, None)


def _provisiona(cliente: Client, ref: str) -> None:
    requisicao = type("R", (), {"COOKIES": dict(cliente.cookies), "META": {}})()
    resposta = _Resposta()
    station_trust.provision(requisicao, resposta, ref)
    for nome, token in resposta.cookies.items():
        cliente.cookies[nome] = token


@pytest.fixture
def operador(db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("gestor-op", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


@pytest.fixture
def passe(db):
    return Terminal.objects.create(
        ref="passe",
        label="Passe",
        metadata={"auto_lock_seconds": 90, "station": {"mode": "attended"}},
    )


@pytest.fixture
def cliente_no_posto(client, operador, passe):
    _provisiona(client, passe.ref)
    client.force_login(operador)
    return client


def test_posto_sem_arrumacao_le_vazio_e_a_tela_abre_com_as_tres(cliente_no_posto):
    resposta = cliente_no_posto.get(reverse(URL))

    assert resposta.status_code == 200
    assert resposta.json() == {"station": "passe", "columns": None}


def test_posto_saida_fica_lembrado_e_nao_apaga_o_resto_do_terminal(cliente_no_posto, passe):
    resposta = cliente_no_posto.put(reverse(URL), {"columns": SAIDA}, content_type="application/json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["columns"]["expedition"] == {"open": True, "weight": 1.0}
    passe.refresh_from_db()
    assert passe.metadata["auto_lock_seconds"] == 90
    assert passe.metadata["station"] == {"mode": "attended"}
    assert passe.metadata["gestor_board"]["columns"]["intake"]["open"] is False

    # Outra leitura (outro navegador do mesmo posto, ou depois de recarregar).
    assert cliente_no_posto.get(reverse(URL)).json()["columns"] == resposta.json()["columns"]


def test_dispositivo_que_nao_e_posto_nao_grava(client, operador):
    client.force_login(operador)

    assert client.get(reverse(URL)).json() == {"station": "", "columns": None}
    resposta = client.put(reverse(URL), {"columns": SAIDA}, content_type="application/json")
    assert resposta.status_code == 409
    assert "não é um posto" in resposta.json()["detail"]


def test_todas_recolhidas_e_recusado(cliente_no_posto, passe):
    fechadas = {zona: {"open": False, "weight": 1} for zona in order_board_layout.ZONES}

    resposta = cliente_no_posto.put(reverse(URL), {"columns": fechadas}, content_type="application/json")

    assert resposta.status_code == 400
    assert resposta.json()["field"] == "columns"
    passe.refresh_from_db()
    assert "gestor_board" not in passe.metadata


@pytest.mark.parametrize(
    "colunas",
    [
        None,
        {"intake": {"open": True, "weight": 1}},  # falta zona
        {**SAIDA, "extra": {"open": True, "weight": 1}},  # zona desconhecida
        {**SAIDA, "prep": {"open": "sim", "weight": 1}},
        {**SAIDA, "prep": {"open": False, "weight": 9}},
        {**SAIDA, "prep": {"open": False, "weight": True}},
    ],
)
def test_arrumacao_invalida_e_recusada(cliente_no_posto, colunas):
    resposta = cliente_no_posto.put(reverse(URL), {"columns": colunas}, content_type="application/json")

    assert resposta.status_code == 400


def test_guardado_corrompido_le_como_vazio(cliente_no_posto, passe):
    passe.metadata = {**passe.metadata, "gestor_board": {"columns": {"intake": "x"}}}
    passe.save(update_fields=["metadata"])

    assert cliente_no_posto.get(reverse(URL)).json()["columns"] is None


def test_sem_permissao_de_pedidos_nao_le_nem_grava(client, passe):
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("sem-perm", password="pw", is_staff=True)
    _provisiona(client, passe.ref)
    client.force_login(user)

    assert client.get(reverse(URL)).status_code == 403
    assert client.put(reverse(URL), {"columns": SAIDA}, content_type="application/json").status_code == 403


def test_rota_nao_e_engolida_pelo_detalhe_do_pedido():
    from shopman.backstage.api.operations import OrderBoardLayoutView

    assert resolve("/api/v1/backstage/orders/board-layout/").func.view_class is OrderBoardLayoutView
