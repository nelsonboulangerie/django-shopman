"""Pedido de troco sem trânsito: o dinheiro não anda, o troco vem até o balcão.

Antes o operador atravessava a loja com dinheiro até o cofre. Parte do trajeto
tem câmera, parte não — a janela clássica de desvio, com a falta aparecendo só
no fechamento, horas depois e misturada com o turno inteiro. Aqui o operador
PEDE, alguém traz, e a troca acontece no balcão, entre duas pessoas.

O pedido é linha do livro (``cashman.Entry``): ``change_requested`` com
``amount_q = 0``, e o atendimento/cancelamento é outra linha apontando para ele
por ``parent``. O estado é dobrado do livro (``cashman.services.change_requests``).

⚠️ O que este arquivo protege acima de tudo: a troca é NET ZERO. Saem R$ 50,
entram 5×R$ 10 — o total da gaveta não muda. Atender um pedido NÃO pode mexer no
saldo do livro. Já aconteceu o contrário (Troco entrou como motivo de sangria,
PR #178): o esperado caía por um dinheiro que nunca saiu e o turno fechava com
falta fantasma.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift
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


def _requests(operator) -> list[dict]:
    return cash.change_requests(cash.open_shift_for(operator))


# ── Pedir ─────────────────────────────────────────────────────────────────


def test_pedir_troco_grava_quem_o_que_e_quando(operator):
    entry = pos_service.request_change(
        operator=operator, amount_raw="100,00", denominations=[50, 25]
    )

    assert entry.kind == Entry.Kind.CHANGE_REQUESTED
    assert entry.amount_q == 0
    pedidos = _requests(operator)
    assert len(pedidos) == 1
    assert pedidos[0]["entry_id"] == entry.pk
    assert pedidos[0]["amount_q"] == 10000
    assert pedidos[0]["denominations"] == [50, 25]
    assert pedidos[0]["status"] == "pending"
    assert pedidos[0]["requested_by"] == "marina"
    assert pedidos[0]["requested_at"]


def test_o_valor_e_exato_e_vive_no_payload(operator):
    """O valor pedido é payload, nunca efeito no saldo: a linha continua zerada."""
    entry = pos_service.request_change(operator=operator, amount_raw="50,00")
    assert entry.payload["amount_q"] == 5000
    assert entry.amount_q == 0


def test_pedido_sem_valor_e_recusado(operator):
    """Sem número, quem vai buscar o troco tem de adivinhar quanto trazer.

    Era o defeito do modelo antigo: "moedas" era um pedido válido e mudo, e a
    pessoa voltava do cofre com o que achou. Agora o valor é sempre exigido.
    """
    with pytest.raises(POSError, match="valor"):
        pos_service.request_change(operator=operator, amount_raw="0")


def test_valor_sem_denominacao_e_um_pedido_completo(operator):
    """"Me traz R$ 100" basta — escolher cédula é refino, não obrigação."""
    entry = pos_service.request_change(operator=operator, amount_raw="100")
    assert entry.payload["amount_q"] == 10000
    assert entry.payload["denominations"] == []


def test_denominacao_que_nao_existe_e_recusada(operator):
    """R$ 0,03 não é um pedido, é um dedo errado — e viajaria calado ao balcão."""
    with pytest.raises(POSError, match="Denominação"):
        pos_service.request_change(operator=operator, amount_raw="10", denominations=[3])


def test_nota_grande_nao_e_troco(operator):
    """R$ 50 e R$ 100 existem; pedir troco neles é o oposto do problema."""
    with pytest.raises(POSError, match="Denominação"):
        pos_service.request_change(operator=operator, amount_raw="200", denominations=[5000])


def test_denominacoes_saem_ordenadas_e_sem_repetir(operator):
    """A lista é do maior para o menor, e o dedo trêmulo não vira dois pedidos."""
    entry = pos_service.request_change(
        operator=operator, amount_raw="100", denominations=[25, 2000, 25, 500]
    )
    assert entry.payload["denominations"] == [2000, 500, 25]


def test_pedir_sem_caixa_aberto_e_recusado():
    user = get_user_model().objects.create_user(username="sem-turno", password="x")
    with pytest.raises(POSError, match="Caixa não aberto"):
        pos_service.request_change(operator=user, amount_raw="50")


def test_pedidos_acumulam_sem_apagar_o_anterior(operator):
    pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])
    pos_service.request_change(operator=operator, amount_raw="80", denominations=[500])

    assert [p["amount_q"] for p in _requests(operator)] == [5000, 8000]
    assert [p["denominations"] for p in _requests(operator)] == [[50], [500]]


def test_pedido_e_abertura_de_gaveta_convivem_no_mesmo_livro(operator):
    """Os dois vizinhos são linhas do mesmo turno; uma não apaga a outra."""
    pos_service.register_drawer_opening(operator=operator, reason="Conferência")
    pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    shift = cash.open_shift_for(operator)
    kinds = [e.kind for e in cash.timeline(shift)]
    assert kinds == [Entry.Kind.FLOAT_IN, Entry.Kind.DRAWER_OPEN, Entry.Kind.CHANGE_REQUESTED]


# ── Atender ───────────────────────────────────────────────────────────────


def test_atender_exige_pin_de_gerente(operator):
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    with pytest.raises(PosIntentError) as exc:
        pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk))
    assert exc.value.code == "manager_approval_required"


def test_pin_de_quem_nao_e_gerente_nao_atende(operator):
    """O balconista não assina a própria exceção — é a segunda assinatura que vale."""
    PinCredential.set_for(operator, "1111")
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    with pytest.raises(PosIntentError) as exc:
        pos_service.serve_change_request(
            operator=operator,
            request_ref=str(entry.pk),
            manager_approval=_approval("marina", "1111"),
        )
    assert exc.value.code == "manager_approval_invalid"


def test_atender_grava_quem_atendeu_e_quando(operator, manager):
    entry = pos_service.request_change(operator=operator, amount_raw="80", denominations=[500])

    served = pos_service.serve_change_request(
        operator=operator, request_ref=str(entry.pk), manager_approval=_approval()
    )

    # A linha de atendimento aponta para o pedido e leva a segunda assinatura.
    assert served.kind == Entry.Kind.CHANGE_SERVED
    assert served.parent_id == entry.pk
    assert served.approved_by == manager
    pedido = _requests(operator)[0]
    assert pedido["status"] == "served"
    assert pedido["served_by"] == "pablo"
    assert pedido["served_at"]
    # As duas assinaturas: quem pediu continua gravado ao lado de quem atendeu.
    assert pedido["requested_by"] == "marina"


def test_atender_duas_vezes_diz_que_ja_foi_resolvido(operator, manager):
    """Duas pessoas na mesma tela: o segundo toque precisa explicar, não confundir."""
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])
    pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk), manager_approval=_approval())

    with pytest.raises(POSError, match="já foi resolvido"):
        pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk), manager_approval=_approval())


def test_atender_pedido_inexistente_e_recusado(operator, manager):
    with pytest.raises(POSError, match="não encontrado"):
        pos_service.serve_change_request(operator=operator, request_ref="nao-existe", manager_approval=_approval())
    with pytest.raises(POSError, match="não encontrado"):
        pos_service.serve_change_request(operator=operator, request_ref="999999", manager_approval=_approval())


def test_pedido_de_outro_turno_nao_e_atendido_daqui(operator, manager):
    """O ``ref`` é id de linha, mas só do livro DO OPERADOR: turno alheio não resolve."""
    other = get_user_model().objects.create_user(username="outro", password="x", is_staff=True)
    from shopman.cashman.models import Terminal

    other_shift = cash.open_shift(
        operator=other, terminal=Terminal.objects.create(ref="pos-2", label="POS 2"), float_q=0
    )
    alheio = cash.record(Entry.Kind.CHANGE_REQUESTED, shift=other_shift, operator=other, payload={"kind": "coins"})

    with pytest.raises(POSError, match="não encontrado"):
        pos_service.serve_change_request(operator=operator, request_ref=str(alheio.pk), manager_approval=_approval())


# ── ⚠️ A regra que não pode ser violada: NET ZERO ─────────────────────────


def test_atender_pedido_nao_altera_o_saldo_do_livro(operator, manager):
    """A prova da feature: trocar dinheiro NÃO muda o total da gaveta.

    Saem R$ 50, entram 5×R$ 10. Se atender lançasse valor, o esperado do
    fechamento cairia por um dinheiro que nunca saiu e o turno fecharia com falta
    fantasma — exatamente o defeito que o PR #178 desfez quando "Troco" era
    motivo de sangria. Este teste falha se alguém reintroduzir isso.
    """
    shift = cash.open_shift_for(operator)
    saldo_antes = cash.balance(shift)

    entry = pos_service.request_change(operator=operator, amount_raw="50,00")
    pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk), manager_approval=_approval())

    assert cash.balance(shift) == saldo_antes
    assert not Entry.objects.filter(shift=shift, kind__in=[Entry.Kind.CASH_OUT, Entry.Kind.CASH_IN]).exists()


def test_fechamento_cego_nao_sente_o_pedido_de_troco(operator, manager):
    """A prova pelo fechamento: o esperado sai igual com e sem pedido atendido."""
    entry = pos_service.request_change(operator=operator, amount_raw="50,00")
    pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk), manager_approval=_approval())

    shift = cash.open_shift_for(operator)
    cash.close_shift(shift, counted_q=10000, actor=operator)

    # Fundo 100,00, zero vendas, zero movimentos → esperado 100,00 e sem
    # diferença. Um lançamento escondido no pedido apareceria aqui como falta.
    assert cash.expected_before_count(shift) == 10000
    assert cash.difference(shift) == 0


def test_cancelar_tambem_nao_mexe_no_saldo(operator):
    shift = cash.open_shift_for(operator)
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])
    cancelled = pos_service.cancel_change_request(operator=operator, request_ref=str(entry.pk))

    assert cancelled.kind == Entry.Kind.CHANGE_CANCELLED
    assert cancelled.parent_id == entry.pk
    assert cancelled.amount_q == 0
    assert cash.balance(shift) == 10000


# ── Cancelar ──────────────────────────────────────────────────────────────


def test_cancelar_tira_o_pedido_da_tela_sem_apagar_a_trilha(operator):
    """Achou troco na gaveta: o pendente some da tela, mas o registro fica."""
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    pos_service.cancel_change_request(operator=operator, request_ref=str(entry.pk))

    shift = cash.open_shift_for(operator)
    assert pos_service.pending_change_requests(shift) == []
    pedido = _requests(operator)[0]
    assert pedido["status"] == "cancelled"
    assert pedido["cancelled_at"]
    # A trilha é o livro: pedido e cancelamento continuam lá, em ordem.
    assert Entry.objects.filter(shift=shift, kind=Entry.Kind.CHANGE_REQUESTED).count() == 1
    assert Entry.objects.filter(shift=shift, kind=Entry.Kind.CHANGE_CANCELLED).count() == 1


# ── Projection ────────────────────────────────────────────────────────────


def test_o_pendente_chega_a_antesala_pelo_cash_runtime(operator):
    entry = pos_service.request_change(
        operator=operator, amount_raw="50,00", denominations=[1000], note="notas de 10"
    )

    runtime = build_pos(operator=operator).cash_runtime
    assert len(runtime.pending_change_requests) == 1
    pedido = runtime.pending_change_requests[0]
    # O ``ref`` da tela é o id da linha: é por ele que a tela atende e cancela.
    assert pedido.ref == str(entry.pk)
    assert pedido.denominations == (1000,)
    assert pedido.amount_display == "R$ 50,00"
    assert pedido.note == "notas de 10"
    assert pedido.requested_by == "marina"


def test_o_valor_pedido_chega_formatado_a_tela(operator):
    """Quem vai buscar o troco lê um número, não um adjetivo."""
    pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    pedido = build_pos(operator=operator).cash_runtime.pending_change_requests[0]
    assert pedido.amount_display == "R$ 50,00"
    assert pedido.denominations == (50,)


def test_atendido_sai_da_tela(operator, manager):
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])
    pos_service.serve_change_request(operator=operator, request_ref=str(entry.pk), manager_approval=_approval())

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
        data={"amount": "20", "denominations": [50, 25], "note": "acabou moeda de 50 centavos"},
        content_type="application/json",
    )

    assert response.status_code == 200
    ref = response.json()["request_ref"]
    pedido = _requests(operator)[0]
    assert str(pedido["entry_id"]) == ref
    assert pedido["note"] == "acabou moeda de 50 centavos"


def test_endpoint_de_atender_sem_pin_devolve_o_codigo_do_desafio(client, operator):
    """A tela precisa do CÓDIGO para abrir o diálogo de PIN, não de um toast mudo."""
    _grant(operator, "operate_pos")
    client.force_login(operator)
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    response = client.post(
        reverse("api-backstage-pos-change-request-serve", args=[str(entry.pk)]),
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
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    response = client.post(
        reverse("api-backstage-pos-change-request-serve", args=[str(entry.pk)]),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )

    assert response.status_code == 200
    shift = cash.open_shift_for(operator)
    assert _requests(operator)[0]["status"] == "served"
    # ⚠️ Net zero também pelo endpoint: o saldo do livro não mexeu.
    assert cash.balance(shift) == 10000


def test_endpoint_de_cancelar_resolve(client, operator):
    _grant(operator, "operate_pos")
    client.force_login(operator)
    entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    response = client.post(
        reverse("api-backstage-pos-change-request-cancel", args=[str(entry.pk)]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert _requests(operator)[0]["status"] == "cancelled"


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
        entry = pos_service.request_change(operator=operator, amount_raw="50", denominations=[50])

    assert enviados, "o pedido de troco precisa deixar sinal no canal de alertas"
    kind, event_type, payload = enviados[-1]
    assert (kind, event_type) == ("alerts", "backstage-alerts-update")
    assert payload["type"] == "change_request"
    assert payload["ref"] == str(entry.pk)
    assert payload["denominations"] == [50]
    assert payload["status"] == "pending"
    assert payload["requested_by"] == "marina"
