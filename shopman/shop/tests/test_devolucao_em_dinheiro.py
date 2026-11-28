"""Devolução de venda paga em DINHEIRO vira pendência de devolver na gaveta.

O cancelamento já deixava o dinheiro pendente (``pending_cash_refunds``) até
alguém com turno aberto entregar as notas. A devolução PARCIAL não: o Gestor
registrava a devolução, o ``ReturnHandler`` pedia o estorno, o ``refund`` deixa
o dinheiro em paz (cancelar não é devolver) e nada mais acontecia. O cliente
saía sem o dinheiro e nenhuma tela mandava devolver.

O que esta suíte prende:

- devolução parcial em dinheiro vira pendência de devolver SÓ o devolvido, com
  o motivo "devolução de parte da venda"; a total, com "venda devolvida";
- só o gesto "Devolvi em dinheiro" (``refund_cash``) grava o estorno no Payman
  e a linha ``refund`` no turno, e o pedido guarda quem devolveu, quando e
  quem autorizou (evento ``cash_refund_recorded``);
- na venda mista (dinheiro + maquininha) devolvida em parte, o dinheiro devolve
  primeiro e a maquininha não pede o mesmo valor de novo.
"""

from __future__ import annotations

import pytest
from shopman.cashman import Entry
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.shop.handlers.returns import ReturnService
from shopman.shop.services import payment as payment_service
from shopman.shop.tests.test_estorno_na_maquininha import _Balcao

pytestmark = pytest.mark.django_db


@pytest.fixture
def balcao():
    return _Balcao()


def _vender_dois(balcao, ref: str, **overrides) -> Order:
    payload = {
        "items": [{"sku": "POS-ITEM", "name": "Item de balcão", "qty": 2, "unit_price_q": 1200}],
        "payment_method": "cash",
        "tendered_q": 2400,
    }
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}
    order = balcao.vender(client_request_id=ref, **payload)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.COMPLETED)
    order.refresh_from_db()
    return order


def _devolver_um(order) -> Order:
    line_id = order.items.first().line_id
    result = ReturnService.initiate_return(order, [{"line_id": line_id, "qty": 1}], reason="defeito", actor="gestor")
    assert result.success, result.error
    order.refresh_from_db()
    ReturnService.process_refund(order, 1200, "return.process", refund_reference=f"return:{order.ref}:0")
    order.refresh_from_db()
    return order


def _refunds(order_ref: str) -> int:
    return sum(
        PaymentTransaction.objects.filter(intent__order_ref=order_ref, type="refund").values_list("amount_q", flat=True)
    )


def test_devolucao_parcial_em_dinheiro_vira_pendencia_na_gaveta(balcao):
    order = _devolver_um(_vender_dois(balcao, "dv-parcial"))

    assert _refunds(order.ref) == 0, "devolver é gesto de gente, o cancel/estorno automático não toca em dinheiro"
    (pendente,) = payment_service.pending_cash_refunds()
    assert (pendente.order_ref, pendente.amount_q, pendente.reason) == (order.ref, 1200, "partial_return")


def test_devolvi_em_dinheiro_grava_os_dois_livros_com_quem_e_quando(balcao):
    order = _devolver_um(_vender_dois(balcao, "dv-gesto"))

    devolvido = payment_service.refund_cash(
        order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager, reason="devolução",
    )

    assert devolvido == 1200
    (intent,) = PaymentIntent.objects.filter(order_ref=order.ref)
    # O que o cliente ficou continua pago.
    assert PaymentService.captured_total(intent.ref) - PaymentService.refunded_total(intent.ref) == 1200
    linha = Entry.objects.get(kind=Entry.Kind.REFUND, order_ref=order.ref)
    assert linha.amount_q == -1200 and linha.shift == balcao.shift
    evento = order.events.get(type="cash_refund_recorded")
    assert evento.actor == "marina"
    assert evento.payload == {
        "amount_q": 1200, "reason": "partial_return", "approved_by": "gerente", "shift_id": balcao.shift.pk,
    }
    assert payment_service.pending_cash_refunds() == []
    # A segunda vez não acha o que devolver.
    assert payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator) == 0


