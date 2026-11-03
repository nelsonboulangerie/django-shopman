"""Caixa do PDV: a trava do PIN do gerente arma, o comprovante é da gaveta da
estação e valor que não é número finito é valor inválido.

Achados da auditoria adversarial do caixa (03/11/2026). O PIN errado era gravado
pelo ``PinCredential`` dentro da transação da mutação, e a recusa desfazia o
registro junto: a força bruta do PIN do gerente pela sangria não travava nunca.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import Permission, User
from shopman.cashman import services as cash
from shopman.cashman.models import Terminal
from shopman.doorman.models import PinCredential

from shopman.backstage.tests.pos_test_runtime import bind_station

pytestmark = pytest.mark.django_db

BASE = "/api/v1/backstage"


def _user(name, *perms):
    u = User.objects.create_user(name, password="pw", is_staff=True)
    for codename in perms:
        u.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=u.pk)


@pytest.fixture
def setup(client):
    Terminal.objects.all().update(is_active=False)
    t1 = Terminal.objects.create(ref="balcao-1", label="Balcão 1", is_active=True)
    t2 = Terminal.objects.create(ref="balcao-2", label="Balcão 2", is_active=True)
    op = _user("op-audit", "operate_pos")
    mgr = _user("mgr-audit", "operate_pos", "adjust_shift")
    PinCredential.set_for(mgr, "4321")
    s1 = cash.open_shift(operator=op, terminal=t1, float_q=10000)
    s2 = cash.open_shift(operator=op, terminal=t2, float_q=10000)
    client.force_login(op)
    bind_station(client, t1.ref)
    return {"t1": t1, "t2": t2, "op": op, "mgr": mgr, "s1": s1, "s2": s2}


def _post(client, path, body):
    body = {**body, "client_request_id": str(uuid.uuid4())}
    return client.post(BASE + path, data=json.dumps(body), content_type="application/json")


def test_pin_errado_na_sangria_conta_tentativa(client, setup):
    """Brute force do PIN do gerente pela sangria: a falha precisa ficar gravada."""
    mgr = setup["mgr"]
    max_attempts = PinCredential.objects.get(user=mgr).max_attempts
    for i in range(max_attempts + 2):
        r = _post(client, "/pos/cash/movement/", {
            "kind": "sangria", "amount": "10,00", "reason": "cofre", "terminal_ref": "balcao-1",
            "manager_approval": {"username": mgr.username, "pin": f"{i:04d}"},
        })
        assert r.status_code in (400, 403, 409, 422), r.content
    cred = PinCredential.objects.get(user=mgr)
    assert cred.attempts >= max_attempts, f"tentativas gravadas={cred.attempts}"
    assert cred.is_locked
    # e o PIN certo agora é recusado (travado)
    r = _post(client, "/pos/cash/movement/", {
        "kind": "sangria", "amount": "10,00", "reason": "cofre", "terminal_ref": "balcao-1",
        "manager_approval": {"username": mgr.username, "pin": "4321"},
    })
    assert r.status_code != 200, "PIN certo passou depois de N+2 erros: a trava nunca armou"


def test_pin_errado_no_atendimento_de_troco_conta_tentativa(setup):
    """serve_change_request é @transaction.atomic: a falha do PIN é revertida junto."""
    from shopman.backstage.services import pos as pos_service
    from shopman.shop.services.pos import PosIntentError

    mgr = setup["mgr"]
    req = pos_service.request_change(operator=setup["op"], amount_raw="50", terminal_ref="balcao-1")
    for i in range(3):
        with pytest.raises(PosIntentError):
            pos_service.serve_change_request(
                operator=setup["op"], request_ref=str(req.pk),
                manager_approval={"username": mgr.username, "pin": f"{i:04d}"}, terminal_ref="balcao-1",
            )
    assert PinCredential.objects.get(user=mgr).attempts == 3


def test_comprovante_de_outra_gaveta_nao_sai_por_query_param(client, setup):
    """Estação do balcão 1 tira (e reimprime) o comprovante da sangria do balcão 2."""
    entry = cash.record(
        "cash_out", shift=setup["s2"], operator=setup["op"], approved_by=setup["mgr"],
        amount_q=-5000, reason="cofre",
    )
    r = client.get(f"{BASE}/pos/cash/entry/{entry.pk}/receipt/?terminal_ref=balcao-2")
    assert r.status_code >= 400, f"vazou o comprovante da outra gaveta: {r.status_code}"


def test_valor_nan_no_acerto_de_conta_nao_vira_500(client, setup):
    r = _post(client, "/pos/accounts/CLI-1/settle/", {"amount": "NaN", "method": "cash", "terminal_ref": "balcao-1"})
    assert r.status_code < 500, r.status_code


def test_pin_certo_depois_de_erros_zera_o_contador_e_lanca(client, setup):
    """O veredito conferido fora da transação vale para a mutação: uma conferência só."""
    mgr = setup["mgr"]
    for i in range(2):
        _post(client, "/pos/cash/movement/", {
            "kind": "sangria", "amount": "10,00", "reason": "cofre", "terminal_ref": "balcao-1",
            "manager_approval": {"username": mgr.username, "pin": f"{i:04d}"},
        })
    assert PinCredential.objects.get(user=mgr).attempts == 2
    r = _post(client, "/pos/cash/movement/", {
        "kind": "sangria", "amount": "10,00", "reason": "cofre", "terminal_ref": "balcao-1",
        "manager_approval": {"username": mgr.username, "pin": "4321"},
    })
    assert r.status_code == 200, r.content
    assert PinCredential.objects.get(user=mgr).attempts == 0


@pytest.mark.parametrize("raw", ["NaN", "nan", "Infinity", "-Infinity", "sNaN"])
def test_valor_que_nao_e_numero_finito_e_valor_invalido(raw):
    from shopman.backstage.services.pos import POSError, parse_money_to_q

    with pytest.raises(POSError, match="Valor inválido."):
        parse_money_to_q(raw)
