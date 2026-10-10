"""A arrumação das colunas do Gestor fica lembrada por POSTO, no servidor (SUITE-UX §16, L7).

O posto é o ``Workstation`` da estação confiável; a arrumação mora em
``Workstation.metadata["gestor_board"]`` sem tocar nas outras chaves. Sem posto não há
de quem ser a arrumação: a leitura volta vazia e a gravação é recusada com 409.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import resolve, reverse
from shopman.cashman.models import Terminal

from shopman.backstage.models import Workstation
from shopman.backstage.services import order_board_layout
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

URL = "api-backstage-order-board-layout"

SAIDA = {
    "intake": {"open": False, "weight": 1},
    "prep": {"open": False, "weight": 1},
    "expedition": {"open": True, "weight": 1},
}


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
    trust_station(client, passe.ref)
    client.force_login(operador)
    return client


def test_posto_sem_arrumacao_le_vazio_e_a_tela_abre_com_as_tres(cliente_no_posto):
    resposta = cliente_no_posto.get(reverse(URL))

    assert resposta.status_code == 200
    assert resposta.json() == {"station": "passe", "columns": None}


def test_posto_saida_fica_lembrado_no_posto_e_nao_toca_o_terminal(cliente_no_posto, passe):
    resposta = cliente_no_posto.put(reverse(URL), {"columns": SAIDA}, content_type="application/json")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["columns"]["expedition"] == {"open": True, "weight": 1.0}
    posto = Workstation.objects.get(ref="passe")
    assert posto.metadata["gestor_board"]["columns"]["intake"]["open"] is False
    passe.refresh_from_db()
    assert passe.metadata == {"auto_lock_seconds": 90, "station": {"mode": "attended"}}

    # Outra leitura (outro navegador do mesmo posto, ou depois de recarregar).
    assert cliente_no_posto.get(reverse(URL)).json()["columns"] == resposta.json()["columns"]


def test_posto_sem_caixa_tambem_lembra(client, operador):
    """A Expedição não tem gaveta, e é justamente o posto que recolhe Entrada e Preparo."""
    Workstation.objects.create(ref="expedicao", label="Expedição", kind="dispatch")
    trust_station(client, "expedicao")
    client.force_login(operador)

    resposta = client.put(reverse(URL), {"columns": SAIDA}, content_type="application/json")

    assert resposta.status_code == 200, resposta.content
    assert client.get(reverse(URL)).json() == {"station": "expedicao", "columns": resposta.json()["columns"]}


def test_posto_desativado_nao_grava(cliente_no_posto):
    Workstation.objects.filter(ref="passe").update(is_active=False)

    resposta = cliente_no_posto.put(reverse(URL), {"columns": SAIDA}, content_type="application/json")

    assert resposta.status_code == 409


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
    assert resposta.json()["detail"] == "Arrumação das colunas inválida. Nada foi guardado."
    assert "gestor_board" not in Workstation.objects.get(ref="passe").metadata


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
    Workstation.objects.filter(ref="passe").update(metadata={"gestor_board": {"columns": {"intake": "x"}}})

    assert cliente_no_posto.get(reverse(URL)).json()["columns"] is None


def test_sem_permissao_de_pedidos_nao_le_nem_grava(client, passe):
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("sem-perm", password="pw", is_staff=True)
    trust_station(client, passe.ref)
    client.force_login(user)

    assert client.get(reverse(URL)).status_code == 403
    assert client.put(reverse(URL), {"columns": SAIDA}, content_type="application/json").status_code == 403


def test_rota_nao_e_engolida_pelo_detalhe_do_pedido():
    from shopman.backstage.api.operations import OrderBoardLayoutView

    assert resolve("/api/v1/backstage/orders/board-layout/").func.view_class is OrderBoardLayoutView
