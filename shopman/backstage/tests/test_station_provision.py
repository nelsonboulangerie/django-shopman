"""Como um dispositivo VIRA uma estação — e por que isso não pode ser fácil demais.

Sem este caminho nada do resto existe: o gate da estação é a chave da antessala,
e isto é quem entrega a chave. Um dispositivo não provisionado não tem antessala, o
balcão amanhece pedindo senha de gestor, e a loja não abre com PIN.

O ato é de gestão e acontece uma vez por dispositivo: alguém com
``cashman.manage_operators`` entra com senha ali e diz "este computador é o
pdv-main". Depois disso, o cookie responde por ele.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman.models import Shift, Terminal
from shopman.doorman.models import SubjectType, TrustedDevice

from shopman.backstage import station_trust
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

STATION_URL = "/api/v1/backstage/operator/station/"
POS_URL = "/api/v1/backstage/pos/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def terminal():
    return Terminal.objects.create(ref="pdv-main", label="PDV principal")


@pytest.fixture
def gerente(terminal):
    user = get_user_model().objects.create_user("marina", password="x", is_staff=True)
    return _grant(user, "manage_operators", "operate_pos")


def test_o_gerente_transforma_o_dispositivo_em_estacao(client, gerente, terminal):
    """O caminho da montagem do balcão, inteiro."""
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 200
    assert resposta.json()["station"] == terminal.ref
    assert TrustedDevice.objects.filter(
        subject_type=SubjectType.STATION, subject_id=terminal.ref, is_active=True
    ).count() == 1
    # E o navegador saiu daqui com a chave: a antessala já o reconhece.
    sessao = client.get(reverse("api-backstage-operator-session")).json()
    assert sessao["station"] == terminal.ref


def test_a_estacao_sobrevive_a_saida_do_gerente(client, gerente, terminal):
    """O ponto inteiro: provisionar uma vez, e o balcão abrir sozinho amanhã.

    Se a confiança morresse com a sessão de quem provisionou, seria só um login
    com outro nome — e alguém teria de trazer a senha toda manhã.
    """
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    client.post(reverse("api-backstage-operator-lock"))  # o gerente sai

    sessao = client.get(reverse("api-backstage-operator-session")).json()
    assert sessao["locked"] is True
    assert sessao["operator"] is None
    assert sessao["station"] == terminal.ref
    # ...e a estação sozinha continua não autorizando nada.
    assert client.get(POS_URL).status_code == 403


def test_quem_nao_gere_operadores_nao_provisiona(client, terminal):
    """Provisionar é decidir que aquele dispositivo passa a pedir identificação.

    Um operador de caixa que pudesse fazê-lo transformaria o próprio celular numa
    estação da loja — e a chave da antessala sairia pela porta no fim do turno.
    """
    caixa = _grant(
        get_user_model().objects.create_user("joyce", password="x", is_staff=True), "operate_pos"
    )
    client.force_login(caixa)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 403
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_terminal_desconhecido_e_recusado(client, gerente):
    """Confiança gravada para um ref que não existe passa no gate e lê a gaveta errada.

    O dispositivo seria reconhecido, o `Terminal.default()` assumiria, e o balcão
    estaria operando a gaveta de outro — sem nenhum sintoma até o fechamento.
    """
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": "pdv-fantasma"}, content_type="application/json"
    )

    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "terminal_unknown"
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_terminal_inativo_e_recusado(client, gerente, terminal):
    terminal.is_active = False
    terminal.save(update_fields=["is_active"])
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 400


def test_a_tela_de_provisionamento_ve_o_estado_e_as_opcoes(client, gerente, terminal):
    Terminal.objects.create(ref="pdv-2", label="Balcão do fundo")
    client.force_login(gerente)

    antes = client.get(STATION_URL).json()
    assert antes["station"] == ""
    assert [t["ref"] for t in antes["terminals"]] == ["pdv-2", "pdv-main"]

    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert client.get(STATION_URL).json()["station"] == terminal.ref


def test_revogar_mata_a_confianca_no_banco(client, gerente, terminal):
    """Tirar o cookie não basta: um token copiado antes continuaria valendo.

    É o caminho de quem está com a máquina na mão — desativar o quiosque que vai
    sair da loja. O dispositivo perdido continua revogável pelo Admin.
    """
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    resposta = client.delete(f"{STATION_URL}?terminal_ref={terminal.ref}")

    assert resposta.status_code == 200
    assert not TrustedDevice.objects.filter(
        subject_type=SubjectType.STATION, is_active=True
    ).exists()


def test_provisionar_duas_vezes_nao_polui_a_auditoria(client, gerente, terminal):
    """Abrir a tela de novo no mesmo dispositivo não cria um segundo dispositivo."""
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert TrustedDevice.objects.filter(subject_type=SubjectType.STATION).count() == 1


def test_um_dispositivo_ja_provisionado_nao_precisa_de_gerente_para_pedir_PIN(client, terminal):
    """O contrapeso do gate: `manage_operators` guarda o PROVISIONAMENTO, não o uso.

    Se guardasse o uso, a antessala exigiria gerente e a loja não abriria — que é
    o defeito que este arranjo inteiro existe para evitar.
    """
    trust_station(client, terminal.ref)

    sessao = client.get(reverse("api-backstage-operator-session"))

    assert sessao.status_code == 200
    assert sessao.json()["station"] == terminal.ref
    assert station_trust.PROVISION_PERM == "cashman.manage_operators"
