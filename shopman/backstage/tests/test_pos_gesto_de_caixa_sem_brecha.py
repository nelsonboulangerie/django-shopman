"""WP-E6 do plano de excelência do PDV: gesto de caixa sem brecha.

- P1-9: erro de caixa chegava cru ao balcão (``str(exc)`` com 400 para QUALQUER
  exceção) e o ``sale/close`` falava fora do dialeto ``{detail, field, errors}``
  (#2347). Recusa de negócio fala a frase do serviço; falha do sistema é 500 com a
  frase do gesto, e o texto da exceção fica no log.
- P1-5: repetir o gesto com outra assinatura do gerente é o MESMO lançamento.
- P2-12: a Caixa, errando o PIN do gerente, travava quem autoriza.
- P2-13: os atalhos gravavam no terminal que o corpo escolhesse.
"""

from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential

from shopman.backstage.tests.pos_test_runtime import bind_station

pytestmark = pytest.mark.django_db

BASE = "/api/v1/backstage"
PIN = "4321"


def _user(name: str, *codenames: str) -> User:
    user = User.objects.create_user(name, password="pw", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def balcao(client):
    from shopman.backstage.services import pos as pos_service

    Terminal.objects.all().update(is_active=False)
    Terminal.objects.create(ref="balcao", label="Balcão", is_active=True)
    fran = _user("fran-e6", "operate_pos")
    joyce = _user("joyce-e6", "operate_pos", "adjust_shift")
    PinCredential.set_for(joyce, PIN)
    bind_station(client, "balcao")
    pos_service.open_cash_shift(operator=fran, opening_amount_raw="500,00", terminal_ref="balcao")
    client.force_login(fran)
    return {"client": client, "fran": fran, "joyce": joyce}


def _post(client, path: str, body: dict, *, chave: str | None = None):
    corpo = {**body, "client_request_id": chave or f"pos-cash:{uuid.uuid4()}"}
    return client.post(BASE + path, data=json.dumps(corpo), content_type="application/json")


def _saida(valor: str = "50,00", **extra) -> dict:
    return {"kind": "sangria", "amount": valor, "reason": "Depósito", **extra}


# ── P1-9: o dialeto do caixa ─────────────────────────────────────────────────


def test_falha_do_sistema_nao_chega_crua_ao_balcao(balcao, monkeypatch):
    from shopman.backstage.services import pos as pos_service

    def quebra(**_kwargs):
        raise KeyError("SELECT * FROM cashman_entry -- segredo")

    monkeypatch.setattr(pos_service, "register_cash_movement", quebra)
    resposta = _post(balcao["client"], "/pos/cash/movement/", _saida(manager_approval={
        "username": "joyce-e6", "pin": PIN}))
    assert resposta.status_code == 500
    corpo = resposta.json()
    assert corpo["detail"] == "O sistema não conseguiu registrar o movimento no livro-caixa."
    assert corpo["error"]["code"] == "cash_system_error"
    assert "segredo" not in resposta.content.decode()
    assert "cashman_entry" not in resposta.content.decode()


def test_recusa_de_negocio_fala_a_frase_do_servico(balcao):
    resposta = _post(balcao["client"], "/pos/cash/movement/", _saida(valor="abc", manager_approval={
        "username": "joyce-e6", "pin": PIN}))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Valor inválido."


def test_pedido_de_gerente_sai_com_campo_no_topo(balcao):
    resposta = _post(balcao["client"], "/pos/cash/movement/", _saida())
    corpo = resposta.json()
    assert corpo["error"]["code"] == "manager_approval_required"
    assert corpo["field"] == "manager_approval"
    assert corpo["errors"] == {"manager_approval": [corpo["detail"]]}


def test_tipo_de_movimento_invalido_nomeia_o_campo(balcao):
    resposta = _post(balcao["client"], "/pos/cash/movement/", {"kind": "outro", "amount": "1,00"})
    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["detail"] == "Escolha entrada ou saída de caixa."
    assert corpo["field"] == "kind"
    assert corpo["errors"] == {"kind": ["Escolha entrada ou saída de caixa."]}


def test_tentativa_sem_chave_nomeia_o_campo(balcao):
    resposta = balcao["client"].post(
        BASE + "/pos/cash/movement/", data=json.dumps(_saida()), content_type="application/json",
    )
    assert resposta.status_code == 422
    assert resposta.json()["field"] == "client_request_id"


# ── #2347: sale/close no dialeto ─────────────────────────────────────────────


def test_fechar_venda_sem_revisao_da_comanda_fala_o_dialeto(balcao):
    resposta = balcao["client"].post(
        # Com a chave da tentativa (#2565): o que este teste prova é a revisão da comanda.
        BASE + "/pos/sale/close/", data=json.dumps({"tab_ref": "00001007", "client_request_id": "pos-revisao-1"}),
        content_type="application/json",
    )
    assert resposta.status_code == 422
    corpo = resposta.json()
    assert corpo["error"]["code"] == "tab_revision_required"
    assert corpo["field"] == "expected_revision"
    assert corpo["errors"] == {"expected_revision": [corpo["detail"]]}


def test_recusa_do_intent_no_fechamento_sobe_o_campo(balcao):
    resposta = balcao["client"].post(
        BASE + "/pos/sale/close/",
        data=json.dumps({"client_request_id": "x" * 300, "items": []}),
        content_type="application/json",
    )
    corpo = resposta.json()
    assert resposta.status_code >= 400
    assert isinstance(corpo["detail"], str) and corpo["detail"]
    campo = corpo["error"].get("field")
    assert campo, corpo
    assert corpo["field"] == campo
    assert corpo["errors"][campo] == [corpo["detail"]]


# ── P1-5: a assinatura não muda o gesto ──────────────────────────────────────


def test_repetir_com_outra_assinatura_grava_uma_vez(balcao):
    """Rede cortada depois de gravar: o toque seguinte, sem gerente ou com outro, é replay."""
    chave = f"pos-cash:{uuid.uuid4()}"
    assinada = _post(balcao["client"], "/pos/cash/movement/",
                     _saida(manager_approval={"username": "joyce-e6", "pin": PIN}), chave=chave)
    assert assinada.status_code == 200, assinada.content
    de_novo = _post(balcao["client"], "/pos/cash/movement/", _saida(), chave=chave)
    assert de_novo.status_code == 200, de_novo.content
    assert de_novo.json()["entry_id"] == assinada.json()["entry_id"]
    assert Entry.objects.filter(kind="cash_out", amount_q=-5000).count() == 1


# ── P2-12: quem digita o PIN errado para antes do gerente travar ─────────────


def _confere(client, pin: str):
    return client.post(
        BASE + "/pos/manager-approval/check/",
        data=json.dumps({"manager_approval": {"username": "joyce-e6", "pin": pin}}),
        content_type="application/json",
    )


def test_a_caixa_nao_trava_o_gerente_pela_conferencia(balcao):
    for tentativa in range(3):
        assert _confere(balcao["client"], f"{tentativa:04d}").status_code == 422
    barrada = _confere(balcao["client"], "0009")
    assert barrada.status_code == 429
    corpo = barrada.json()
    assert corpo["error"]["code"] == "manager_approval_throttled"
    assert corpo["field"] == "manager_approval"
    credencial = PinCredential.objects.get(user=balcao["joyce"])
    assert credencial.attempts == 3
    assert not credencial.is_locked


def test_a_caixa_nao_trava_o_gerente_pela_saida(balcao):
    for tentativa in range(3):
        resposta = _post(balcao["client"], "/pos/cash/movement/",
                         _saida(manager_approval={"username": "joyce-e6", "pin": f"{tentativa:04d}"}))
        assert resposta.json()["error"]["code"] == "manager_approval_invalid"
    barrada = _post(balcao["client"], "/pos/cash/movement/",
                    _saida(manager_approval={"username": "joyce-e6", "pin": PIN}))
    assert barrada.status_code == 429
    assert PinCredential.objects.get(user=balcao["joyce"]).attempts == 3
    assert not Entry.objects.filter(kind="cash_out").exists()


def test_o_cracha_do_gerente_nao_entra_na_conta(balcao):
    for tentativa in range(3):
        _confere(balcao["client"], f"{tentativa:04d}")
    cracha = balcao["client"].post(
        BASE + "/pos/manager-approval/check/",
        data=json.dumps({"manager_approval": {"badge": "nao-existe"}}),
        content_type="application/json",
    )
    assert cracha.status_code == 422
    assert cracha.json()["error"]["code"] == "manager_approval_invalid"


# ── P2-13: atalhos só no terminal deste dispositivo ──────────────────────────


def test_atalhos_gravam_no_terminal_da_estacao(balcao):
    from shopman.offerman.models import Collection

    Collection.objects.create(ref="doces", name="Doces")
    outro = Terminal.objects.create(ref="balcao-2", label="Balcão 2", is_active=True, metadata={})
    url = BASE + "/pos/settings/"

    alheio = balcao["client"].post(url, data=json.dumps({
        "section": "shortcuts", "terminal_ref": "balcao-2", "favorite_collection_refs": ["doces"],
    }), content_type="application/json")
    assert alheio.status_code == 400
    assert alheio.json()["field"] == "terminal_ref"
    outro.refresh_from_db()
    assert "favorite_collection_refs" not in (outro.metadata or {})

    proprio = balcao["client"].post(url, data=json.dumps({
        "section": "shortcuts", "favorite_collection_refs": ["doces"],
    }), content_type="application/json")
    assert proprio.status_code == 200, proprio.content
    assert Terminal.objects.get(ref="balcao").metadata["favorite_collection_refs"] == ["doces"]
