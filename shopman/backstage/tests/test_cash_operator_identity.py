"""O livro registra a PESSOA, não o computador.

Com ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR`` ligado (o valor do staging vivo), o
balcão inteiro roda numa sessão da conta do APARELHO — ``admin`` — e quem opera
se identifica por PIN ou crachá. O gate da API já usava o operador ativo para
AUTORIZAR; o subsistema de caixa continuava recebendo ``request.user``.

Resultado medido antes do conserto: a Joyce abria o turno, digitava o valor,
escolhia o motivo e autorizava, e a linha saía ``op=admin appr=joyce``. Além da
autoria errada, ``Shift.operator`` era sempre a mesma conta, e aí a
``UniqueConstraint`` "um turno aberto por operador" virava "um por loja" — não
existia troca de custódia entre turnos.

⚠️ Os testes vizinhos (``test_pos_cash_service``, ``test_api_operator_pin``)
passavam porque rodam com a flag DESLIGADA, onde ``request.user`` É quem opera.
A asserção que faltava é esta: com a flag ligada, o nome no livro é o do
operador identificado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
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
def aparelho(client):
    """A conta do balcão: é ela que tem a sessão do Django, como no staging."""
    device = get_user_model().objects.create_user("admin", password="x", is_staff=True)
    device = _grant(device, "operate_pos", "adjust_shift")
    client.force_login(device)
    return device


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


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_o_turno_nasce_no_nome_de_quem_se_identificou(client, aparelho, joyce, terminal):
    _identifica(client, joyce)

    resposta = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    shift = Shift.objects.get(pk=resposta.json()["shift_id"])
    assert shift.operator == joyce, "o turno saiu no nome do aparelho"
    # O fundo de troco é a primeira linha do livro, e ela tem dono também.
    float_in = Entry.objects.get(shift=shift, kind=Entry.Kind.FLOAT_IN)
    assert float_in.operator == joyce


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_a_sangria_sai_com_quem_fez_e_com_quem_autorizou(client, aparelho, joyce, gerente, terminal):
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


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
def test_a_custodia_troca_de_dono_entre_turnos(client, aparelho, joyce, terminal):
    """Sem isto, "um turno aberto por operador" era "um por loja".

    A segunda pessoa a assumir o balcão levava o beco: a constraint achava um
    turno aberto do ``admin`` e recusava, porque toda abertura era do ``admin``.
    """
    outro = _grant(get_user_model().objects.create_user("fran", password="x", is_staff=True), "operate_pos")
    PinCredential.set_for(outro, PIN_CAIXA)

    _identifica(client, joyce)
    abertura = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )
    assert abertura.status_code == 200, abertura.content
    fechamento = client.post(
        reverse("api-backstage-pos-cash-close"),
        {"closing_amount": "100,00"},
        content_type="application/json",
    )
    assert fechamento.status_code == 200, fechamento.content

    _identifica(client, outro)
    segunda = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "50,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert segunda.status_code == 200, segunda.content
    assert Shift.objects.get(pk=segunda.json()["shift_id"]).operator == outro
    assert set(Shift.objects.values_list("operator__username", flat=True)) == {"joyce", "fran"}


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
def test_sem_a_flag_a_conta_da_sessao_continua_decidindo(client, aparelho, terminal):
    """A estação pessoal (o PC do gestor) não tem operador ativo, e continua valendo."""
    resposta = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    assert Shift.objects.get(pk=resposta.json()["shift_id"]).operator == aparelho
