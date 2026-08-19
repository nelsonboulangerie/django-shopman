"""O livro é imutável (no app) e o sinal mora no tipo (no banco)."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from shopman.cashman.models import Entry, Shift, Terminal

pytestmark = pytest.mark.django_db


def _shift(operator, terminal):
    return Shift.objects.create(terminal=terminal, operator=operator)


def test_o_lancamento_recusa_editar_e_apagar(operator, terminal):
    shift = _shift(operator, terminal)
    entry = Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.CASH_IN, amount_q=1000)

    with pytest.raises(ValueError, match="imutáveis"):
        entry.amount_q = 5
        entry.save()
    with pytest.raises(ValueError, match="imutáveis"):
        entry.delete()
    with pytest.raises(ValueError, match="imutáveis"):
        Entry.objects.filter(pk=entry.pk).update(amount_q=5)
    with pytest.raises(ValueError, match="imutáveis"):
        Entry.objects.all().delete()

    entry.refresh_from_db()
    assert entry.amount_q == 1000


def test_o_livro_protege_turno_e_terminal(operator, terminal):
    shift = _shift(operator, terminal)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.CASH_IN, amount_q=1000)

    with pytest.raises(ProtectedError):
        shift.delete()
    with pytest.raises(ProtectedError):
        terminal.delete()


@pytest.mark.parametrize(
    ("kind", "amount_q"),
    [
        (Entry.Kind.FLOAT_IN, 0),
        (Entry.Kind.FLOAT_IN, -1),
        (Entry.Kind.CASH_IN, -1),
        (Entry.Kind.COD_SETTLED, 0),
        (Entry.Kind.SALE, -1),
        (Entry.Kind.CASH_OUT, 0),
        (Entry.Kind.CASH_OUT, 1),
        (Entry.Kind.REFUND, 1),
        (Entry.Kind.COURIER_OUT, 0),
        (Entry.Kind.COURIER_OUT, 2000),
        (Entry.Kind.COURIER_IN, -1),
        (Entry.Kind.DRAWER_OPEN, 1),
        (Entry.Kind.DRAWER_UNLOCK, -1),
        (Entry.Kind.CHANGE_REQUESTED, 5),
        (Entry.Kind.RECEIPT_RESULT, 1),
        (Entry.Kind.NOTE, 1),
    ],
)
def test_o_banco_recusa_sinal_errado_para_o_tipo(operator, terminal, kind, amount_q):
    """O sinal vive no TIPO. Uma sangria positiva ou uma abertura de gaveta com
    valor seriam um segundo jeito de dizer a mesma coisa, e é assim que um
    lançamento se disfarça de outro."""
    shift = _shift(operator, terminal)
    with pytest.raises(IntegrityError), transaction.atomic():
        Entry.objects.create(shift=shift, operator=operator, kind=kind, amount_q=amount_q)


@pytest.mark.parametrize(
    ("kind", "amount_q"),
    [
        (Entry.Kind.FLOAT_IN, 1),
        (Entry.Kind.SALE, 0),
        (Entry.Kind.SALE, 1500),
        (Entry.Kind.CASH_OUT, -1),
        (Entry.Kind.REFUND, -1),
        (Entry.Kind.COURIER_OUT, -2000),
        (Entry.Kind.COURIER_IN, 0),
        (Entry.Kind.COURIER_IN, 500),
        (Entry.Kind.COUNT, -300),
        (Entry.Kind.COUNT, 0),
        (Entry.Kind.COUNT_CORRECTION, 500),
        (Entry.Kind.DRAWER_OPEN, 0),
    ],
)
def test_o_banco_aceita_o_sinal_do_tipo(operator, terminal, kind, amount_q):
    shift = _shift(operator, terminal)
    Entry.objects.create(shift=shift, operator=operator, kind=kind, amount_q=amount_q)


def test_sign_allows_e_a_mesma_tabela_do_check_constraint():
    """A regra é uma só: o service consulta a mesma tabela que o banco confere.
    Se um tipo novo entrar sem regra, `sign_allows` diz não."""
    assert Entry.sign_allows(Entry.Kind.SALE, 0)
    assert not Entry.sign_allows(Entry.Kind.CASH_OUT, 10)
    assert Entry.sign_allows(Entry.Kind.COUNT, -10)
    assert not Entry.sign_allows("inventado", 0)
    assert set(Entry.SIGN_BY_KIND) == set(Entry.Kind.values)


def test_o_banco_recusa_duas_vendas_do_mesmo_pedido_no_mesmo_turno(operator, terminal):
    """A idempotência da venda é constraint, não boa vontade de quem chama.

    Dois submits do mesmo fechamento (retry de rede do PDV) dobrariam o dinheiro
    esperado do turno se a unicidade dependesse de um `exists()` antes do insert.
    """
    shift = _shift(operator, terminal)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.SALE, amount_q=1500, order_ref="A01")

    with pytest.raises(IntegrityError), transaction.atomic():
        Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.SALE, amount_q=1500, order_ref="A01")


def test_o_banco_recusa_dois_acertos_de_entrega_do_mesmo_pedido_no_mesmo_turno(operator, terminal):
    shift = _shift(operator, terminal)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.COD_SETTLED, amount_q=1500, order_ref="A01")

    with pytest.raises(IntegrityError), transaction.atomic():
        Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.COD_SETTLED, amount_q=1500, order_ref="A01")


def test_a_unicidade_e_por_turno_por_tipo_e_so_com_pedido(operator, manager, terminal):
    """O que a constraint NÃO proíbe, e por quê.

    - venda sem `order_ref` (não há pedido a que amarrar) repete à vontade;
    - a devolução do mesmo pedido convive com a venda (tipos diferentes);
    - o mesmo pedido pode voltar noutro turno (acerto de entrega de ontem).
    """
    shift = _shift(operator, terminal)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.SALE, amount_q=1500)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.SALE, amount_q=900)
    Entry.objects.create(shift=shift, operator=operator, kind=Entry.Kind.SALE, amount_q=1500, order_ref="A01")
    Entry.objects.create(
        shift=shift, operator=operator, kind=Entry.Kind.REFUND, amount_q=-1500, order_ref="A01"
    )

    other_terminal = Terminal.objects.create(ref="pdv-2")
    other_shift = Shift.objects.create(terminal=other_terminal, operator=manager)
    Entry.objects.create(shift=other_shift, operator=manager, kind=Entry.Kind.SALE, amount_q=1500, order_ref="A01")


def test_um_turno_aberto_por_operador_e_por_terminal(operator, manager, terminal):
    Shift.objects.create(terminal=terminal, operator=operator)
    with pytest.raises(IntegrityError), transaction.atomic():
        Shift.objects.create(terminal=Terminal.objects.create(ref="pdv-2"), operator=operator)
    with pytest.raises(IntegrityError), transaction.atomic():
        Shift.objects.create(terminal=terminal, operator=manager)


def test_turno_fechado_libera_o_operador_e_o_terminal(operator, terminal):
    shift = Shift.objects.create(terminal=terminal, operator=operator, status=Shift.Status.CLOSED)
    assert not shift.is_open
    Shift.objects.create(terminal=terminal, operator=operator)


def test_o_turno_nao_tem_coluna_de_dinheiro():
    """Fechamento cego por construção: sem coluna, não há número para vazar."""
    names = {f.name for f in Shift._meta.get_fields()}
    assert not any(n.endswith("_q") for n in names), names
    assert "metadata" not in names


def test_terminal_default_nasce_uma_vez():
    assert Terminal.default().pk == Terminal.default().pk
    assert Terminal.default().ref == "pdv-main"
