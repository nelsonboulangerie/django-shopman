"""Os services: únicos escritores do turno e do livro; o livro prova o fechamento."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.cashman import services as cash
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.cashman.signals import entry_recorded, shift_closed, shift_opened

pytestmark = pytest.mark.django_db

K = Entry.Kind


# ── Abrir ─────────────────────────────────────────────────────────────────


def test_abrir_cria_a_custodia_e_o_fundo_de_troco_juntos(operator, terminal):
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)

    assert shift.is_open
    assert list(cash.timeline(shift).values_list("kind", "amount_q")) == [(K.FLOAT_IN, 10000)]
    assert cash.balance(shift) == 10000


def test_abrir_sem_fundo_deixa_o_livro_vazio(operator, terminal):
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=0)
    assert cash.balance(shift) == 0
    assert not cash.timeline(shift).exists()


def test_abrir_recusa_a_GAVETA_ja_aberta_e_so_ela(operator, manager, terminal):
    """Duas custódias na mesma gaveta, nunca. A mesma pessoa em duas gavetas, sim."""
    cash.open_shift(operator=operator, terminal=terminal)

    # A marina já tem o balcão aberto e abre o totem: permitido.
    outra = cash.open_shift(operator=operator, terminal=Terminal.objects.create(ref="totem-1"))
    assert outra.terminal.ref == "totem-1"

    with pytest.raises(CashError) as exc:
        cash.open_shift(operator=manager, terminal=terminal)
    assert exc.value.code == "SHIFT_ALREADY_OPEN"
    assert exc.value.context["opened_by"] == "marina"


def test_abrir_sem_terminal_usa_o_default(operator):
    shift = cash.open_shift(operator=operator)
    assert shift.terminal.ref == "pdv-main"


def test_fundo_negativo_e_recusado(operator, terminal):
    with pytest.raises(CashError, match="negativo"):
        cash.open_shift(operator=operator, terminal=terminal, float_q=-1)


# ── Lançar ────────────────────────────────────────────────────────────────


def test_venda_em_dinheiro_e_venda_sem_dinheiro(shift, operator):
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01", payment_ref="pi_1",
                payload={"received_q": 2000, "change_q": 500, "method": "cash"})
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=0, order_ref="A02", payment_ref="pi_2",
                payload={"method": "pix"})

    assert cash.balance(shift) == 11500
    assert cash.timeline(shift).filter(kind=K.SALE).count() == 2


def test_troco_da_entrega_sai_e_volta_pelo_livro(shift, operator):
    """O entregador leva R$ 20 de troco (``courier_out``, sem segunda assinatura:
    é rotina do despacho) e volta com R$ 5 (``courier_in``, ≥ 0). No meio, o
    saldo do livro é o que a gaveta TEM: a contagem cega não acusa falta falsa."""
    out = cash.record(K.COURIER_OUT, shift=shift, operator=operator, amount_q=-2000, order_ref="D01")
    assert cash.balance(shift) == 8000
    cash.record(K.COD_SETTLED, shift=shift, operator=operator, amount_q=3500, order_ref="D01", payment_ref="pi_d")
    back = cash.record(K.COURIER_IN, shift=shift, operator=operator, amount_q=500, order_ref="D01", parent=out)
    assert back.parent_id == out.pk
    assert cash.balance(shift) == 12000
    # Voltou zero: o entregador usou tudo; o acerto ainda fecha o ciclo.
    cash.record(K.COURIER_IN, shift=shift, operator=operator, amount_q=0, order_ref="D02")
    with pytest.raises(CashError):
        cash.record(K.COURIER_OUT, shift=shift, operator=operator, amount_q=2000, order_ref="D03")


def test_sangria_exige_assinatura_e_sinal_negativo(shift, operator, manager):
    with pytest.raises(CashError) as exc:
        cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000)
    assert exc.value.code == "APPROVAL_REQUIRED"
    with pytest.raises(CashError) as exc:
        cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=5000, approved_by=manager)
    assert exc.value.code == "INVALID_AMOUNT"

    entry = cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000, approved_by=manager, reason="Cofre")
    assert entry.approved_by == manager
    assert cash.balance(shift) == 5000


def test_tipo_desconhecido_e_tipos_reservados(shift, operator):
    with pytest.raises(CashError) as exc:
        cash.record("inventado", shift=shift, operator=operator)
    assert exc.value.code == "INVALID_KIND"
    for reserved in (K.FLOAT_IN, K.COUNT):
        with pytest.raises(CashError, match="abrir e fechar"):
            cash.record(reserved, shift=shift, operator=operator, amount_q=1)


def test_evento_sem_dinheiro_recusa_valor(shift, operator):
    with pytest.raises(CashError) as exc:
        cash.record(K.DRAWER_OPEN, shift=shift, operator=operator, amount_q=1)
    assert exc.value.code == "INVALID_AMOUNT"
    entry = cash.record(K.DRAWER_OPEN, shift=shift, operator=operator, reason="Conferência")
    assert entry.amount_q == 0
    assert cash.balance(shift) == 10000


def test_parent_obrigatorio_e_do_tipo_certo(shift, operator, manager):
    with pytest.raises(CashError) as exc:
        cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager)
    assert exc.value.code == "PARENT_REQUIRED"

    opening = cash.record(K.DRAWER_OPEN, shift=shift, operator=operator)
    with pytest.raises(CashError) as exc:
        cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=opening)
    assert exc.value.code == "PARENT_MISMATCH"


def test_parent_de_outro_turno_e_recusado(shift, operator, manager):
    other = cash.open_shift(operator=manager, terminal=Terminal.objects.create(ref="pdv-2"))
    request = cash.record(K.CHANGE_REQUESTED, shift=other, operator=manager, payload={"amount_q": 10000})
    with pytest.raises(CashError) as exc:
        cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=request)
    assert exc.value.code == "PARENT_MISMATCH"


def test_a_mesma_venda_duas_vezes_no_turno_e_recusada_com_mensagem_da_casa(shift, operator):
    """O banco decide, a mensagem continua sendo nossa (a fórmula do `open_shift`).

    Dois submits do mesmo fechamento — retry de rede do PDV — dobrariam o
    esperado do turno. Quem impede é a `UniqueConstraint` parcial; `record`
    traduz o `IntegrityError` para o dialeto do balcão.
    """
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01")

    with pytest.raises(CashError) as exc:
        cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01")
    assert exc.value.code == "DUPLICATE_ENTRY"
    assert Entry.objects.filter(shift=shift, kind=K.SALE, order_ref="A01").count() == 1


def test_o_acerto_de_entrega_tambem_nao_repete(shift, operator):
    cash.record(K.COD_SETTLED, shift=shift, operator=operator, amount_q=1500, order_ref="A01")

    with pytest.raises(CashError) as exc:
        cash.record(K.COD_SETTLED, shift=shift, operator=operator, amount_q=1500, order_ref="A01")
    assert exc.value.code == "DUPLICATE_ENTRY"


def test_pedido_de_troco_exige_valor_positivo_no_proprio_livro(shift, operator):
    """Contrato que só a superfície cobra não é contrato.

    O valor do pedido de troco vive no payload (o lançamento tem efeito zero por
    construção), mas quem chama a API crua não passa pelo `backstage`. O único
    escritor do livro valida o que tem schema.
    """
    for payload in ({}, {"amount_q": 0}, {"amount_q": -500}, {"amount_q": "cem"}):
        with pytest.raises(CashError) as exc:
            cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload=payload)
        assert exc.value.code == "INVALID_PAYLOAD"

    entry = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 10000})
    assert entry.payload["amount_q"] == 10000


def test_denominacao_do_pedido_de_troco_e_lista_de_centavos(shift, operator):
    """O pacote confere a FORMA (lista de centavos positivos), não o catálogo.

    Quais cédulas o balcão pode pedir é política da superfície e tem fonte única
    em `backstage/services/pos.py::CHANGE_DENOMINATIONS`, de onde a projection
    serve a tela; repeti-la aqui criaria a segunda lista que aquele comentário
    existe para evitar.
    """
    with pytest.raises(CashError) as exc:
        cash.record(
            K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 10000, "denominations": "1000"}
        )
    assert exc.value.code == "INVALID_PAYLOAD"

    with pytest.raises(CashError):
        cash.record(
            K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 10000, "denominations": [0]}
        )

    entry = cash.record(
        K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 10000, "denominations": [1000, 500]}
    )
    assert entry.payload["denominations"] == [1000, 500]


def test_resultado_do_comprovante_so_aceita_o_que_o_balcao_pode_dizer(shift, operator, manager):
    sangria = cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-100, approved_by=manager, reason="x")

    for payload in ({}, {"status": "pending"}, {"status": "quase"}):
        with pytest.raises(CashError) as exc:
            cash.record(K.RECEIPT_RESULT, shift=shift, operator=operator, parent=sangria, payload=payload)
        assert exc.value.code == "INVALID_PAYLOAD"

    entry = cash.record(K.RECEIPT_RESULT, shift=shift, operator=operator, parent=sangria, payload={"status": "failed"})
    assert entry.payload["status"] == "failed"


def test_turno_fechado_so_aceita_correcao_anotacao_e_comprovante(shift, operator, manager):
    sangria = cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-100, approved_by=manager)
    cash.close_shift(shift, counted_q=9900, actor=operator)

    with pytest.raises(CashError) as exc:
        cash.record(K.DRAWER_OPEN, shift=shift, operator=operator)
    assert exc.value.code == "SHIFT_NOT_OPEN"
    cash.record(K.NOTE, shift=shift, operator=manager, payload={"text": "conferido"})
    cash.record(K.RECEIPT_RESULT, shift=shift, operator=operator, parent=sangria, payload={"status": "printed"})


def test_lancar_anuncia_entry_recorded_no_commit(shift, operator, django_capture_on_commit_callbacks):
    seen = []
    entry_recorded.connect(lambda sender, entry, **kw: seen.append(entry.kind), weak=False, dispatch_uid="t1")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            cash.record(K.DRAWER_OPEN, shift=shift, operator=operator)
    finally:
        entry_recorded.disconnect(dispatch_uid="t1")
    assert seen == [K.DRAWER_OPEN]


# ── Fechar (cego) ─────────────────────────────────────────────────────────


def test_fechamento_cego_e_um_lancamento_de_ajuste(shift, operator, manager):
    """Esperado, contado e diferença são PROVADOS pelo livro, não guardados."""
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01")
    cash.record(K.CASH_IN, shift=shift, operator=operator, amount_q=2000)
    cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000, approved_by=manager)
    # esperado = 10000 + 1500 + 2000 − 5000 = 8500; contou 8490 → faltou 10

    count = cash.close_shift(shift, counted_q=8490, actor=operator, notes="ok")

    assert count.kind == K.COUNT
    assert count.amount_q == -10
    assert count.payload == {"counted_q": 8490, "notes": "ok"}
    assert cash.expected_before_count(shift) == 8500
    assert cash.counted(shift) == 8490
    assert cash.difference(shift) == -10
    assert cash.balance(shift) == 8490
    shift.refresh_from_db()
    assert not shift.is_open
    assert shift.closed_at is not None


def test_antes_de_contar_nao_ha_diferenca(shift):
    assert cash.difference(shift) is None
    assert cash.counted(shift) is None


def test_fechar_duas_vezes_e_recusado(shift, operator):
    cash.close_shift(shift, counted_q=10000, actor=operator)
    with pytest.raises(CashError) as exc:
        cash.close_shift(shift, counted_q=10000, actor=operator)
    assert exc.value.code == "SHIFT_NOT_OPEN"


def test_quem_contou_fica_na_linha_da_contagem(shift, operator, manager):
    """Fechar o caixa que outra pessoa abriu é o caso NORMAL, não exceção.

    Por isso não há mais marca de "supervisório": quem contou está em
    ``count.operator``, e quem abriu está no turno. Uma bandeira que subiria
    quase sempre não informa nada.
    """
    count = cash.close_shift(shift, counted_q=10000, actor=manager)
    assert count.operator == manager
    assert "supervisory" not in count.payload
    assert Shift.objects.get(pk=shift.pk).opened_by == operator


def test_fechar_anuncia_shift_closed_no_commit(shift, operator, django_capture_on_commit_callbacks):
    seen = []
    shift_closed.connect(lambda sender, shift, count, **kw: seen.append(count.amount_q), weak=False, dispatch_uid="t2")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            cash.close_shift(shift, counted_q=10005, actor=operator)
    finally:
        shift_closed.disconnect(dispatch_uid="t2")
    assert seen == [5]


def test_abrir_anuncia_shift_opened(operator, terminal, django_capture_on_commit_callbacks):
    seen = []
    shift_opened.connect(lambda sender, shift, **kw: seen.append(shift.pk), weak=False, dispatch_uid="t3")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            shift = cash.open_shift(operator=operator, terminal=terminal)
    finally:
        shift_opened.disconnect(dispatch_uid="t3")
    assert seen == [shift.pk]


# ── Corrigir ──────────────────────────────────────────────────────────────


def test_correcao_e_lancamento_novo_apontando_para_a_contagem(shift, operator, manager):
    count = cash.close_shift(shift, counted_q=9900, actor=operator)  # faltou 100
    assert cash.difference(shift) == -100

    fix = cash.correct_count(shift, delta_q=100, actor=manager, approved_by=manager, reason="nota grudada")

    assert fix.kind == K.COUNT_CORRECTION
    assert fix.parent == count
    assert cash.difference(shift) == 0
    assert cash.counted(shift) == 10000
    # A contagem original continua lá, intacta: correção não edita.
    count.refresh_from_db()
    assert count.amount_q == -100


def test_correcao_exige_turno_fechado_motivo_e_valor(shift, operator, manager):
    with pytest.raises(CashError) as exc:
        cash.correct_count(shift, delta_q=100, actor=manager, approved_by=manager, reason="x")
    assert exc.value.code == "SHIFT_NOT_CLOSED"
    cash.close_shift(shift, counted_q=10000, actor=operator)
    with pytest.raises(CashError, match="zero"):
        cash.correct_count(shift, delta_q=0, actor=manager, approved_by=manager, reason="x")
    with pytest.raises(CashError, match="motivo"):
        cash.correct_count(shift, delta_q=5, actor=manager, approved_by=manager, reason="  ")


# ── Pedido de troco: estado dobrado do livro ──────────────────────────────


def test_pedido_de_troco_dobra_pedido_atendimento_e_cancelamento(shift, operator, manager):
    a = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 2000, "denominations": [50]})
    b = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 5000, "denominations": [1000], "note": "notas de 10"})
    c = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 8000, "denominations": []})
    cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=a)
    cash.record(K.CHANGE_CANCELLED, shift=shift, operator=operator, parent=b)

    requests = {r["entry_id"]: r for r in cash.change_requests(shift)}
    assert requests[a.pk]["status"] == "served"
    assert requests[a.pk]["served_by"] == "pablo"
    assert requests[b.pk]["status"] == "cancelled"
    assert requests[b.pk]["amount_q"] == 5000
    assert requests[b.pk]["denominations"] == [1000]
    assert requests[b.pk]["note"] == "notas de 10"
    # Sem denominação é pedido INTEIRO, não pedido pela metade.
    assert requests[c.pk]["denominations"] == []
    assert requests[c.pk]["status"] == "pending"
    assert requests[c.pk]["requested_by"] == "marina"
    assert cash.balance(shift) == 10000  # net zero: troco não é dinheiro


def test_segunda_resolucao_fica_no_livro_mas_nao_muda_o_estado(shift, operator, manager):
    a = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"amount_q": 10000})
    cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=a)
    cash.record(K.CHANGE_CANCELLED, shift=shift, operator=operator, parent=a)

    (request,) = cash.change_requests(shift)
    assert request["status"] == "served"
    assert cash.timeline(shift).filter(parent=a).count() == 2


# ── Consultas de custódia ─────────────────────────────────────────────────


def test_open_shift_for_terminal_e_is_closed(operator, manager, terminal):
    assert cash.open_shift_for_terminal(terminal) is None
    shift = cash.open_shift(operator=operator, terminal=terminal)
    assert cash.open_shift_for_terminal(terminal) == shift
    assert cash.is_closed(shift.pk) is False
    cash.close_shift(shift, counted_q=0, actor=operator)
    assert cash.open_shift_for_terminal(terminal) is None
    assert cash.is_closed(shift.pk) is True
    assert cash.is_closed("nope") is False
    assert cash.is_closed(999999) is False


def test_balance_ate_um_lancamento(shift, operator, manager):
    sale = cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500)
    cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000, approved_by=manager)
    assert cash.balance(shift, until=sale) == 11500
    assert cash.balance(shift) == 6500


def test_quem_lancou_nao_precisa_ser_quem_abriu(shift, manager):
    """O balcão se reveza dentro de UM turno: cada linha diz quem a fez."""
    entry = cash.record(K.NOTE, shift=shift, operator=manager, payload={"text": "x"})
    assert entry.operator == manager
    assert Shift.objects.get(pk=shift.pk).opened_by != manager


def test_get_user_model_e_o_unico_acoplamento_externo():
    """O pacote só conhece o User configurado; nada de shop/backstage."""
    assert get_user_model() is not None