def test_devolucao_total_em_dinheiro_diz_que_a_venda_foi_devolvida(balcao, django_capture_on_commit_callbacks):
    order = _vender_dois(balcao, "dv-total")
    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(Order.Status.RETURNED, actor="test")

    (pendente,) = payment_service.pending_cash_refunds()
    assert (pendente.amount_q, pendente.reason) == (2400, "returned")


def test_venda_mista_devolvida_em_parte_devolve_o_dinheiro_primeiro(balcao):
    order = _vender_dois(
        balcao,
        "dv-mista",
        payment_method="mixed",
        tendered_q=None,
        payment_tenders=[
            {"method": "cash", "amount_q": 1400, "collection": "terminal"},
            {"method": "debit", "amount_q": 1000, "collection": "terminal"},
        ],
    )
    order = _devolver_um(order)

    (dinheiro,) = payment_service.pending_cash_refunds()
    assert dinheiro.amount_q == 1200
    # A maquininha não pede de novo o que a gaveta já vai devolver.
    assert payment_service.pending_card_machine_refunds() == []


def test_sessao_de_caixa_mostra_o_motivo_da_devolucao(balcao):
    _devolver_um(_vender_dois(balcao, "dv-tela"))

    from shopman.backstage.projections.pos import _pending_cash_refunds

    (linha,) = _pending_cash_refunds(balcao.shift)
    assert linha.reason == "partial_return"
    assert linha.reason_label == "Devolução de parte da venda"


# ── M1 (laudo 23/10): dois "Devolvi em dinheiro" ao mesmo tempo ────────────


def _vender_cancelada(balcao, ref: str) -> Order:
    order = balcao.vender(
        client_request_id=ref,
        items=[{"sku": "POS-ITEM", "name": "Item de balcão", "qty": 1, "unit_price_q": 1200}],
        payment_method="cash",
        tendered_q=1200,
    )
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    return order


def test_devolvi_em_dinheiro_trava_os_intents_antes_de_ler_o_saldo(balcao, monkeypatch):
    order = _vender_cancelada(balcao, "m1-lock")
    calls: list[str] = []
    real_lock = payment_service._lock_payment_intents
    real_balance = payment_service._payman_refundable_amount

    def lock(refs):
        calls.append("lock")
        return real_lock(refs)

    def balance(ref):
        calls.append("balance")
        return real_balance(ref)

    monkeypatch.setattr(payment_service, "_lock_payment_intents", lock)
    monkeypatch.setattr(payment_service, "_payman_refundable_amount", balance)

    devolvido = payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager)

    assert devolvido == 1200
    assert calls[0] == "lock"
    assert "balance" in calls[1:]


def test_segundo_devolvi_em_dinheiro_com_leitura_velha_nao_grava_segunda_saida(balcao, monkeypatch):
    """Duas requisições com chaves diferentes (dois dispositivos, duplo toque).

    A segunda leu saldo e contador antes da primeira gravar. O Payman reconhece o
    estorno pela chave e devolve a transação existente; o livro-caixa não ganha a
    segunda linha, e o fechamento cego não acusa sobra falsa.
    """
    import shopman.payman.models as payman_models

    order = _vender_cancelada(balcao, "m1-race-1")
    first = payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager)
    assert first == 1200

    # Leitura velha: saldo cheio e nenhum estorno anterior.
    monkeypatch.setattr(payment_service, "_payman_refundable_amount", lambda ref: 1200)
    real_filter = payman_models.PaymentTransaction.objects.filter

    class _StaleCount:
        def __init__(self, qs):
            self.qs = qs

        def count(self):
            return 0

        def values_list(self, *args, **kwargs):
            return self.qs.values_list(*args, **kwargs)

    def stale_filter(*args, **kwargs):
        qs = real_filter(*args, **kwargs)
        if kwargs.get("type") == "refund" and "intent__ref" in kwargs:
            return _StaleCount(qs)
        return qs

    monkeypatch.setattr(payman_models.PaymentTransaction.objects, "filter", stale_filter)
    second = payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager)
    monkeypatch.undo()

    assert second == 0
    assert PaymentTransaction.objects.filter(intent__order_ref=order.ref, type="refund").count() == 1
    lines = list(Entry.objects.filter(kind=Entry.Kind.REFUND, order_ref=order.ref).values_list("amount_q", flat=True))
    assert lines == [-1200]
    assert order.events.filter(type="cash_refund_recorded").count() == 1
