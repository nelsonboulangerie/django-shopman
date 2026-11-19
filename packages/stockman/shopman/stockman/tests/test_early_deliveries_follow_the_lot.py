"""
A entrega feita antes de o lote fechar segue para o lote (issue #2724).

``fulfill`` baixa a reserva do quant em que ela está, e esse quant pode ainda
ser saldo de produção (planejado, ou ``batch='started'``). O ``realize``
debitava do saldo de produção ``min(realizado, saldo)`` e creditava o lote com
o realizado inteiro: o que já tinha saído voltava como disponível. Medido em
18/11/2026 pela fiação real: lote de 10, 4 entregues antes de fechar, vitrine
com 10.

A regra (decisão da coordenação, 19/11/2026): a baixa sai na hora, e o
fechamento credita a vitrine só com o que ainda não foi vendido. O abatimento
sai do ledger (o ``Move`` da entrega no saldo de produção), sem contador novo.
As pernas de produção continuam dizendo o realizado inteiro.

Estes testes prendem a regra no Stockman, sem o Craftsman: o "início" aqui é o
que a ponte faz (entrada no ``started``, entrega acompanha, baixa do planejado).
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db.models import Sum
from shopman.stockman import StockError, stock
from shopman.stockman.models import Hold, Move, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.holds import delivery_reason
from shopman.stockman.services.planning import StockPlanning

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
STARTED = "started"
D = Decimal


@pytest.fixture
def baguete():
    return SimpleNamespace(sku=SKU, name="Baguete", shelf_life_days=None, availability_policy="planned_ok")


def _plan(baguete, qty, day, position) -> Quant:
    return stock.plan(D(str(qty)), baguete, day, position=position, reason="plano")


def _hold(baguete, qty, day, **metadata) -> Hold:
    hold_id = stock.hold(D(str(qty)), baguete, target_date=day, **metadata)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _deliver(hold: Hold, *, quantity=None, kind=Move.Kind.SELL) -> None:
    """A baixa do pedido: confirma e entrega, como o orquestrador faz."""
    stock.confirm(hold.hold_id)
    kwargs = {} if kind is None else {"kind": kind}
    stock.fulfill(hold.hold_id, quantity=None if quantity is None else D(str(quantity)), **kwargs)


def _start(planned: Quant, qty, position) -> Quant:
    """O que a ponte do Craftsman faz no início do lote."""
    qty = D(str(qty))
    started = stock.receive(
        qty, SKU, position, target_date=planned.target_date, batch=STARTED, reason="produção do lote", kind="make",
    )
    StockPlanning.carry_deliveries(planned, started, limit=qty)
    planned.refresh_from_db()
    stock.adjust(planned, max(planned.quantity - qty, D("0")), reason="entrada em produção")
    started.refresh_from_db()
    return started


def _realize(baguete, qty, day, *, to, source, from_batch="", **kwargs) -> Quant:
    return stock.realize(
        baguete, day, D(str(qty)), to, from_position=source, from_batch=from_batch, reason="lote", **kwargs,
    )


def _qty(quant: Quant) -> Decimal:
    quant.refresh_from_db()
    return quant.quantity


def _ledger(quant: Quant) -> list[tuple[Decimal, str, str]]:
    return list(Move.objects.filter(quant=quant).order_by("pk").values_list("delta", "kind", "reason"))


def _where(hold: Hold) -> int | None:
    hold.refresh_from_db()
    return hold.quant_id


def _total(kind) -> Decimal:
    return Move.objects.filter(quant__sku=SKU, kind=kind).aggregate(total=Sum("delta"))["total"] or D("0")


# ── O fechamento credita só o que ainda não saiu ─────────────────────────────


def test_lot_receives_only_what_was_not_delivered_yet(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 4, today, reference="order:P-1")
    _deliver(pedido)
    assert _qty(planned) == D("6")

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("6"), "10 produzidas, 4 já entregues: 6 para vender"
    assert _qty(planned) == D("0")
    assert _where(pedido) == lot.pk, "a entrega passa a pesar no lote que a pagou"
    pedido.refresh_from_db()
    assert pedido.status == HoldStatus.FULFILLED


def test_production_legs_still_say_the_full_output(baguete, producao, vitrine, today):
    """O registro de produção não muda: as pernas ``MAKE`` são as de um lote sem entrega antecipada."""
    planned = _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 4, today)
    _deliver(pedido)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    entrega = delivery_reason(pedido.pk)
    assert _ledger(planned) == [
        (D("10"), "adjust", "plano"),
        (D("-4"), "sell", entrega),
        (D("4"), "sell", f"{entrega} segue com o lote"),
        (D("-10"), "make", "Transferência: lote"),
    ]
    assert _ledger(lot) == [
        (D("10"), "make", "Recebido de produção: lote"),
        (D("-4"), "sell", entrega),
    ]
    assert _total(Move.Kind.SELL) == D("-4"), "a venda continua contada uma vez só"
    assert _total(Move.Kind.MAKE) == D("0"), "transferência de produção: sai 10, entra 10"


def test_without_early_delivery_the_ledger_is_untouched(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    reserva = _hold(baguete, 4, today)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _ledger(planned) == [(D("10"), "adjust", "plano"), (D("-10"), "make", "Transferência: lote")]
    assert _ledger(lot) == [(D("10"), "make", "Recebido de produção: lote")]
    assert _where(reserva) == lot.pk
    assert (lot.quantity, lot.held) == (D("10"), D("4"))


def test_everything_delivered_before_closing_credits_zero(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    for qty in (6, 4):
        _deliver(_hold(baguete, qty, today))
    assert _qty(planned) == D("0")

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("0")
    assert _ledger(lot)[0] == (D("10"), "make", "Recebido de produção: lote")
    assert _total(Move.Kind.SELL) == D("-10")


def test_output_above_plan_is_still_production_gain(baguete, producao, vitrine, today):
    """O forno rendeu 12 de 10, com 4 já entregues: 8 na vitrine, e o plano não fica negativo."""
    planned = _plan(baguete, 10, today, producao)
    _deliver(_hold(baguete, 4, today))

    lot = _realize(baguete, 12, today, to=vitrine, source=producao)

    assert _qty(lot) == D("8")
    assert _qty(planned) == D("0")


# ── Quebra, e entrega maior que a produção ───────────────────────────────────


def test_short_output_leaves_the_loss_on_the_production_balance(baguete, producao, vitrine, today):
    """Lote de 10 em produção, 4 entregues, saíram 6: 2 na vitrine e os 4 de quebra seguem
    no saldo de produção, para a ponte lançar como perda (antes sobravam 0 e o fechamento falhava)."""
    planned = _plan(baguete, 10, today, producao)
    started = _start(planned, 10, producao)
    _deliver(_hold(baguete, 4, today))
    assert _qty(started) == D("6")

    lot = _realize(baguete, 6, today, to=vitrine, source=producao, from_batch=STARTED)

    assert _qty(lot) == D("2")
    assert _qty(started) == D("4"), "previsto 10, realizado 6: a quebra é 4"


def test_delivered_beyond_the_output_never_goes_negative_nor_vanishes(baguete, producao, vitrine, today):
    """4 entregues, lote fechado com 3: o lote zera e a unidade sem lastro continua
    devida ao saldo de produção, no ledger e na reserva. Recusar o fechamento é de quem
    chama (a ponte, em modo fail-closed, não acha a quebra inteira para baixar)."""
    planned = _plan(baguete, 10, today, producao)
    started = _start(planned, 10, producao)
    pedido = _hold(baguete, 4, today)
    _deliver(pedido)

    lot = _realize(baguete, 3, today, to=vitrine, source=producao, from_batch=STARTED)

    assert _qty(lot) == D("0")
    assert _qty(started) == D("6"), "10 iniciadas menos 4 entregues: nada some"
    assert _where(pedido) == started.pk, "enquanto não quita, a reserva segue no saldo que deve"
    entrega = delivery_reason(pedido.pk)
    owed = Move.objects.filter(quant=started, reason__startswith=entrega).aggregate(total=Sum("delta"))["total"]
    assert owed == D("-1")
    assert _total(Move.Kind.SELL) == D("-4")


def test_a_delivery_larger_than_one_leg_spreads_over_the_lots(baguete, producao, vitrine, today):
    """Partição do fechamento em dois lotes (7 e 3) com 8 já entregues: 7 pesam no
    primeiro, 1 no segundo, e a reserva vai para o lote que a quita."""
    planned = _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 8, today)
    _deliver(pedido)

    first = _realize(baguete, 7, today, to=vitrine, source=producao, to_batch="L-A")
    assert _where(pedido) == planned.pk
    second = _realize(baguete, 3, today, to=vitrine, source=producao, to_batch="L-B")

    assert (_qty(first), _qty(second)) == (D("0"), D("2"))
    assert _where(pedido) == second.pk
    assert _qty(planned) == D("0")
    assert _total(Move.Kind.SELL) == D("-8")


def test_closing_twice_does_not_charge_the_delivery_twice(baguete, producao, vitrine, today):
    """Dois lotes do mesmo SKU e dia no mesmo saldo: a entrega pesa no primeiro que fecha, uma vez."""
    planned = _plan(baguete, 20, today, producao)
    _deliver(_hold(baguete, 4, today))

    first = _realize(baguete, 10, today, to=vitrine, source=producao, to_batch="L-1")
    second = _realize(baguete, 10, today, to=vitrine, source=producao, to_batch="L-2")

    assert (_qty(first), _qty(second)) == (D("6"), D("10"))
    assert _qty(planned) == D("0")


# ── As reservas ainda ativas seguem, no que sobra do lote ────────────────────


def test_active_holds_follow_into_what_is_left_of_the_lot(baguete, producao, vitrine, today):
    _plan(baguete, 10, today, producao)
    entregue = _hold(baguete, 4, today)
    primeira = _hold(baguete, 5, today, reference="order:A")
    segunda = _hold(baguete, 1, today, reference="order:B")
    _deliver(entregue)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert (_where(primeira), _where(segunda)) == (lot.pk, lot.pk)
    lot.refresh_from_db()
    assert (lot.quantity, lot.held) == (D("6"), D("6"))


def test_active_hold_beyond_what_is_left_stays_behind(baguete, producao, vitrine, today):
    """Saíram 8 de 10 com 4 entregues: sobram 4 no lote, e a reserva de 5 não cabe.
    Fica onde estava, como já ficava a reserva que não cabe num lote curto."""
    planned = _plan(baguete, 10, today, producao)
    entregue = _hold(baguete, 4, today)
    grande = _hold(baguete, 5, today)
    _deliver(entregue)

    lot = _realize(baguete, 8, today, to=vitrine, source=producao)

    assert _where(grande) == planned.pk
    lot.refresh_from_db()
    assert (lot.quantity, lot.held) == (D("4"), D("0"))


# ── O fato lido é o do ledger ────────────────────────────────────────────────


def test_the_amount_is_what_the_ledger_delivered_not_what_was_held(baguete, producao, vitrine, today):
    """Reserva de 5 que entregou 3 (sacola adotada a mais): o lote paga 3."""
    _plan(baguete, 10, today, producao)
    _deliver(_hold(baguete, 5, today), quantity=3)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("7")


def test_the_carry_keeps_the_kind_of_the_delivery(baguete, producao, vitrine, today):
    """``fulfill`` sem ``kind`` grava ajuste: as duas pernas seguem o tipo da entrega."""
    planned = _plan(baguete, 10, today, producao)
    _deliver(_hold(baguete, 4, today), kind=None)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("6")
    assert _ledger(lot)[1][:2] == (D("-4"), "adjust")
    assert _ledger(planned)[2][:2] == (D("4"), "adjust")
    assert _total(Move.Kind.SELL) == D("0")


def test_a_delivery_given_back_to_the_production_balance_is_not_owed(baguete, producao, vitrine, today):
    """Pedido cancelado antes de o lote fechar: a devolução entra na conta da entrega,
    no mesmo saldo, e o lote fecha inteiro. Devolução parcial deixa o resto devido."""
    planned = _plan(baguete, 10, today, producao)
    cancelado = _hold(baguete, 4, today)
    alterado = _hold(baguete, 3, today)
    _deliver(cancelado)
    _deliver(alterado)
    for hold, qty in ((cancelado, 4), (alterado, 1)):
        stock.receive(
            D(str(qty)), SKU, producao, target_date=today, kind=Move.Kind.RETURN,
            reason=delivery_reason(hold.pk, "devolvida: pedido cancelado"),
        )
    assert _qty(planned) == D("8")

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("8"), "10 produzidas, 2 entregues de fato"
    assert _qty(planned) == D("0")
    assert (_where(cancelado), _where(alterado)) == (planned.pk, lot.pk)
    assert _total(Move.Kind.SELL) == D("-7")
    assert _total(Move.Kind.RETURN) == D("5")


def test_the_account_of_one_hold_never_reads_another(baguete, producao, vitrine, today):
    """``Entrega hold:1`` não é a conta de ``Entrega hold:12``: a devolução de outra
    reserva, cujo número começa pelo desta, não quita a entrega desta."""
    _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 1, today)
    _deliver(pedido)
    outra = int(f"{pedido.pk}2")
    assert delivery_reason(outra).startswith(delivery_reason(pedido.pk))
    stock.receive(
        D("1"), SKU, producao, target_date=today, kind=Move.Kind.RETURN,
        reason=delivery_reason(outra, "devolvida: pedido cancelado"),
    )

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _where(pedido) == lot.pk
    assert _ledger(lot)[1] == (D("-1"), "sell", delivery_reason(pedido.pk))
    assert _qty(lot) == D("9")


def test_released_or_active_holds_are_not_deliveries(baguete, producao, vitrine, today):
    _plan(baguete, 10, today, producao)
    solta = _hold(baguete, 3, today)
    stock.release(solta.hold_id, reason="desistiu")
    _hold(baguete, 2, today)

    lot = _realize(baguete, 10, today, to=vitrine, source=producao)

    assert _qty(lot) == D("10")


# ── O início do lote leva a entrega junto ────────────────────────────────────


def test_start_carries_the_delivery_made_against_the_plan(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 4, today)
    _deliver(pedido)

    started = _start(planned, 10, producao)

    assert (_qty(planned), _qty(started)) == (D("0"), D("6")), "o saldo em produção não nasce cheio"
    assert _where(pedido) == started.pk
    entrega = delivery_reason(pedido.pk)
    assert _ledger(started) == [(D("10"), "make", "produção do lote"), (D("-4"), "sell", entrega)]

    lot = _realize(baguete, 10, today, to=vitrine, source=producao, from_batch=STARTED)

    assert _qty(lot) == D("6")
    assert _qty(started) == D("0")
    assert _where(pedido) == lot.pk
    assert _total(Move.Kind.SELL) == D("-4")


def test_partial_start_carries_what_fits_and_keeps_the_rest_owed(baguete, producao, today):
    """Plano de 10 com 8 entregues, entram 6 em produção: 6 seguem, 2 ficam devidos ao plano."""
    planned = _plan(baguete, 10, today, producao)
    pedido = _hold(baguete, 8, today)
    _deliver(pedido)

    started = stock.receive(D("6"), SKU, producao, target_date=today, batch=STARTED, reason="produção do lote")
    carried = StockPlanning.carry_deliveries(planned, started, limit=D("6"))

    assert carried == D("6")
    assert (_qty(planned), _qty(started)) == (D("8"), D("0"))
    assert _where(pedido) == planned.pk
    assert StockPlanning.carry_deliveries(planned, started, limit=D("0")) == D("0")


def test_carry_is_idempotent(baguete, producao, today):
    planned = _plan(baguete, 10, today, producao)
    _deliver(_hold(baguete, 4, today))
    started = stock.receive(D("10"), SKU, producao, target_date=today, batch=STARTED, reason="produção do lote")

    assert StockPlanning.carry_deliveries(planned, started, limit=D("10")) == D("4")
    assert StockPlanning.carry_deliveries(planned, started, limit=D("10")) == D("0")
    assert (_qty(planned), _qty(started)) == (D("10"), D("6"))


def test_carry_refuses_what_is_not_a_production_balance(baguete, producao, vitrine, today):
    planned = _plan(baguete, 10, today, producao)
    physical = stock.receive(D("5"), SKU, vitrine, reason="na vitrine")
    other = stock.plan(D("5"), SimpleNamespace(sku="CROISSANT"), today, position=producao, reason="plano")

    for source, destination in ((physical, planned), (planned, planned), (planned, other)):
        with pytest.raises(StockError) as error:
            StockPlanning.carry_deliveries(source, destination, limit=D("1"))
        assert error.value.code == "INVALID_CARRY"
