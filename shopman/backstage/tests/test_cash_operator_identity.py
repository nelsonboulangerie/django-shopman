"""O livro registra a PESSOA, não o computador.

O balcão rodava numa sessão da conta do APARELHO — ``admin`` — e quem operava se
identificava por PIN ou crachá num segundo lugar. O gate da API já usava esse
operador para AUTORIZAR; o subsistema de caixa continuava recebendo
``request.user``, que era a máquina.

Resultado medido antes do conserto: a Joyce abria o turno, digitava o valor,
escolhia o motivo e autorizava, e a linha saía ``op=admin appr=joyce``. Além da
autoria errada, ``Shift.opened_by`` era sempre a mesma conta.

A D1 Parte B tirou o segundo sujeito: quem prova o PIN vira a sessão, então
``request.user`` é a pessoa e não há mais dois lugares para consultar. Estes
testes seguem valendo — e é justamente por não olharem o mecanismo, e sim o
NOME QUE SAI NO LIVRO, que eles atravessaram a troca de desenho inteiros.

⚠️ A custódia passou a ser da GAVETA em 21/08/2026: não há mais "um turno por
operador", e o balcão se reveza dentro de um turno só. O que estes testes
guardam é a AUTORIA de cada lançamento, que é o que sobrevive — e é o único
lugar onde a pergunta "quem fez isso" tem resposta.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

PIN_CAIXA = "1234"
PIN_GERENTE = "4321"


@pytest.fixture
def _loja():
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def terminal():
    return Terminal.objects.create(ref="balcao", label="Balcão")


@pytest.fixture
def balcao(client, terminal):
    """O balcão: aparelho reconhecido, e NENHUMA sessão.

    Era uma conta staff logada (``admin``) que representava a máquina. Ela some
    aqui pela mesma razão que sumiu do sistema — uma máquina com sessão é uma
    máquina com permissões, e era ela quem assinava o livro.
    """
    from shopman.backstage.tests.support import trust_station

    return trust_station(client, terminal.ref)


@pytest.fixture
def joyce():
    user = get_user_model().objects.create_user("joyce", password="x", is_staff=True)
    user = _grant(user, "operate_pos")
    PinCredential.set_for(user, PIN_CAIXA)
    return user


@pytest.fixture
def gerente():
    user = get_user_model().objects.create_user("marina", password="x", is_staff=True)
    user = _grant(user, "adjust_shift")
    PinCredential.set_for(user, PIN_GERENTE)
    return user


def _identifica(client, operator, pin=PIN_CAIXA):
    resposta = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": operator.pk, "pin": pin, "perm": "cashman.operate_pos"},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    return resposta


def test_o_turno_nasce_no_nome_de_quem_se_identificou(client, balcao, joyce, terminal):
    _identifica(client, joyce)

    resposta = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    shift = Shift.objects.get(pk=resposta.json()["shift_id"])
    assert shift.opened_by == joyce, "o turno saiu no nome do aparelho"
    # O fundo de troco é a primeira linha do livro, e ela tem dono também.
    float_in = Entry.objects.get(shift=shift, kind=Entry.Kind.FLOAT_IN)
    assert float_in.operator == joyce


def test_a_sangria_sai_com_quem_fez_e_com_quem_autorizou(client, balcao, joyce, gerente, terminal):
    """``op=joyce appr=marina``. Antes saía ``op=admin appr=marina``."""
    _identifica(client, joyce)
    client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    resposta = client.post(
        reverse("api-backstage-pos-cash-movement"),
        {
            "kind": "sangria",
            "amount": "30,00",
            "reason": "Depósito no cofre",
            "manager_approval": {"username": gerente.username, "pin": PIN_GERENTE},
        },
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    saida = Entry.objects.get(kind=Entry.Kind.CASH_OUT)
    assert saida.operator == joyce
    assert saida.approved_by == gerente


def test_o_balcao_se_reveza_DENTRO_do_mesmo_turno(client, balcao, joyce, terminal):
    """Uma gaveta, um turno, várias mãos — sem fechar e sem contar no meio.

    Este teste afirmava o contrário até 21/08/2026: fechava o caixa da Joyce
    antes de a Fran abrir o dela, e chamava isso de "troca de custódia". Era o
    modelo de custódia por PESSOA, e ele obriga uma contagem cega a cada troca
    de operador — ritual que a loja não faz e não vai fazer.

    O que sobrevive daquele teste é o que importava: cada lançamento sai no nome
    de quem o fez. Só que agora sem fechar nada.
    """
    fran = _grant(get_user_model().objects.create_user("fran", password="x", is_staff=True), "operate_pos")
    PinCredential.set_for(fran, PIN_CAIXA)

    _identifica(client, joyce)
    abertura = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )
    assert abertura.status_code == 200, abertura.content
    turno_id = abertura.json()["shift_id"]

    # A Fran assume o balcão. Nada é fechado, nada é contado.
    _identifica(client, fran)
    sangria = client.post(
        reverse("api-backstage-pos-cash-movement"),
        {"kind": "suprimento", "amount": "50,00", "reason": "troco"},
        content_type="application/json",
    )
    assert sangria.status_code == 200, sangria.content

    # UM turno só, o da gaveta, aberto pela Joyce.
    assert Shift.objects.count() == 1
    turno = Shift.objects.get(pk=turno_id)
    assert turno.is_open
    assert turno.opened_by == joyce

    # E o livro distingue as duas: cada linha tem o nome de quem a fez.
    fundo = Entry.objects.get(shift=turno, kind=Entry.Kind.FLOAT_IN)
    entrada = Entry.objects.get(shift=turno, kind=Entry.Kind.CASH_IN)
    assert fundo.operator == joyce
    assert entrada.operator == fran


def test_quem_entra_com_SENHA_tambem_assina_o_proprio_nome(client, joyce, terminal):
    """A estação pessoal — o PC do gestor — não tem PIN nem crachá, e não precisa.

    Entrar com usuário e senha é identificar-se do mesmo jeito: a sessão é da
    pessoa, e o livro sai no nome dela. Não existe um caminho "sem operador"
    onde a conta da máquina volte a assinar, porque não existe conta de máquina.
    """
    client.force_login(joyce)

    resposta = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    assert Shift.objects.get(pk=resposta.json()["shift_id"]).opened_by == joyce
