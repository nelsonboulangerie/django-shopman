"""A corrida entre lançar e contar: dinheiro não entra depois do fechamento.

O fechamento cego só significa alguma coisa se a contagem for o ÚLTIMO fato do
turno. ``close_shift`` tranca o turno com ``select_for_update``; se ``record``
lesse o status só da instância que recebeu, uma venda em voo commitaria depois
da contagem, num turno CLOSED — e o ``count`` (congelado como "contado −
esperado no instante do fechamento") ficaria órfão da própria premissa: o livro
passaria a provar um saldo que a gaveta nunca teve.

Dois testes, duas fidelidades:

- o determinístico roda em qualquer banco e é o gate: prova que ``record``
  releva a instância recebida e pergunta ao banco;
- o de threads roda só no PostgreSQL (SQLite não tem ``SELECT FOR UPDATE``) e é
  a prova de que os dois caminhos se SERIALIZAM de verdade, no molde do
  ``packages/payman/shopman/payman/tests/test_concurrency.py``.
"""

from __future__ import annotations

import threading

import pytest
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift, Terminal

K = Entry.Kind

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Exige PostgreSQL: SQLite não tem SELECT FOR UPDATE, e sem lock não há o que serializar",
)


def _close_behind_the_instance(shift: Shift) -> None:
    """Fecha o turno NO BANCO sem tocar na instância em memória.

    É o que a outra conexão faz: o gerente conta a gaveta e fecha enquanto a
    venda ainda está em voo com o turno que leu antes.
    """
    Shift.objects.filter(pk=shift.pk).update(status=Shift.Status.CLOSED, closed_at=timezone.now())


def test_venda_em_voo_nao_entra_no_turno_fechado_por_tras(shift, operator):
    _close_behind_the_instance(shift)
    assert shift.is_open, "a instância em memória é a de antes: é esse o cenário"

    with pytest.raises(CashError) as exc:
        cash.record(K.SALE, shift=shift, operator=operator, amount_q=1500, order_ref="A01")

    assert exc.value.code == "SHIFT_NOT_OPEN"
    assert not Entry.objects.filter(shift_id=shift.pk, kind=K.SALE).exists()


def test_sangria_em_voo_nao_entra_no_turno_fechado_por_tras(shift, operator, manager):
    _close_behind_the_instance(shift)

    with pytest.raises(CashError) as exc:
        cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-5000, approved_by=manager, reason="Cofre")

    assert exc.value.code == "SHIFT_NOT_OPEN"
    assert not Entry.objects.filter(shift_id=shift.pk, kind=K.CASH_OUT).exists()


def test_abertura_de_gaveta_em_voo_nao_entra_no_turno_fechado_por_tras(shift, operator):
    _close_behind_the_instance(shift)

    with pytest.raises(CashError) as exc:
        cash.record(K.DRAWER_OPEN, shift=shift, operator=operator, reason="conferir")

    assert exc.value.code == "SHIFT_NOT_OPEN"


def test_o_que_o_turno_fechado_aceita_continua_aceito_com_a_instancia_velha(shift, operator, manager):
    """Comprovante e anotação sobrevivem ao fechamento — a releitura não os mata.

    O navegador do balcão confirma a impressão depois de o turno fechar; é por
    isso que ``receipt_result`` está na lista de exceções do pacote.
    """
    sangria = cash.record(K.CASH_OUT, shift=shift, operator=operator, amount_q=-100, approved_by=manager, reason="x")
    _close_behind_the_instance(shift)

    cash.record(K.NOTE, shift=shift, operator=manager, payload={"text": "conferido"})
    cash.record(K.RECEIPT_RESULT, shift=shift, operator=operator, parent=sangria, payload={"status": "printed"})


def test_correcao_de_contagem_le_o_fechamento_do_banco(shift, operator, manager):
    """O inverso: `count_correction` exige turno FECHADO, e quem responde é o banco."""
    count = cash.close_shift(shift, counted_q=9900, actor=operator)
    stale_open = Shift.objects.get(pk=shift.pk)
    Shift.objects.filter(pk=shift.pk).update(status=Shift.Status.CLOSED)
    stale_open.status = Shift.Status.OPEN  # a instância mente: diz aberto

    entry = cash.record(
        K.COUNT_CORRECTION,
        shift=stale_open,
        operator=manager,
        approved_by=manager,
        amount_q=100,
        parent=count,
        reason="recontagem",
    )
    assert entry.pk


@requires_postgres
class TestFecharEnquantoVende(TransactionTestCase):
    """Duas conexões, o interleaving exato do fim de expediente.

    1. a venda em dinheiro abre transação e lê o turno (aberto);
    2. o gerente conta a gaveta, fecha o turno e COMMITA;
    3. a venda tenta gravar a linha ``sale`` na transação que já estava em voo.

    O passo 3 tem de ser recusado. Se ele passar, o dinheiro entra depois da
    contagem: ``expected_before_count`` cresce e o ``count`` — congelado como
    "contado − esperado" no instante 2 — passa a provar um saldo que a gaveta
    nunca teve.
    """

    def test_venda_em_voo_perde_para_o_fechamento(self):
        from django.contrib.auth import get_user_model
        from django.db import transaction

        user_model = get_user_model()
        operator = user_model.objects.create_user(username="marina-conc", password="x")
        manager = user_model.objects.create_user(username="pablo-conc", password="x")
        terminal = Terminal.objects.create(ref="pdv-conc", label="Balcão")
        shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)

        results = []
        sale_read_the_shift = threading.Event()
        shift_is_closed = threading.Event()

        def sell():
            try:
                with transaction.atomic():
                    local_shift = Shift.objects.get(pk=shift.pk)  # leitura sem lock, ANTES
                    sale_read_the_shift.set()
                    assert shift_is_closed.wait(timeout=10), "o fechamento não commitou a tempo"
                    cash.record(K.SALE, shift=local_shift, operator=operator, amount_q=1500, order_ref="A01")
                results.append(("sale_ok", None))
            except CashError as exc:
                results.append(("sale_err", exc.code))
            finally:
                connection.close()

        def close():
            try:
                assert sale_read_the_shift.wait(timeout=10), "a venda não chegou a ler o turno"
                local_shift = Shift.objects.get(pk=shift.pk)
                cash.close_shift(local_shift, counted_q=11500, actor=manager)
                results.append(("close_ok", None))
            except CashError as exc:
                results.append(("close_err", exc.code))
            finally:
                shift_is_closed.set()
                connection.close()

        threads = [threading.Thread(target=sell), threading.Thread(target=close)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertIn(("close_ok", None), results, f"o fechamento tem de acontecer: {results}")
        self.assertIn(("sale_err", "SHIFT_NOT_OPEN"), results, f"a venda tardia tem de ser recusada: {results}")
        self.assertFalse(
            Entry.objects.filter(shift_id=shift.pk, kind=K.SALE).exists(),
            "a venda entrou depois da contagem: o fechamento cego virou ficção",
        )
        count = Entry.objects.filter(shift_id=shift.pk, kind=K.COUNT).get()
        self.assertEqual(count.amount_q, 1500, "a contagem tem de seguir provando o esperado do instante em que fechou")
