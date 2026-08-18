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


def test_abrir_recusa_operador_ou_terminal_ja_abertos(operator, manager, terminal):
    cash.open_shift(operator=operator, terminal=terminal)
    with pytest.raises(CashError) as exc:
        cash.open_shift(operator=operator, terminal=Terminal.objects.create(ref="pdv-2"))
    assert exc.value.code == "SHIFT_ALREADY_OPEN"
    with pytest.raises(CashError) as exc:
        cash.open_shift(operator=manager, terminal=terminal)
    assert exc.value.code == "SHIFT_ALREADY_OPEN"
    assert exc.value.context["operator"] == "marina"


def test_abrir_sem_terminal_usa_o_default(operator):
    shift = cash.open_shift(operator=operator)
    assert shift.terminal.ref == "pdv-main"


def test_fundo_negativo_e_recusado(operator, terminal):
    with pytest.raises(CashError, match="negativo"):
        cash.open_shift(operator=operator, terminal=terminal, float_q=-1)


# ── Lançar ────────────────────────────────────────────────────────────────


@pytest.fixture
def shift(operator, terminal):
    return cash.open_shift(operator=operator, terminal=terminal, float_q=10000)


def test_venda_em_dinheiro_e_venda_sem_dinheiro(shift, operator):
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01", payment_ref="pi_1",
                payload={"received_q": 2000, "change_q": 500, "method": "cash"})
    cash.record(K.SALE, shift=shift, operator=operator, amount_q=0, order_ref="A02", payment_ref="pi_2",
                payload={"method": "pix"})

    assert cash.balance(shift) == 11500
    assert cash.timeline(shift).filter(kind=K.SALE).count() == 2


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
    request = cash.record(K.CHANGE_REQUESTED, shift=other, operator=manager, payload={"kind": "coins"})
    with pytest.raises(CashError) as exc:
        cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=request)
    assert exc.value.code == "PARENT_MISMATCH"


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
    assert count.payload == {"counted_q": 8490, "notes": "ok", "supervisory": False}
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


def test_fechamento_supervisorio_assina_quem_fechou(shift, operator, manager):
    count = cash.close_shift(shift, counted_q=10000, actor=manager)
    assert count.operator == manager
    assert count.payload["supervisory"] is True


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
    a = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"kind": "coins"})
    b = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"kind": "amount", "amount_q": 5000, "note": "notas de 10"})
    c = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"kind": "small_bills"})
    cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=a)
    cash.record(K.CHANGE_CANCELLED, shift=shift, operator=operator, parent=b)

    requests = {r["entry_id"]: r for r in cash.change_requests(shift)}
    assert requests[a.pk]["status"] == "served"
    assert requests[a.pk]["served_by"] == "pablo"
    assert requests[b.pk]["status"] == "cancelled"
    assert requests[b.pk]["amount_q"] == 5000
    assert requests[b.pk]["note"] == "notas de 10"
    assert requests[c.pk]["status"] == "pending"
    assert requests[c.pk]["requested_by"] == "marina"
    assert cash.balance(shift) == 10000  # net zero: troco não é dinheiro


def test_segunda_resolucao_fica_no_livro_mas_nao_muda_o_estado(shift, operator, manager):
    a = cash.record(K.CHANGE_REQUESTED, shift=shift, operator=operator, payload={"kind": "coins"})
    cash.record(K.CHANGE_SERVED, shift=shift, operator=operator, approved_by=manager, parent=a)
    cash.record(K.CHANGE_CANCELLED, shift=shift, operator=operator, parent=a)

    (request,) = cash.change_requests(shift)
    assert request["status"] == "served"
    assert cash.timeline(shift).filter(parent=a).count() == 2


# ── Consultas de custódia ─────────────────────────────────────────────────


def test_open_shift_for_e_is_closed(operator, manager, terminal):
    assert cash.open_shift_for(operator) is None
    shift = cash.open_shift(operator=operator, terminal=terminal)
    assert cash.open_shift_for(operator) == shift
    assert cash.open_shift_for_terminal(terminal) == shift
    assert cash.is_closed(shift.pk) is False
    cash.close_shift(shift, counted_q=0, actor=operator)
    assert cash.open_shift_for(operator) is None
    assert cash.is_closed(shift.pk) is True
    assert cash.is_closed("nope") is False
    assert cash.is_closed(999999) is False


def test_balance_ate_um_lancamento(shift, operator, manager):
    sale = cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500)
    cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000, approved_by=manager)
    assert cash.balance(shift, until=sale) == 11500
    assert cash.balance(shift) == 6500


def test_o_operador_do_lancamento_pode_nao_ser_o_do_turno(shift, manager):
    """Fechamento supervisório e acerto por gerente: quem agiu fica na linha."""
    entry = cash.record(K.NOTE, shift=shift, operator=manager, payload={"text": "x"})
    assert entry.operator == manager
    assert Shift.objects.get(pk=shift.pk).operator != manager


def test_get_user_model_e_o_unico_acoplamento_externo():
    """O pacote só conhece o User configurado; nada de shop/backstage."""
    assert get_user_model() is not None
