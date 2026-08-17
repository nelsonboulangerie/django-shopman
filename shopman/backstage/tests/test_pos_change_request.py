"""Pedido de troco sem trânsito: o dinheiro não anda, o troco vem até o balcão.

Antes o operador atravessava a loja com dinheiro até o cofre. Parte do trajeto
tem câmera, parte não — a janela clássica de desvio, com a falta aparecendo só
no fechamento, horas depois e misturada com o turno inteiro. Aqui o operador
PEDE, alguém traz, e a troca acontece no balcão, entre duas pessoas.

⚠️ O que este arquivo protege acima de tudo: a troca é NET ZERO. Saem R$ 50,
entram 5×R$ 10 — o total da gaveta não muda. Atender um pedido NÃO pode criar
``CashMovement`` nem mexer no esperado do fechamento. Já aconteceu o contrário
(Troco entrou como motivo de sangria, PR #178): o esperado caía por um dinheiro
que nunca saiu e o turno fechava com falta fantasma.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.models import CashShift, POSTerminal
from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(CashShift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def operator():
    user = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    CashShift.objects.create(terminal=POSTerminal.default(), operator=user, opening_amount_q=10000)
    return user


@pytest.fixture
def manager():
    user = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(user, "adjust_cashshift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


def _approval(username: str = "pablo", pin: str = MANAGER_PIN) -> dict:
    return {"username": username, "pin": pin}


# ── Pedir ─────────────────────────────────────────────────────────────────


def test_pedir_troco_grava_quem_o_que_e_quando(operator):
    entry = pos_service.request_change(operator=operator, kind="coins")

    shift = CashShift.get_open_for_operator(operator)
    pedidos = shift.metadata["change_requests"]
    assert len(pedidos) == 1
    assert pedidos[0]["ref"] == entry["ref"]
    assert pedidos[0]["kind"] == "coins"
    assert pedidos[0]["status"] == "pending"
    assert pedidos[0]["requested_by"] == "marina"
    assert pedidos[0]["requested_at"]


def test_pedido_por_valor_aproximado_guarda_centavos(operator):
    entry = pos_service.request_change(operator=operator, kind="amount", amount_raw="50,00")
    assert entry["amount_q"] == 5000


def test_pedido_por_valor_sem_valor_e_recusado(operator):
    """"Me traz um valor" sem número não diz nada a quem vai buscar o troco."""
    with pytest.raises(POSError, match="valor"):
        pos_service.request_change(operator=operator, kind="amount", amount_raw="0")


def test_falta_de_moeda_nao_precisa_de_valor(operator):
    """"Acabou moeda" já é um pedido inteiro — exigir número travaria a fila."""
    entry = pos_service.request_change(operator=operator, kind="coins")
    assert entry["amount_q"] == 0


def test_tipo_desconhecido_e_recusado(operator):
    with pytest.raises(POSError, match="inválido"):
        pos_service.request_change(operator=operator, kind="ouro")


def test_pedir_sem_caixa_aberto_e_recusado():
    user = get_user_model().objects.create_user(username="sem-turno", password="x")
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.request_change(operator=user, kind="coins")


def test_pedidos_acumulam_sem_apagar_o_anterior(operator):
    pos_service.request_change(operator=operator, kind="coins")
    pos_service.request_change(operator=operator, kind="small_bills")

    pedidos = CashShift.get_open_for_operator(operator).metadata["change_requests"]
    assert [p["kind"] for p in pedidos] == ["coins", "small_bills"]


def test_a_lista_tem_teto_para_um_botao_repetido_nao_inchar_o_turno(operator):
    shift = CashShift.get_open_for_operator(operator)
    shift.metadata = {
        "change_requests": [{"ref": f"r{i}", "kind": "coins", "status": "served"} for i in range(50)]
    }
    shift.save(update_fields=["metadata"])

    pos_service.request_change(operator=operator, kind="small_bills")

    pedidos = CashShift.get_open_for_operator(operator).metadata["change_requests"]
    assert len(pedidos) == 50
    assert pedidos[-1]["kind"] == "small_bills"


def test_pedido_nao_apaga_a_trilha_de_abertura_de_gaveta(operator):
    """Os dois vizinhos moram no mesmo JSONField; escrever um não pode zerar o outro."""
    pos_service.register_drawer_opening(operator=operator, reason="Conferência")
    pos_service.request_change(operator=operator, kind="coins")

    metadata = CashShift.get_open_for_operator(operator).metadata
    assert len(metadata["drawer_openings"]) == 1
    assert len(metadata["change_requests"]) == 1


# ── Atender ───────────────────────────────────────────────────────────────


def test_atender_exige_pin_de_gerente(operator):
    entry = pos_service.request_change(operator=operator, kind="coins")

    with pytest.raises(PosIntentError) as exc:
        pos_service.serve_change_request(operator=operator, request_ref=entry["ref"])
    assert exc.value.code == "manager_approval_required"


def test_pin_de_quem_nao_e_gerente_nao_atende(operator):
    """O balconista não assina a própria exceção — é a segunda assinatura que vale."""
    PinCredential.set_for(operator, "1111")
    entry = pos_service.request_change(operator=operator, kind="coins")

    with pytest.raises(PosIntentError) as exc:
        pos_service.serve_change_request(
            operator=operator,
            request_ref=entry["ref"],
            manager_approval=_approval("marina", "1111"),
        )
    assert exc.value.code == "manager_approval_invalid"


def test_atender_grava_quem_atendeu_e_quando(operator, manager):
    entry = pos_service.request_change(operator=operator, kind="small_bills")

    pos_service.serve_change_request(
        operator=operator, request_ref=entry["ref"], manager_approval=_approval()
    )

    pedido = CashShift.get_open_for_operator(operator).metadata["change_requests"][0]
    assert pedido["status"] == "served"
    assert pedido["served_by"] == "pablo"
    assert pedido["served_at"]
    # As duas assinaturas: quem pediu continua gravado ao lado de quem atendeu.
    assert pedido["requested_by"] == "marina"


def test_atender_duas_vezes_diz_que_ja_foi_resolvido(operator, manager):
    """Duas pessoas na mesma tela: o segundo toque precisa explicar, não confundir."""
    entry = pos_service.request_change(operator=operator, kind="coins")
    pos_service.serve_change_request(
        operator=operator, request_ref=entry["ref"], manager_approval=_approval()
    )

    with pytest.raises(POSError, match="já foi resolvido"):
        pos_service.serve_change_request(
            operator=operator, request_ref=entry["ref"], manager_approval=_approval()
        )


def test_atender_pedido_inexistente_e_recusado(operator, manager):
    with pytest.raises(POSError, match="não encontrado"):
        pos_service.serve_change_request(
            operator=operator, request_ref="nao-existe", manager_approval=_approval()
        )


# ── ⚠️ A regra que não pode ser violada: NET ZERO ─────────────────────────


def test_atender_pedido_nao_cria_movimento_nem_altera_o_esperado(operator, manager):
    """A prova da feature: trocar dinheiro NÃO muda o total da gaveta.

    Saem R$ 50, entram 5×R$ 10. Se atender criasse ``CashMovement``, o
    ``expected_amount_q`` do fechamento cairia por um dinheiro que nunca saiu e o
    turno fecharia com falta fantasma — exatamente o defeito que o PR #178
    desfez quando "Troco" era motivo de sangria. Este teste falha se alguém
    reintroduzir isso.
    """
    shift = CashShift.get_open_for_operator(operator)
    esperado_antes = shift.expected_amount_q
    abertura_antes = shift.opening_amount_q

    entry = pos_service.request_change(operator=operator, kind="amount", amount_raw="50,00")
    pos_service.serve_change_request(
        operator=operator, request_ref=entry["ref"], manager_approval=_approval()
    )

    shift.refresh_from_db()
    assert shift.movements.count() == 0, "pedido de troco não é movimento de caixa"
    assert shift.expected_amount_q == esperado_antes
    assert shift.opening_amount_q == abertura_antes


def test_fechamento_cego_nao_sente_o_pedido_de_troco(operator, manager):
    """A prova pelo fechamento: o esperado sai igual com e sem pedido atendido.

    O teste acima olha o turno no meio do caminho; este roda o cálculo real de
    ``close()``, que é onde a falta fantasma apareceria para o operador.
    """
    entry = pos_service.request_change(operator=operator, kind="amount", amount_raw="50,00")
    pos_service.serve_change_request(
        operator=operator, request_ref=entry["ref"], manager_approval=_approval()
    )

    shift = CashShift.get_open_for_operator(operator)
    shift.close(blind_closing_amount_q=10000)

    shift.refresh_from_db()
    # Abertura 100,00, zero vendas, zero movimentos → esperado 100,00 e sem
    # diferença. Um lançamento escondido no pedido apareceria aqui como falta.
    assert shift.expected_amount_q == 10000
    assert shift.difference_q == 0


def test_cancelar_tambem_nao_cria_movimento(operator):
    entry = pos_service.request_change(operator=operator, kind="coins")
    pos_service.cancel_change_request(operator=operator, request_ref=entry["ref"])

    shift = CashShift.get_open_for_operator(operator)
    assert shift.movements.count() == 0
    assert shift.expected_amount_q is None


# ── Cancelar ──────────────────────────────────────────────────────────────


def test_cancelar_tira_o_pedido_da_tela_sem_apagar_a_trilha(operator):
    """Achou troco na gaveta: o pendente some da tela, mas o registro fica."""
    entry = pos_service.request_change(operator=operator, kind="coins")

    pos_service.cancel_change_request(operator=operator, request_ref=entry["ref"])

    shift = CashShift.get_open_for_operator(operator)
    assert pos_service.pending_change_requests(shift) == []
    pedido = shift.metadata["change_requests"][0]
    assert pedido["status"] == "cancelled"
    assert pedido["cancelled_at"]


# ── Projection ────────────────────────────────────────────────────────────


def test_o_pendente_chega_a_antesala_pelo_cash_runtime(operator):
    pos_service.request_change(operator=operator, kind="amount", amount_raw="50,00", note="notas de 10")

    runtime = build_pos(operator=operator).cash_runtime
    assert len(runtime.pending_change_requests) == 1
    pedido = runtime.pending_change_requests[0]
    assert pedido.kind == "amount"
    assert pedido.amount_display == "R$ 50,00"
    assert pedido.note == "notas de 10"
    assert pedido.requested_by == "marina"


def test_pedido_sem_valor_nao_mostra_zero_reais(operator):
    """"R$ 0,00" na tela pareceria pedido malformado; vazio é honesto."""
    pos_service.request_change(operator=operator, kind="coins")

    pedido = build_pos(operator=operator).cash_runtime.pending_change_requests[0]
    assert pedido.amount_display == ""


def test_atendido_sai_da_tela(operator, manager):
    entry = pos_service.request_change(operator=operator, kind="coins")
    pos_service.serve_change_request(
        operator=operator, request_ref=entry["ref"], manager_approval=_approval()
    )

    assert build_pos(operator=operator).cash_runtime.pending_change_requests == ()


def test_as_acoes_do_pedido_de_troco_estao_no_contrato(operator):
    refs = {a.ref for a in build_pos(operator=operator).actions}
    assert {"request_change", "serve_change_request", "cancel_change_request"} <= refs


# ── Endpoints ─────────────────────────────────────────────────────────────


def test_endpoints_exigem_permissao_de_operar_pdv(client):
    user = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(user)

    response = client.post(
        reverse("api-backstage-pos-change-request"),
        data={"kind": "coins"},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_endpoint_pede_troco_e_devolve_a_ref(client, operator):
    _grant(operator, "operate_pos")
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-pos-change-request"),
        data={"kind": "coins", "note": "acabou moeda de 50 centavos"},
        content_type="application/json",
    )

    assert response.status_code == 200
    ref = response.json()["request_ref"]
    pedido = CashShift.get_open_for_operator(operator).metadata["change_requests"][0]
    assert pedido["ref"] == ref
    assert pedido["note"] == "acabou moeda de 50 centavos"


def test_endpoint_de_atender_sem_pin_devolve_o_codigo_do_desafio(client, operator):
    """A tela precisa do CÓDIGO para abrir o diálogo de PIN, não de um toast mudo."""
    _grant(operator, "operate_pos")
    client.force_login(operator)
    entry = pos_service.request_change(operator=operator, kind="coins")

    response = client.post(
        reverse("api-backstage-pos-change-request-serve", args=[entry["ref"]]),
        data={},
        content_type="application/json",
    )

    # 422 é o dialeto do desafio de PIN em todo o PDV (mesmo da sangria): não é
    # "você não pode", é "falta a assinatura" — e a tela distingue pelo código.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"


def test_endpoint_de_atender_com_pin_do_gerente_resolve(client, operator, manager):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    entry = pos_service.request_change(operator=operator, kind="coins")

    response = client.post(
        reverse("api-backstage-pos-change-request-serve", args=[entry["ref"]]),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )

    assert response.status_code == 200
    shift = CashShift.get_open_for_operator(operator)
    assert shift.metadata["change_requests"][0]["status"] == "served"
    # ⚠️ Net zero também pelo endpoint: nenhuma linha de movimento nasceu aqui.
    assert shift.movements.count() == 0


def test_endpoint_de_cancelar_resolve(client, operator):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    entry = pos_service.request_change(operator=operator, kind="coins")

    response = client.post(
        reverse("api-backstage-pos-change-request-cancel", args=[entry["ref"]]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert CashShift.get_open_for_operator(operator).metadata["change_requests"][0]["status"] == "cancelled"


# ── Aviso ─────────────────────────────────────────────────────────────────


def test_o_pedido_anuncia_no_canal_de_alertas(operator, monkeypatch, django_capture_on_commit_callbacks):
    """O evento é trilha e dado para o B.I., NÃO um recado entregue.

    As superfícies de operador leem alertas por poll; quem chama o gerente numa
    padaria pequena continua sendo a voz do operador. O que se prova aqui é que
    o sinal existe e carrega o suficiente para ser contado depois.

    O publish é adiado para o COMMIT (ADR-016) — sem o `capture`, o evento nunca
    sairia dentro do teste e o assert seria mentira nas duas direções.
    """
    enviados = []
    monkeypatch.setattr(
        "shopman.shop.handlers._sse_emitters._publish_backstage",
        lambda kind, event_type, payload, scope: enviados.append((kind, event_type, payload)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        pos_service.request_change(operator=operator, kind="coins")

    assert enviados, "o pedido de troco precisa deixar sinal no canal de alertas"
    kind, event_type, payload = enviados[-1]
    assert (kind, event_type) == ("alerts", "backstage-alerts-update")
    assert payload["type"] == "change_request"
    assert payload["kind"] == "coins"
    assert payload["status"] == "pending"
    assert payload["requested_by"] == "marina"
