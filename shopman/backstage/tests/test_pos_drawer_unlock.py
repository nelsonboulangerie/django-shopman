"""A trava da gaveta tem UMA porta: o destrave com PIN de gerente, e ele fica no livro.

A trava é do PDV (é a página que lê o sensor pelo agente do balcão; o servidor
não alcança). O servidor só entra no destrave, para registrar quem liberou, para
quem, quando, e o que o sensor disse. Regras decididas e não reabertas: trava
ao INICIAR a venda; sem carência; só quando SABE; cada destrave vale UMA venda.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential

from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def operator():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    cash.open_shift(operator=user, float_q=10000)
    return user


@pytest.fixture
def manager():
    user = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(user, "adjust_shift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


def _approval(username: str = "pablo", pin: str = MANAGER_PIN) -> dict:
    return {"username": username, "pin": pin}


def _unlocks(operator):
    return list(Entry.objects.filter(shift=cash.open_shift_for_terminal(Terminal.default()), kind=Entry.Kind.DRAWER_UNLOCK))


def test_o_destrave_exige_pin_de_gerente(operator):
    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator)
    assert exc.value.code == "manager_approval_required"
    assert _unlocks(operator) == []


def test_o_balconista_nao_destrava_a_propria_gaveta(operator):
    PinCredential.set_for(operator, "1111")
    with pytest.raises(PosIntentError) as exc:
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval("marina", "1111"))
    assert exc.value.code == "manager_approval_invalid"


def test_o_destrave_fica_no_livro_com_quem_liberou_e_o_que_o_sensor_disse(operator, manager):
    entry = pos_service.unlock_drawer(operator=operator, manager_approval=_approval(), drawer_raw="0x12")

    assert entry.kind == Entry.Kind.DRAWER_UNLOCK
    assert entry.amount_q == 0  # efeito zero: a gaveta não mudou de saldo
    assert entry.operator == operator
    assert entry.approved_by == manager
    assert entry.payload == {"drawer_raw": "0x12"}
    assert cash.balance(entry.shift) == 10000


def test_destravar_sem_caixa_aberto_e_recusado(manager):
    user = get_user_model().objects.create_user(username="sem-turno", password="x")
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.unlock_drawer(operator=user, manager_approval=_approval())


def test_cada_destrave_e_uma_linha_porque_cada_um_e_uma_venda(operator, manager):
    """Sem carência e sem liberação "até fechar": três liberações são três
    linhas. É a contagem por operador e por horário que o B.I. lê."""
    for _ in range(3):
        pos_service.unlock_drawer(operator=operator, manager_approval=_approval())
    assert len(_unlocks(operator)) == 3


def test_o_destrave_esta_no_contrato_de_acoes(operator):
    refs = {a.ref for a in build_pos(operator=operator).actions}
    assert "drawer_unlock" in refs


def test_endpoint_exige_permissao_de_operar_pdv(client):
    user = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(user)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_endpoint_sem_pin_devolve_o_codigo_do_desafio(client, operator):
    """A tela precisa do CÓDIGO para abrir o diálogo de PIN, não de um toast mudo."""
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(reverse("api-backstage-pos-cash-drawer-unlock"), data={}, content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"


def test_endpoint_com_pin_registra_e_devolve_ok(client, operator, manager):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-pos-cash-drawer-unlock"),
        data={"manager_approval": _approval(), "drawer_raw": "0x12"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    (entry,) = _unlocks(operator)
    assert entry.approved_by == manager
    assert entry.payload["drawer_raw"] == "0x12"
